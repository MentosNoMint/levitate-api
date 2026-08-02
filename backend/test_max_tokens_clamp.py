import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Добавляем backend в sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.providers.antigravity import AntigravityProvider
from app.db.models import Credential

# Будем сохранять перехваченные запросы здесь
captured_requests = []

class MockResponse:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self._content = content

    async def aread(self):
        return self._content

    async def aiter_lines(self):
        # Возвращаем пустой генератор, чтобы выйти из цикла чтения линий
        if False:
            yield

    @property
    def request(self):
        return MagicMock()

def mock_stream(*args, **kwargs):
    # httpx.AsyncClient.stream принимает метод как первый аргумент, URL как второй
    # В коде antigravity.py: client.stream("POST", url, headers=headers, json=body)
    method = args[0] if len(args) > 0 else kwargs.get("method")
    url = args[1] if len(args) > 1 else kwargs.get("url")
    json_body = kwargs.get("json")
    
    captured_requests.append({
        "method": method,
        "url": url,
        "json": json_body
    })
    
    mock_resp = MockResponse(200, b"")
    
    # Для использования с контекстным менеджером async with client.stream(...) as response:
    context_mock = MagicMock()
    context_mock.__aenter__ = AsyncMock(return_value=mock_resp)
    context_mock.__aexit__ = AsyncMock(return_value=None)
    return context_mock

async def run_test():
    # Мокаем decrypt_secret
    with patch("app.providers.antigravity.decrypt_secret", return_value='{"refresh_token": "mocked", "project_id": "test-project"}'):
        # Мокаем redis_client
        with patch("app.providers.antigravity.redis_client", MagicMock()):
            
            # Создаем фейковые credentials
            cred = Credential(
                id="00000000-0000-0000-0000-000000000001",
                user_id="261000a1-45fa-442f-baf1-1fe36a1bc896",
                type="google",
                name="Google Test",
                provider="antigravity",
                encrypted_secret="encrypted_mock"
            )
            
            provider = AntigravityProvider(credential=cred)
            # Мокаем get_access_token, чтобы не ходить по сети за токеном
            provider.get_access_token = AsyncMock(return_value="mocked-access-token")
            
            # Патчим httpx.AsyncClient.stream
            with patch("httpx.AsyncClient.stream", side_effect=mock_stream):
                
                print("1. Тестируем модель gemini-3.1-pro-high (gemini-pro-agent) с max_tokens=65536...")
                captured_requests.clear()
                try:
                    # Запускаем генератор, чтобы вызвать внутренний цикл
                    gen = await provider.chat_completion(
                        model="gemini-3.1-pro-high",
                        messages=[{"role": "user", "content": "Hello"}],
                        max_tokens=65536
                    )
                    # Вычитываем генератор (хотя он вернет пустоту)
                    async for _ in gen:
                        pass
                except Exception as e:
                    # Игнорируем ошибки парсинга пустого ответа, нам важно что ушло в сеть
                    pass
                
                assert len(captured_requests) > 0, "Запрос не был отправлен!"
                req_body = captured_requests[0]["json"]
                gen_config = req_body["request"].get("generationConfig", {})
                max_output_tokens = gen_config.get("maxOutputTokens")
                print(f"Отправленный maxOutputTokens: {max_output_tokens}")
                
                # На текущем коде (без фикса) это значение будет 65536. После фикса должно стать 8192.
                # Мы пока просто напечатаем его, чтобы увидеть текущее поведение.
                
                print("\n2. Тестируем модель gemini-3.5-flash-high (gemini-3-flash-agent) с max_tokens=65536...")
                captured_requests.clear()
                try:
                    gen = await provider.chat_completion(
                        model="gemini-3.5-flash-high",
                        messages=[{"role": "user", "content": "Hello"}],
                        max_tokens=65536
                    )
                    async for _ in gen:
                        pass
                except Exception:
                    pass
                
                req_body_flash = captured_requests[0]["json"]
                gen_config_flash = req_body_flash["request"].get("generationConfig", {})
                max_output_tokens_flash = gen_config_flash.get("maxOutputTokens")
                print(f"Отправленный maxOutputTokens для Flash: {max_output_tokens_flash}")
                
                # Проверим, как сработает clamp после того, как мы внесем изменения.
                
if __name__ == "__main__":
    asyncio.run(run_test())
