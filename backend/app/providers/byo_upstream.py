from typing import Any, List, Dict
import litellm
from app.providers.base import BaseProvider
from app.crypto.cipher import decrypt_secret
from app.security.egress import sanitize_headers

class BYOUpstreamProvider(BaseProvider):
    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Any:
        api_key = decrypt_secret(self.credential.encrypted_secret)
        headers_dict = {"Authorization": f"Bearer {api_key}"}
        if self.credential.provider == "azure":
            headers_dict = {"api-key": api_key}
        custom_headers = sanitize_headers(headers_dict)
        
        return await litellm.acompletion(
            model=f"{self.credential.provider}/{model}",
            messages=messages,
            api_key=api_key,
            base_url=self.credential.base_url,
            custom_headers=custom_headers,
            **kwargs
        )

    async def embedding(self, model: str, input_data: Any, **kwargs) -> Any:
        api_key = decrypt_secret(self.credential.encrypted_secret)
        headers_dict = {"Authorization": f"Bearer {api_key}"}
        if self.credential.provider == "azure":
            headers_dict = {"api-key": api_key}
        custom_headers = sanitize_headers(headers_dict)
        
        return await litellm.aembedding(
            model=f"{self.credential.provider}/{model}",
            input=input_data,
            api_key=api_key,
            base_url=self.credential.base_url,
            custom_headers=custom_headers,
            **kwargs
        )
