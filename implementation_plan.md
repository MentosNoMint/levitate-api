# План реализации: Безопасность окружения и шифрования в Production (Task 1)

> **Для Antigravity:** REQUIRED SUB-SKILL: Load executing-plans to implement this plan task-by-task.

**Goal:** Гарантировать, что приложение упадет с ошибкой на этапе старта в production, если критические переменные безопасности не установлены или содержат дефолтные значения для разработки.

**Architecture:** 
- При импорте модулей `cipher.py` и `auth.py` проверяется значение переменной окружения `APP_ENV` (без учета регистра).
- Если `APP_ENV` равен `"production"`, то производится валидация ключей `ENCRYPTION_KEY` и `AUTH_SECRET`.
- Если ключи отсутствуют, пустые или соответствуют небезопасным значениям по умолчанию (`vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8=` или `dev-auth-secret-key-32-chars-minimum-for-security`), выбрасывается исключение `RuntimeError`.

**Tech Stack:** Python 3, FastAPI, cryptography (Fernet)

---

### Шаг 1: Обновление .env.example
**Файлы:**
- Modify: `C:/Repos/levitate-api/.env.example`

**Действие:**
Добавить в конец файла:
```ini
APP_ENV=development
ALLOW_MOCK_AUTH=true
ALLOWED_ADMIN_EMAILS=admin@levitate.ai,dev-user@levitate.ai
```

---

### Шаг 2: Безопасность шифрования в cipher.py
**Файлы:**
- Modify: `C:/Repos/levitate-api/backend/app/crypto/cipher.py`

**Действие:**
Изменить логику инициализации `_key` и `cipher`.
Если `APP_ENV` равен `"production"` (case-insensitive), проверить `ENCRYPTION_KEY`.
Если `ENCRYPTION_KEY` отсутствует, пуст или равен `"vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8="`, выкинуть `RuntimeError`.
Иначе выполнить стандартную инициализацию.

Код для `cipher.py`:
```python
import os
import base64
from cryptography.fernet import Fernet

app_env = os.getenv("APP_ENV", "development").lower()
_key = os.getenv("ENCRYPTION_KEY")

if app_env == "production":
    if not _key or _key == "vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8=":
        raise RuntimeError("ENCRYPTION_KEY must be securely configured in production mode!")
else:
    if not _key:
        _key = base64.urlsafe_b64encode(b"01234567890123456789012345678901")
    else:
        try:
            base64.urlsafe_b64decode(_key)
        except Exception:
            _key = base64.urlsafe_b64encode(_key.encode().ljust(32)[:32])

cipher = Fernet(_key)

def encrypt_secret(secret: str) -> str:
    return cipher.encrypt(secret.encode()).decode()

def decrypt_secret(encrypted: str) -> str:
    return cipher.decrypt(encrypted.encode()).decode()
```

---

### Шаг 3: Безопасность подписи токенов в auth.py
**Файлы:**
- Modify: `C:/Repos/levitate-api/backend/app/security/auth.py`

**Действие:**
Изменить определение `AUTH_SECRET`.
Если `APP_ENV` равен `"production"` (case-insensitive), проверить `AUTH_SECRET`.
Если `AUTH_SECRET` отсутствует, пуст или равен `"dev-auth-secret-key-32-chars-minimum-for-security"` или `"vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8="`, выкинуть `RuntimeError`.

Код для `auth.py`:
```python
app_env = os.getenv("APP_ENV", "development").lower()
AUTH_SECRET = os.getenv("AUTH_SECRET") or os.getenv("ENCRYPTION_KEY")

if app_env == "production":
    if not AUTH_SECRET or AUTH_SECRET in ("dev-auth-secret-key-32-chars-minimum-for-security", "vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8="):
        raise RuntimeError("AUTH_SECRET must be securely configured in production mode!")
else:
    if not AUTH_SECRET:
        AUTH_SECRET = "dev-auth-secret-key-32-chars-minimum-for-security"
```

---

### Шаг 4: Проверка работоспособности (Верификация)
Мы запустим тесты бэкенда и проверим старт приложения в режиме `APP_ENV=production` без ключей (должен падать) и с корректными ключами (должен запускаться).

---

### Шаг 5: Коммит изменений
Закоммитить изменения с сообщением:
`feat(security): enforce secure encryption keys in production`
