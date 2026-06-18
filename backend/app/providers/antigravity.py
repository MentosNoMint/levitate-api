import json
import os
import asyncio
import httpx
import litellm
from typing import Any, List, Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy import update

from app.providers.base import BaseProvider
from app.crypto.cipher import decrypt_secret, encrypt_secret
from app.security.egress import sanitize_headers
from app.redis_client import redis_client
from app.db.session import AsyncSessionLocal
from app.db.models import Credential
from app.core.constants import get_credential_access_token_key

def _antigravity_headers(token: str) -> dict:
    return {
        "User-Agent": "antigravity/1.15.8 windows/amd64",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}',
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

class AntigravityProvider(BaseProvider):
    def _format_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            res = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        res.append(item.get("text", ""))
                elif isinstance(item, str):
                    res.append(item)
            return "".join(res)
        return str(content) if content is not None else ""

    async def get_access_token(self) -> str:
        cache_key = get_credential_access_token_key(self.credential.id)
        cached_token = await redis_client.get(cache_key)
        if cached_token:
            return cached_token

        secret_data = decrypt_secret(self.credential.encrypted_secret)
        try:
            config = json.loads(secret_data)
            refresh_token = config.get("refresh_token")
            client_id = config.get("client_id")
            client_secret = config.get("client_secret")
        except Exception:
            refresh_token = secret_data
            client_id = None
            client_secret = None

        async with httpx.AsyncClient() as client:
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
            if client_id and client_secret:
                payload["client_id"] = client_id
                payload["client_secret"] = client_secret

            resp = await client.post("https://oauth2.googleapis.com/token", data=payload)
            resp.raise_for_status()
            access_token = resp.json()["access_token"]
            
        await redis_client.set(cache_key, access_token, ex=3000)
        return access_token

    async def _trigger_cooldown(self) -> None:
        async with AsyncSessionLocal() as db:
            cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=5)
            stmt = (
                update(Credential)
                .where(Credential.id == self.credential.id)
                .values(status="cooldown", reset_at=cooldown_until)
            )
            await db.execute(stmt)
            await db.commit()

    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Any:
        import uuid
        import time

        try:
            access_token = await self.get_access_token()
        except Exception as oauth_err:
            await self._trigger_cooldown()
            raise oauth_err

        try:
            secret_data = decrypt_secret(self.credential.encrypted_secret)
            secret_dict = json.loads(secret_data)
            project_id = secret_dict.get("project_id", "levitate-api")
        except Exception:
            project_id = "levitate-api"

        MODEL_MAPPINGS = {
            "Claude 4.6 Sonnet": "claude-sonnet-4-6",
            "Claude 4.6 Opus (Thinking)": "claude-opus-4-6-thinking",
            "Gemini 3.5 Flash Low": "gemini-3.5-flash-low",
            "Gemini 3.5 Flash Extra Low": "gemini-3.5-flash-extra-low",
            "Gemini 3 Flash": "gemini-3-flash",
            "Gemini 3.1 Flash Lite": "gemini-3.1-flash-lite",
            "Gemini 3.1 Flash Image": "gemini-3.1-flash-image",
            "Gemini 3.1 Pro (Low/High)": "gemini-3.1-pro-low",
            "Gemini 3 Flash Agent": "gemini-3-flash-agent",
            "Gemini Pro Agent": "gemini-pro-agent",
            "claude-4.6-sonnet": "claude-sonnet-4-6",
            "claude-4.6-opus-thinking": "claude-opus-4-6-thinking",
            "gemini-3.5-flash-low": "gemini-3.5-flash-low",
            "gemini-3.5-flash-extra-low": "gemini-3.5-flash-extra-low",
            "gemini-3-flash": "gemini-3-flash",
            "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
            "gemini-3.1-flash-image": "gemini-3.1-flash-image",
            "gemini-3.1-pro-low-high": "gemini-3.1-pro-low",
            "gemini-3-flash-agent": "gemini-3-flash-agent",
            "gemini-pro-agent": "gemini-pro-agent"
        }
        mapped_model = MODEL_MAPPINGS.get(model)
        if not mapped_model:
            for k, v in MODEL_MAPPINGS.items():
                if k.lower() == model.lower():
                    mapped_model = v
                    break
        if not mapped_model:
            mapped_model = model

        headers = {
            "User-Agent": "antigravity/2.35.0 windows/amd64",
            "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
            "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}',
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        contents = []
        system_instruction = None
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            formatted_text = self._format_content(content)
            if role == "system":
                system_instruction = {"parts": [{"text": formatted_text}]}
            else:
                gemini_role = "model" if role == "assistant" else "user"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": formatted_text}]
                })

        request_body = {
            "contents": contents
        }
        if system_instruction:
            request_body["systemInstruction"] = system_instruction

        body = {
            "project": project_id,
            "model": mapped_model,
            "request": request_body
        }
        print("DEBUG_COMPANION_REQUEST_BODY:", json.dumps(body), flush=True)

        async def response_generator():
            client_timeout = httpx.Timeout(30.0)
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                url = "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
                try:
                    async with client.stream("POST", url, headers=headers, json=body) as response:
                        if response.status_code != 200:
                            body_text = await response.aread()
                            raise Exception(f"HTTP {response.status_code}: {body_text.decode()}")
                        
                        chat_id = f"chatcmpl-{uuid.uuid4()}"
                        created_time = int(time.time())
                        
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if not data_str:
                                    continue
                                print("DEBUG_RAW_SSE:", data_str, flush=True)
                                try:
                                    chunk_json = json.loads(data_str)
                                except Exception:
                                    continue
                                
                                response_obj = chunk_json.get("response", {})
                                candidates = response_obj.get("candidates", [])
                                text_content = ""
                                finish_reason = None
                                if candidates:
                                    candidate = candidates[0]
                                    content = candidate.get("content", {})
                                    parts = content.get("parts", [])
                                    text_content = "".join(p.get("text", "") for p in parts if "text" in p)
                                    finish_reason = candidate.get("finishReason")
                                    if finish_reason:
                                        finish_reason = finish_reason.lower()
                                
                                usage_meta = response_obj.get("usageMetadata", {})
                                usage_obj = None
                                if usage_meta:
                                    prompt_tokens = usage_meta.get("promptTokenCount", 0)
                                    completion_tokens = usage_meta.get("candidatesTokenCount", 0)
                                    from litellm import Usage
                                    usage_obj = Usage(
                                        prompt_tokens=prompt_tokens,
                                        completion_tokens=completion_tokens,
                                        total_tokens=prompt_tokens + completion_tokens
                                    )
                                
                                from litellm.types.utils import ModelResponseStream
                                choice = {
                                    "index": 0,
                                    "delta": {
                                        "content": text_content
                                    },
                                    "finish_reason": finish_reason
                                }
                                yield ModelResponseStream(
                                    id=chat_id,
                                    object="chat.completion.chunk",
                                    created=created_time,
                                    model=model,
                                    choices=[choice],
                                    usage=usage_obj
                                )
                except Exception as stream_err:
                    await self._trigger_cooldown()
                    raise stream_err

        if kwargs.get("stream", False):
            return response_generator()
        else:
            full_text = []
            final_usage = None
            final_chat_id = None
            final_created = None
            final_finish_reason = "stop"
            
            async for chunk in response_generator():
                if chunk.choices and chunk.choices[0].delta.get("content"):
                    full_text.append(chunk.choices[0].delta["content"])
                if chunk.usage:
                    final_usage = chunk.usage
                if chunk.id:
                    final_chat_id = chunk.id
                if chunk.created:
                    final_created = chunk.created
                if chunk.choices and chunk.choices[0].finish_reason:
                    final_finish_reason = chunk.choices[0].finish_reason
                    
            from litellm import ModelResponse, Usage
            if not final_usage:
                final_usage = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            if not final_chat_id:
                final_chat_id = f"chatcmpl-{uuid.uuid4()}"
            if not final_created:
                final_created = int(time.time())
                
            return ModelResponse(
                id=final_chat_id,
                object="chat.completion",
                created=final_created,
                model=model,
                choices=[
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "".join(full_text)
                        },
                        "finish_reason": final_finish_reason
                    }
                ],
                usage=final_usage
            )

    async def _resolve_project_id(self, client: httpx.AsyncClient, headers: dict) -> str:
        try:
            secret_data = decrypt_secret(self.credential.encrypted_secret)
            secret_dict = json.loads(secret_data)
            if isinstance(secret_dict, dict) and "project_id" in secret_dict and secret_dict["project_id"]:
                return secret_dict["project_id"]
        except Exception:
            pass

        env_project_id = os.getenv("GOOGLE_USER_PROJECT", "levitate-api")

        load_resp = await client.post(
            "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
            headers=headers,
            json={"cloudaicompanionProject": env_project_id}
        )
        if load_resp.status_code == 200:
            load_data = load_resp.json()
            project_id = load_data.get("cloudaicompanionProject")
            if project_id:
                await self._save_project_id(project_id)
                return project_id

        load_resp = await client.post(
            "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
            headers=headers,
            json={}
        )
        if load_resp.status_code == 200:
            load_data = load_resp.json()
            project_id = load_data.get("cloudaicompanionProject")
            if project_id:
                await self._save_project_id(project_id)
                return project_id

        if load_resp.status_code == 200:
            load_data = load_resp.json()
            allowed_tiers = load_data.get("allowedTiers", [])
            is_user_defined = any(t.get("userDefinedCloudaicompanionProject") for t in allowed_tiers)
            if is_user_defined:
                await self._save_project_id(env_project_id)
                return env_project_id

        await client.post(
            "https://cloudcode-pa.googleapis.com/v1internal:onboardUser",
            headers=headers,
            json={}
        )

        for i in range(5):
            await asyncio.sleep(1.0)
            load_resp = await client.post(
                "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
                headers=headers,
                json={}
            )
            if load_resp.status_code == 200:
                load_data = load_resp.json()
                project_id = load_data.get("cloudaicompanionProject")
                if project_id:
                    await self._save_project_id(project_id)
                    return project_id

        raise Exception("Google Account has no eligible cloudaicompanionProject.")

    async def _save_project_id(self, project_id: str) -> None:
        try:
            secret_data = decrypt_secret(self.credential.encrypted_secret)
            secret_dict = json.loads(secret_data)
            if not isinstance(secret_dict, dict):
                secret_dict = {"refresh_token": secret_data}
        except Exception:
            secret_dict = {"refresh_token": decrypt_secret(self.credential.encrypted_secret)}

        secret_dict["project_id"] = project_id
        encrypted = encrypt_secret(json.dumps(secret_dict))

        async with AsyncSessionLocal() as db:
            stmt = (
                update(Credential)
                .where(Credential.id == self.credential.id)
                .values(encrypted_secret=encrypted)
            )
            await db.execute(stmt)
            await db.commit()

        self.credential.encrypted_secret = encrypted

    async def _save_quota_metadata(self, tier: str, load_error: str = None, quota_error: str = None) -> None:
        try:
            secret_data = decrypt_secret(self.credential.encrypted_secret)
            secret_dict = json.loads(secret_data)
            if not isinstance(secret_dict, dict):
                secret_dict = {"refresh_token": secret_data}
        except Exception:
            secret_dict = {"refresh_token": decrypt_secret(self.credential.encrypted_secret)}

        secret_dict["tier"] = tier
        if load_error:
            secret_dict["load_error"] = load_error
        else:
            secret_dict.pop("load_error", None)

        if quota_error:
            secret_dict["quota_error"] = quota_error
        else:
            secret_dict.pop("quota_error", None)

        encrypted = encrypt_secret(json.dumps(secret_dict))

        async with AsyncSessionLocal() as db:
            stmt = (
                update(Credential)
                .where(Credential.id == self.credential.id)
                .values(encrypted_secret=encrypted)
            )
            await db.execute(stmt)
            await db.commit()

        self.credential.encrypted_secret = encrypted

    async def fetch_quota(self) -> dict:
        try:
            access_token = await self.get_access_token()
        except Exception as e:
            return {"error": f"Failed to get access token: {str(e)}"}

        headers = _antigravity_headers(access_token)

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                project_id = await self._resolve_project_id(client, headers)
            except Exception as e:
                async with AsyncSessionLocal() as db:
                    stmt = (
                        update(Credential)
                        .where(Credential.id == self.credential.id)
                        .values(
                            status="error",
                            last_check_at=datetime.now(timezone.utc),
                            quota_total_tokens=1000000,
                            quota_used_tokens=1000000,
                            model_quotas={},
                        )
                    )
                    await db.execute(stmt)
                    await db.commit()
                await self._save_quota_metadata(tier="unknown", load_error=str(e))
                return {"error": f"Project resolution failed: {str(e)}", "load_error": str(e), "status": "error"}

            load_resp = await client.post(
                "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
                headers=headers,
                json={}
            )

            model_payload = {
                "project": project_id
            }
            quota_resp = await client.post(
                "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
                headers=headers,
                json=model_payload
            )

        load_ok = (load_resp.status_code == 200)
        quota_ok = (quota_resp.status_code == 200)

        load_data = load_resp.json() if load_ok else {}
        quota_data = quota_resp.json() if quota_ok else {}

        tier = load_data.get("tier", load_data.get("userTier", "unknown"))

        remaining_fraction = None
        quota_details = {}
        reset_at_val = None

        if quota_ok:
            min_fraction = None
            earliest_reset = None

            models_dict = quota_data.get("models", {})
            for m_id, m_info in models_dict.items():
                quota_info = m_info.get("quotaInfo")
                if quota_info:
                    display_name = m_info.get("displayName", m_id)
                    reset_time = quota_info.get("resetTime")
                    parsed_reset = None
                    if reset_time:
                        try:
                            parsed_reset = datetime.fromisoformat(reset_time.replace("Z", "+00:00"))
                            if earliest_reset is None or parsed_reset < earliest_reset:
                                earliest_reset = parsed_reset
                        except Exception:
                            pass

                    frac = quota_info.get("remainingFraction")
                    if frac is None:
                        if parsed_reset and datetime.now(timezone.utc) < parsed_reset:
                            frac = 0.0
                        else:
                            frac = 1.0
                    else:
                        frac = float(frac)

                    quota_details[display_name] = frac
                    if min_fraction is None or frac < min_fraction:
                        min_fraction = frac

            groups = quota_data.get("groups", [])
            for group in groups:
                buckets = group.get("buckets", [])
                for bucket in buckets:
                    display_name = bucket.get("displayName", bucket.get("bucketId", "unknown"))
                    reset_time = bucket.get("resetTime")
                    parsed_reset = None
                    if reset_time:
                        try:
                            parsed_reset = datetime.fromisoformat(reset_time.replace("Z", "+00:00"))
                            if earliest_reset is None or parsed_reset < earliest_reset:
                                earliest_reset = parsed_reset
                        except Exception:
                            pass

                    frac = bucket.get("remainingFraction")
                    if frac is None:
                        if parsed_reset and datetime.now(timezone.utc) < parsed_reset:
                            frac = 0.0
                        else:
                            frac = 1.0
                    else:
                        frac = float(frac)

                    quota_details[display_name] = frac
                    if min_fraction is None or frac < min_fraction:
                        min_fraction = frac

            if min_fraction is not None:
                remaining_fraction = min_fraction
            if earliest_reset:
                reset_at_val = earliest_reset

        if remaining_fraction is None:
            remaining_fraction = 1.0

        status_val = "active"
        if remaining_fraction <= 0.0:
            status_val = "exhausted"

        if not load_ok or not quota_ok:
            status_val = "error"
            remaining_fraction = 0.0
            models_list = self.credential.models or []
            quota_details = {m: 0.0 for m in models_list}

        total_tokens = 1_000_000
        used_tokens = int(total_tokens * (1 - remaining_fraction))

        if reset_at_val is None:
            reset_at_val = datetime.now(timezone.utc) + timedelta(hours=24)

        async with AsyncSessionLocal() as db:
            stmt = (
                update(Credential)
                .where(Credential.id == self.credential.id)
                .values(
                    quota_total_tokens=total_tokens,
                    quota_used_tokens=used_tokens,
                    last_check_at=datetime.now(timezone.utc),
                    reset_at=reset_at_val,
                    model_quotas=quota_details,
                    status=status_val,
                )
            )
            await db.execute(stmt)
            await db.commit()

        result = {
            "tier": tier,
            "remaining_fraction": remaining_fraction,
            "quota_total_tokens": total_tokens,
            "quota_used_tokens": used_tokens,
            "remaining_pct": round(remaining_fraction * 100, 1),
            "reset_at": reset_at_val.isoformat() if reset_at_val else None,
            "model_quotas": quota_details,
            "status": status_val,
            "raw_load": load_data,
            "raw_quota": quota_data,
        }

        if load_resp.status_code != 200:
            result["load_error"] = f"HTTP {load_resp.status_code}: {load_resp.text[:200]}"
        if quota_resp.status_code != 200:
            result["quota_error"] = f"HTTP {quota_resp.status_code}: {quota_resp.text[:200]}"

        await self._save_quota_metadata(
            tier=tier,
            load_error=result.get("load_error"),
            quota_error=result.get("quota_error")
        )

        return result

