import hashlib
import json
import os
import asyncio
import time
import uuid
import httpx
import logging
from typing import Any, List, Dict

logger = logging.getLogger(__name__)
from datetime import datetime, timezone, timedelta
from sqlalchemy import update

from app.providers.base import BaseProvider
from app.crypto.cipher import decrypt_secret, encrypt_secret
from app.redis_client import redis_client
from app.db.session import AsyncSessionLocal
from app.db.models import Credential
from app.core.constants import get_credential_access_token_key, get_credential_cooldown_key

GOOGLE_CLOUD_CODE_ENDPOINT = os.getenv(
    "ANTIGRAVITY_CLOUD_CODE_ENDPOINT", 
    "https://daily-cloudcode-pa.googleapis.com"
)

# Cloudflare Worker egress IPs are sometimes geo-classified as blocked by Google
# even when the worker itself is healthy. Retry a few times before bubbling up.
_GEO_LOCATION_RETRY_LIMIT = 5


def _is_geo_blocked_error(error_text: str) -> bool:
    text = (error_text or "").lower()
    return (
        "user location is not supported" in text
        or "not available in your country" in text
        or "user_location" in text
        or ("failed_precondition" in text and "location" in text)
        or "location is not supported" in text
    )


def _antigravity_headers(token: str) -> dict:
    return {
        "User-Agent": "antigravity/2.35.0 windows/amd64",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}',
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

def convert_schema_to_gemini(schema: Any, is_properties_dict: bool = False) -> Any:
    if isinstance(schema, dict):
        new_schema = {}
        allowed_keys = {"type", "format", "description", "nullable", "enum", "items", "properties", "required"}
        for k, v in schema.items():
            if not is_properties_dict and k not in allowed_keys:
                continue
            if k == "type" and isinstance(v, str):
                new_schema[k] = v.upper()
            else:
                new_schema[k] = convert_schema_to_gemini(v, is_properties_dict=(k == "properties"))
        return new_schema
    elif isinstance(schema, list):
        return [convert_schema_to_gemini(x, is_properties_dict) for x in schema]
    return schema

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

    def _parse_parts(self, content: Any) -> list:
        if isinstance(content, str):
            return [{"text": content}] if content else []
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append({"text": item})
                elif isinstance(item, dict):
                    t = item.get("type")
                    if t == "text":
                        text = item.get("text", "")
                        if text:
                            parts.append({"text": text})
                    elif t == "image_url":
                        img_url_obj = item.get("image_url", {})
                        url = img_url_obj.get("url", "")
                        if url.startswith("data:"):
                            try:
                                header, base64_data = url.split(",", 1)
                                mime_type = header.split(";")[0].split(":")[1]
                                parts.append({
                                    "inlineData": {
                                        "mimeType": mime_type,
                                        "data": base64_data
                                    }
                                })
                            except Exception:
                                pass
            return parts
        return []

    async def get_access_token(self, force_refresh: bool = False) -> str:
        cache_key = get_credential_access_token_key(self.credential.id)
        if not force_refresh:
            cached_token = await redis_client.get(cache_key)
            if cached_token:
                return cached_token

        lock_key = f"lock:token_refresh:{self.credential.id}"
        lock_token = uuid.uuid4().hex
        acquired = await redis_client.set(lock_key, lock_token, ex=90, nx=True)
        
        if not acquired:
            for _ in range(950):
                await asyncio.sleep(0.1)
                cached_token = await redis_client.get(cache_key)
                if cached_token:
                    return cached_token
            raise TimeoutError("Timed out waiting for the token refresh lock")
                    
        try:
            secret_data = decrypt_secret(self.credential.encrypted_secret)
            config = None
            try:
                config = json.loads(secret_data)
                refresh_token = config.get("refresh_token")
                client_id = config.get("client_id")
                client_secret = config.get("client_secret")
            except Exception:
                refresh_token = secret_data
                client_id = None
                client_secret = None

            if not client_id or not client_secret:
                client_id = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID", "")
                client_secret = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", "")

            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                }
                if client_id and client_secret:
                    payload["client_id"] = client_id
                    payload["client_secret"] = client_secret

                resp = await client.post("https://oauth2.googleapis.com/token", data=payload)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400 and "invalid_grant" in e.response.text.lower():
                        await self._mark_reauth_required()
                        await redis_client.delete(cache_key)
                        raise Exception(f"invalid_grant: {e.response.text}")
                    raise
                token_data = resp.json()
                access_token = token_data["access_token"]
                expires_in = int(token_data.get("expires_in", 3600) or 3600)
                rotated_refresh_token = token_data.get("refresh_token")

            if rotated_refresh_token:
                persisted_config = dict(config) if isinstance(config, dict) else {"refresh_token": refresh_token}
                persisted_config["refresh_token"] = rotated_refresh_token
                encrypted = encrypt_secret(json.dumps(persisted_config))
                async with AsyncSessionLocal() as db:
                    stmt = (
                        update(Credential)
                        .where(Credential.id == self.credential.id)
                        .values(encrypted_secret=encrypted)
                    )
                    await db.execute(stmt)
                    await db.commit()
                self.credential.encrypted_secret = encrypted

            # Refresh early enough that a request never starts with an almost
            # expired token. The Redis TTL is the single-flight cache lifetime.
            await redis_client.set(cache_key, access_token, ex=max(1, expires_in - 60))
            return access_token
        finally:
            if acquired:
                await redis_client.compare_delete(lock_key, lock_token)

    async def _acquire_secret_write_lock(self) -> str:
        """Serialize encrypted-secret updates with OAuth refresh writes."""
        lock_key = f"lock:token_refresh:{self.credential.id}"
        token = uuid.uuid4().hex
        for _ in range(950):
            if await redis_client.set(lock_key, token, ex=90, nx=True):
                return token
            await asyncio.sleep(0.1)
        raise TimeoutError("Timed out waiting for credential secret write lock")

    async def _release_secret_write_lock(self, token: str) -> None:
        await redis_client.compare_delete(f"lock:token_refresh:{self.credential.id}", token)

    async def _mark_reauth_required(self) -> None:
        async with AsyncSessionLocal() as db:
            stmt = (
                update(Credential)
                .where(Credential.id == self.credential.id)
                .values(status="reauth_required", reset_at=None)
            )
            await db.execute(stmt)
            await db.commit()
        self.credential.status = "reauth_required"
        self.credential.reset_at = None

    async def _trigger_cooldown(self, minutes: int = 1) -> None:
        """Apply a short RPM-style cooldown without touching terminal statuses.

        Must not be called for client/schema/model errors or generic stream
        failures — those are classified by the chat failure handler instead.
        Cooldown expiry lives in Redis so the quota window in reset_at is
        never overwritten by a 429 (#6, N1).
        """
        async with AsyncSessionLocal() as db:
            stmt = (
                update(Credential)
                .where(
                    Credential.id == self.credential.id,
                    Credential.status.notin_(["reauth_required", "disabled", "exhausted"]),
                )
                .values(status="cooldown")
            )
            await db.execute(stmt)
            await db.commit()
        await redis_client.set(get_credential_cooldown_key(self.credential.id), "1", ex=300)
        self.credential.status = "cooldown"

    @staticmethod
    def _derive_session_id(messages: List[Dict[str, str]]) -> str:
        for message in messages or []:
            if isinstance(message, dict) and message.get("role") == "user":
                canonical = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                return f"session-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        return "session-anonymous"

    @staticmethod
    def _make_request_id(session_id: str, kwargs: dict) -> str:
        agent_seed = str(kwargs.get("agent_id") or kwargs.get("agent") or session_id)
        agent = hashlib.sha256(agent_seed.encode("utf-8")).hexdigest()[:24]
        trajectory = str(kwargs.get("trajectory_id") or "0").replace("/", "_")
        step = str(kwargs.get("step") or "1").replace("/", "_")
        return f"agent/{agent}/{int(time.time() * 1000)}/{trajectory}/{step}-{uuid.uuid4().hex[:12]}"

    async def chat_completion(self, model: str, messages: List[Dict[str, str]], **kwargs) -> Any:
        session_id = str(kwargs.get("session_id") or self._derive_session_id(messages))
        request_id = str(kwargs.get("request_id") or self._make_request_id(session_id, kwargs))

        try:
            secret_data = decrypt_secret(self.credential.encrypted_secret)
            secret_dict = json.loads(secret_data)
            project_id = secret_dict.get("project_id") or os.getenv("GOOGLE_USER_PROJECT") or "levitate-api"
        except Exception:
            project_id = os.getenv("GOOGLE_USER_PROJECT") or "levitate-api"
        from app.core.constants import resolve_antigravity_upstream_model
        mapped_model = resolve_antigravity_upstream_model(model)



        contents = []
        system_instruction = None
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                formatted_text = self._format_content(content)
                if system_instruction is None:
                    system_instruction = {"parts": [{"text": formatted_text}]}
                else:
                    system_instruction["parts"].append({"text": formatted_text})
            else:
                parts = []
                if role == "assistant":
                    gemini_role = "model"
                    tool_calls = msg.get("tool_calls")
                    if tool_calls:
                        for tc in tool_calls:
                            fn = tc.get("function", {})
                            fn_name = fn.get("name")
                            fn_args_str = fn.get("arguments", "{}")
                            try:
                                fn_args = json.loads(fn_args_str)
                            except Exception:
                                fn_args = {}
                            part = {
                                "functionCall": {
                                    "name": fn_name,
                                    "args": fn_args,
                                    "id": tc.get("id", "")
                                }
                            }
                            thought_sig = tc.get("thought_signature")
                            if not thought_sig:
                                tc_id = tc.get("id")
                                if tc_id:
                                    redis_val = await redis_client.get(f"thought_signature:{tc_id}")
                                    if redis_val:
                                        thought_sig = redis_val.decode("utf-8") if isinstance(redis_val, bytes) else str(redis_val)
                            if thought_sig:
                                part["thoughtSignature"] = thought_sig
                            parts.append(part)
                    
                    formatted_text = self._format_content(content)
                    if formatted_text:
                        parts.append({"text": formatted_text})
                elif role == "tool":
                    tool_name = msg.get("name")
                    if not tool_name:
                        tool_call_id = msg.get("tool_call_id")
                        if tool_call_id:
                            for prev_msg in reversed(messages):
                                prev_tool_calls = prev_msg.get("tool_calls") if isinstance(prev_msg, dict) else getattr(prev_msg, "tool_calls", None)
                                if prev_tool_calls:
                                    for tc in prev_tool_calls:
                                        if isinstance(tc, dict) and tc.get("id") == tool_call_id:
                                            fn = tc.get("function", {})
                                            if isinstance(fn, dict) and fn.get("name"):
                                                tool_name = fn.get("name")
                                                break
                                if tool_name:
                                    break
                    if not tool_name:
                        for prev_msg in reversed(messages):
                            prev_tool_calls = prev_msg.get("tool_calls") if isinstance(prev_msg, dict) else getattr(prev_msg, "tool_calls", None)
                            if prev_tool_calls:
                                for tc in prev_tool_calls:
                                    if isinstance(tc, dict):
                                        fn = tc.get("function", {})
                                        if isinstance(fn, dict) and fn.get("name"):
                                            tool_name = fn.get("name")
                                            break
                            if tool_name:
                                break
                    if not tool_name:
                        openai_tools = kwargs.get("tools")
                        if openai_tools:
                            for tool in openai_tools:
                                if isinstance(tool, dict) and tool.get("type") == "function":
                                    fn = tool.get("function", {})
                                    if isinstance(fn, dict) and fn.get("name"):
                                        tool_name = fn.get("name")
                                        break
                    if not tool_name:
                        tool_name = "unknown_tool"
                    tool_content = self._format_content(content)
                    try:
                        response_json = json.loads(tool_content)
                        if not isinstance(response_json, dict):
                            response_json = {"result": response_json}
                    except Exception:
                        response_json = {"result": tool_content}
                    
                    part = {
                        "functionResponse": {
                            "name": tool_name,
                            "response": response_json,
                            "id": msg.get("tool_call_id", "")
                        }
                    }
                    if contents and contents[-1]["role"] == "user" and any("functionResponse" in p for p in contents[-1]["parts"]):
                        contents[-1]["parts"].append(part)
                    else:
                        contents.append({
                            "role": "user",
                            "parts": [part]
                        })
                    continue
                else:
                    gemini_role = "user"
                    parts = self._parse_parts(content)
                
                if parts:
                    contents.append({
                        "role": gemini_role,
                        "parts": parts
                    })

        # Antigravity proto: sessionId lives under request.*, but requestId /
        # userAgent are top-level wrapper fields. Putting requestId inside
        # request triggers HTTP 400 UNKNOWN_FIELD (seen on gemini-3.1-pro-high).
        request_body = {
            "contents": contents,
            "sessionId": session_id,
        }
        if system_instruction:
            request_body["systemInstruction"] = system_instruction

        supports_thinking = "thinking" in mapped_model.lower() or "thinking" in model.lower()
        thinking_budget = None
        
        if supports_thinking:
            thinking_budget = 2048
            if "thinking" in kwargs:
                client_thinking = kwargs.get("thinking")
                if isinstance(client_thinking, dict):
                    if client_thinking.get("type") == "enabled" or client_thinking.get("type") is True:
                        thinking_budget = client_thinking.get("budget_tokens") or thinking_budget
                elif isinstance(client_thinking, bool) and client_thinking:
                    thinking_budget = thinking_budget or 2048
            if "thinking_budget" in kwargs:
                thinking_budget = kwargs.get("thinking_budget") or thinking_budget
            if "reasoning_effort" in kwargs:
                effort = kwargs.get("reasoning_effort")
                if effort == "high":
                    thinking_budget = 4096
                elif effort == "medium":
                    thinking_budget = 2048
                elif effort == "low":
                    thinking_budget = 1024
                    
        gen_config = {}
        if thinking_budget is not None:
            gen_config["thinkingConfig"] = {
                "thinkingBudget": thinking_budget
            }
        
        max_tokens = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")
        if max_tokens is not None:
            # РџРѕ СѓРјРѕР»С‡Р°РЅРёСЋ Р»РёРјРёС‚ РґР»СЏ Р±РѕР»СЊС€РёРЅСЃС‚РІР° РјРѕРґРµР»РµР№ Gemini СЃРѕСЃС‚Р°РІР»СЏРµС‚ 8192.
            # Р”Р»СЏ РјРѕРґРµР»РµР№ СЃ РїРѕРґРґРµСЂР¶РєРѕР№ РґР»РёРЅРЅРѕРіРѕ РІС‹РІРѕРґР° (flash-agent, thinking) Р»РёРјРёС‚ СЂР°РІРµРЅ 65536.
            max_limit = 8192
            lower_mapped = mapped_model.lower() if mapped_model else ""
            if "flash-agent" in lower_mapped or "thinking" in lower_mapped:
                max_limit = 65536
            gen_config["maxOutputTokens"] = min(int(max_tokens), max_limit)
            
        temperature = kwargs.get("temperature")
        if temperature is not None:
            gen_config["temperature"] = float(temperature)
            
        top_p = kwargs.get("top_p")
        if top_p is not None:
            gen_config["topP"] = float(top_p)
            
        stop = kwargs.get("stop")
        if stop is not None:
            if isinstance(stop, str):
                gen_config["stopSequences"] = [stop]
            elif isinstance(stop, list):
                gen_config["stopSequences"] = [str(s) for s in stop]

        if gen_config:
            request_body["generationConfig"] = gen_config

        openai_tools = kwargs.get("tools")
        if openai_tools:
            function_declarations = []
            has_google_search = False
            for tool in openai_tools:
                if tool.get("type") == "function":
                    fn = tool.get("function", {})
                    tool_def = {
                        "name": fn.get("name"),
                        "description": fn.get("description", "")
                    }
                    raw_params = fn.get("parameters", {})
                    if raw_params and raw_params.get("properties"):
                        tool_def["parameters"] = convert_schema_to_gemini(raw_params)
                    function_declarations.append(tool_def)
                elif tool.get("type") in ("google_search", "googleSearchRetrieval", "google_search_retrieval"):
                    has_google_search = True
                    
            tools_payload = []
            if function_declarations:
                tools_payload.append({"functionDeclarations": function_declarations})
            if has_google_search:
                tools_payload.append({
                    "googleSearchRetrieval": {
                        "dynamicRetrievalConfig": {
                            "mode": "MODE_DYNAMIC",
                            "dynamicThreshold": 0.0
                        }
                    }
                })
                
            if tools_payload:
                request_body["tools"] = tools_payload
                
                openai_tool_choice = kwargs.get("tool_choice")
                if openai_tool_choice:
                    mode = "AUTO"
                    if isinstance(openai_tool_choice, str):
                        if openai_tool_choice == "required":
                            mode = "ANY"
                        elif openai_tool_choice == "none":
                            mode = "NONE"
                    elif isinstance(openai_tool_choice, dict):
                        mode = "ANY"
                    
                    request_body["toolConfig"] = {
                        "functionCallingConfig": {
                            "mode": mode
                        }
                    }

        body = {
            "project": project_id,
            "model": mapped_model,
            "userAgent": "antigravity",
            "requestId": request_id,
            "request": request_body,
        }
        logger.debug(
            "Prepared Antigravity request model=%s session=%s request=%s",
            model,
            session_id,
            request_id,
        )
        # Full request bodies (user prompts) — only when explicitly enabled (#28)
        if os.getenv("ANTIGRAVITY_DEBUG_LOG", "").strip().lower() in ("1", "true", "yes"):
            try:
                with open("/app/debug.log", "a") as f:
                    f.write(f"MODEL: {model} kwargs: {json.dumps(kwargs)}\nBODY: {json.dumps(body)}\n")
            except Exception:
                pass

        async def response_generator():
            client_timeout = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
            url = f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:streamGenerateContent?alt=sse"
            # Auth refresh gets one extra attempt; geo/location flaps get several
            # because CF Worker egress IP classification is intermittent.
            max_attempts = 2 + _GEO_LOCATION_RETRY_LIMIT
            geo_retries = 0
            auth_retried = False
            for attempt in range(max_attempts):
                try:
                    token = await self.get_access_token(force_refresh=(auth_retried and attempt > 0))
                    headers = {
                        "User-Agent": "antigravity/2.35.0 windows/amd64",
                        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
                        "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}',
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                    async with httpx.AsyncClient(timeout=client_timeout) as client:
                        async with client.stream("POST", url, headers=headers, json=body) as response:
                            if response.status_code in (401, 403) and not auth_retried:
                                cache_key = get_credential_access_token_key(self.credential.id)
                                await redis_client.delete(cache_key)
                                auth_retried = True
                                raise httpx.HTTPStatusError("Auth error", request=response.request, response=response)
                            if response.status_code != 200:
                                body_text = await response.aread()
                                error_text = body_text.decode(errors="replace")
                                if _is_geo_blocked_error(error_text) and geo_retries < _GEO_LOCATION_RETRY_LIMIT:
                                    geo_retries += 1
                                    logger.warning(
                                        "Antigravity geo/location block via endpoint=%s (attempt %s/%s): %s",
                                        GOOGLE_CLOUD_CODE_ENDPOINT,
                                        geo_retries,
                                        _GEO_LOCATION_RETRY_LIMIT,
                                        error_text[:240],
                                    )
                                    await asyncio.sleep(min(0.15 * geo_retries, 0.8))
                                    continue
                                logger.error(
                                    "Antigravity request failed with HTTP %s via endpoint=%s: %s",
                                    response.status_code,
                                    GOOGLE_CLOUD_CODE_ENDPOINT,
                                    error_text[:500],
                                )
                                raise Exception(f"HTTP {response.status_code}: {error_text}")
                            chat_id = f"chatcmpl-{uuid.uuid4()}"
                            created_time = int(time.time())
                            async for line in response.aiter_lines():
                                if not line:
                                    continue
                                if line.startswith("data: "):
                                    data_str = line[6:].strip()
                                    if not data_str:
                                        continue
                                    try:
                                        chunk_json = json.loads(data_str)
                                    except Exception:
                                        continue
                                    response_obj = chunk_json.get("response", {})
                                    candidates = response_obj.get("candidates", [])
                                    text_content = ""

                                    reasoning_content = ""

                                    finish_reason = None

                                    tool_calls = []
                                    chunk_images = []

                                    if candidates:

                                        candidate = candidates[0]

                                        content = candidate.get("content", {})

                                        parts = content.get("parts", [])

                                        for p in parts:

                                            p_text = p.get("text", "")

                                            if p.get("thought") is True:

                                                reasoning_content += p_text

                                            else:

                                                text_content += p_text

                                            if "inlineData" in p:
                                                mime_type = p["inlineData"].get("mimeType", "image/jpeg")
                                                base64_data = p["inlineData"].get("data", "")
                                                if base64_data:
                                                    is_jumb = False
                                                    if base64_data.startswith("anVtY"):
                                                        is_jumb = True
                                                    else:
                                                        try:
                                                            import base64
                                                            header_bytes = base64.b64decode(base64_data[:32])
                                                            if b"jumb" in header_bytes:
                                                                is_jumb = True
                                                        except Exception:
                                                            pass
                                                    
                                                    if not is_jumb:
                                                        text_content += f"\n![Generated Image](data:{mime_type};base64,{base64_data})\n"
                                                        chunk_images.append({
                                                            "type": "image_url",
                                                            "image_url": {
                                                                "url": f"data:{mime_type};base64,{base64_data}"
                                                            },
                                                            "index": len(chunk_images)
                                                        })

                                            if "functionCall" in p:

                                                fn_call = p["functionCall"]

                                                fn_name = fn_call.get("name")

                                                fn_args = fn_call.get("args", {})

                                                fn_id = fn_call.get("id") or f"call_{uuid.uuid4().hex[:8]}"

                                                thought_sig = p.get("thoughtSignature")

                                                if thought_sig:

                                                    await redis_client.set(f"thought_signature:{fn_id}", thought_sig, ex=3600)

                                                tool_calls.append({

                                                    "index": len(tool_calls),

                                                    "id": fn_id,

                                                    "type": "function",

                                                    "function": {

                                                        "name": fn_name,

                                                        "arguments": json.dumps(fn_args, ensure_ascii=False)

                                                    },

                                                    "thought_signature": thought_sig

                                                })

                                        finish_reason = candidate.get("finishReason")

                                        if finish_reason:

                                            finish_reason = finish_reason.lower()

                                        if tool_calls and not finish_reason:

                                            finish_reason = "tool_calls"

                                    usage_meta = response_obj.get("usageMetadata", {})

                                    usage_obj = None

                                    if usage_meta:

                                        prompt_tokens = usage_meta.get("promptTokenCount", 0)

                                        completion_tokens = usage_meta.get("candidatesTokenCount", 0)

                                        from litellm import Usage
                                        
                                        cached_tokens = int(usage_meta.get("cachedContentTokenCount", 0) or 0)
                                        usage_obj = Usage(
                                            prompt_tokens=prompt_tokens,
                                            completion_tokens=completion_tokens,
                                            total_tokens=prompt_tokens + completion_tokens,
                                            prompt_tokens_details={"cached_tokens": cached_tokens} if cached_tokens else None,
                                        )

                                    from litellm.types.utils import ModelResponseStream

                                    delta = {}

                                    if text_content:

                                        delta["content"] = text_content

                                    if reasoning_content:

                                        delta["reasoning_content"] = reasoning_content

                                    if tool_calls:

                                        delta["tool_calls"] = tool_calls

                                    if chunk_images:

                                        delta["images"] = chunk_images
                                    choice = {
                                        "index": 0,
                                        "delta": delta,
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
                            break
                except httpx.HTTPStatusError as status_err:
                    # One token-cache refresh retry for auth challenges only.
                    # Do not mutate credential status here — chat/usage classify
                    # quota vs rate-limit vs auth vs client errors centrally.
                    if status_err.response.status_code in (401, 403) and not auth_retried:
                        cache_key = get_credential_access_token_key(self.credential.id)
                        await redis_client.delete(cache_key)
                        auth_retried = True
                        continue
                    raise status_err
                except Exception as stream_err:
                    err_str = str(stream_err)
                    # Retry once only for the HTTP 401/403 envelopes we raise above.
                    # Broad substring matches like "credentials" must NOT reauth.
                    is_retryable_auth_http = (
                        err_str.startswith("HTTP 401:")
                        or err_str.startswith("HTTP 403:")
                        or err_str.startswith("Auth error")
                    )
                    if is_retryable_auth_http and not auth_retried:
                        cache_key = get_credential_access_token_key(self.credential.id)
                        await redis_client.delete(cache_key)
                        auth_retried = True
                        continue
                    if _is_geo_blocked_error(err_str) and geo_retries < _GEO_LOCATION_RETRY_LIMIT:
                        geo_retries += 1
                        logger.warning(
                            "Antigravity geo/location exception via endpoint=%s (attempt %s/%s): %s",
                            GOOGLE_CLOUD_CODE_ENDPOINT,
                            geo_retries,
                            _GEO_LOCATION_RETRY_LIMIT,
                            err_str[:240],
                        )
                        await asyncio.sleep(min(0.15 * geo_retries, 0.8))
                        continue
                    raise stream_err

        if kwargs.get("stream", False):


            return response_generator()


        else:


            full_text = []


            full_reasoning = []


            all_tool_calls = []


            all_images = []


            final_usage = None


            final_chat_id = None


            final_created = None


            final_finish_reason = "stop"


            


            async for chunk in response_generator():


                choice = chunk.choices[0] if chunk.choices else None


                if choice:


                    if choice.delta.get("content"):


                        full_text.append(choice.delta["content"])


                    if choice.delta.get("reasoning_content"):


                        full_reasoning.append(choice.delta["reasoning_content"])


                    if choice.delta.get("images"):


                        all_images.extend(choice.delta["images"])


                    if choice.delta.get("tool_calls"):


                        for tc in choice.delta["tool_calls"]:


                            existing = next((x for x in all_tool_calls if x["id"] == tc["id"]), None)


                            if not existing:


                                all_tool_calls.append(dict(tc))


                    if choice.finish_reason:


                        final_finish_reason = choice.finish_reason


                if chunk.usage:


                    final_usage = chunk.usage


                if chunk.id:


                    final_chat_id = chunk.id


                if chunk.created:


                    final_created = chunk.created


                    


            from litellm import ModelResponse, Usage


            if not final_usage:


                final_usage = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)


            if not final_chat_id:


                final_chat_id = f"chatcmpl-{uuid.uuid4()}"


            if not final_created:


                final_created = int(time.time())


                


            message_body = {


                "role": "assistant",


                "content": "".join(full_text) if full_text else None


            }


            if all_images:


                message_body["images"] = all_images


            if full_reasoning:


                message_body["reasoning_content"] = "".join(full_reasoning)


            if all_tool_calls:


                message_body["tool_calls"] = all_tool_calls
                
            return ModelResponse(
                id=final_chat_id,
                object="chat.completion",
                created=final_created,
                model=model,
                choices=[
                    {
                        "index": 0,
                        "message": message_body,
                        "finish_reason": final_finish_reason
                    }
                ],
                usage=final_usage
            )

    async def embedding(self, model: str, input_data: Any, **kwargs) -> Any:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=501,
            detail="Embedding API is not supported through Antigravity provider. "
                   "Please add a BYO upstream credential with embedding model support "
                   "(e.g., OpenAI text-embedding-3-small)."
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
            f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:loadCodeAssist",
            headers=headers,
            json={"cloudaicompanionProject": env_project_id}
        )
        if load_resp.status_code == 200:
            load_data = load_resp.json()
            project_id = load_data.get("cloudaicompanionProject")
            if project_id:
                await self._save_project_id(project_id)
                return project_id
        
        # If the first request with env_project_id failed (e.g. 403 Forbidden because this account
        # has no access to the env_project_id), try with empty json to let Google resolve the default project.
        load_resp = await client.post(
            f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:loadCodeAssist",
            headers=headers,
            json={}
        )
        if load_resp.status_code in (401, 403):
            raise Exception(f"Auth error: HTTP {load_resp.status_code}")
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

        onboard_resp = await client.post(
            f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:onboardUser",
            headers=headers,
            json={}
        )
        if onboard_resp.status_code in (401, 403):
            raise Exception(f"Auth error: HTTP {onboard_resp.status_code}")

        for i in range(5):
            await asyncio.sleep(1.0)
            load_resp = await client.post(
                f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:loadCodeAssist",
                headers=headers,
                json={}
            )
            if load_resp.status_code in (401, 403):
                raise Exception(f"Auth error: HTTP {load_resp.status_code}")
            if load_resp.status_code == 200:
                load_data = load_resp.json()
                project_id = load_data.get("cloudaicompanionProject")
                if project_id:
                    await self._save_project_id(project_id)
                    return project_id

        raise Exception("Google Account has no eligible cloudaicompanionProject.")

    async def _save_project_id(self, project_id: str) -> None:
        lock_token = await self._acquire_secret_write_lock()
        try:
            async with AsyncSessionLocal() as db:
                db_credential = await db.get(Credential, self.credential.id)
                encrypted_secret = (
                    db_credential.encrypted_secret if db_credential else self.credential.encrypted_secret
                )
                try:
                    secret_data = decrypt_secret(encrypted_secret)
                    secret_dict = json.loads(secret_data)
                    if not isinstance(secret_dict, dict):
                        secret_dict = {"refresh_token": secret_data}
                except Exception:
                    secret_dict = {"refresh_token": decrypt_secret(encrypted_secret)}

                secret_dict["project_id"] = project_id
                encrypted = encrypt_secret(json.dumps(secret_dict))
                stmt = (
                    update(Credential)
                    .where(Credential.id == self.credential.id)
                    .values(encrypted_secret=encrypted)
                )
                await db.execute(stmt)
                await db.commit()
                self.credential.encrypted_secret = encrypted
        finally:
            await self._release_secret_write_lock(lock_token)

    async def _save_quota_metadata(self, tier: str, load_error: str = None, quota_error: str = None) -> None:
        lock_token = await self._acquire_secret_write_lock()
        try:
            async with AsyncSessionLocal() as db:
                db_credential = await db.get(Credential, self.credential.id)
                encrypted_secret = (
                    db_credential.encrypted_secret if db_credential else self.credential.encrypted_secret
                )
                try:
                    secret_data = decrypt_secret(encrypted_secret)
                    secret_dict = json.loads(secret_data)
                    if not isinstance(secret_dict, dict):
                        secret_dict = {"refresh_token": secret_data}
                except Exception:
                    secret_dict = {"refresh_token": decrypt_secret(encrypted_secret)}

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
                stmt = (
                    update(Credential)
                    .where(Credential.id == self.credential.id)
                    .values(encrypted_secret=encrypted)
                )
                await db.execute(stmt)
                await db.commit()
                self.credential.encrypted_secret = encrypted
        finally:
            await self._release_secret_write_lock(lock_token)

    async def fetch_quota(self, force: bool = False) -> dict:
        # РљСЌС€РёСЂСѓРµРј Р·Р°РїСЂРѕСЃС‹ Рє РєРІРѕС‚Р°Рј Google API РЅР° 15 РјРёРЅСѓС‚, С‡С‚РѕР±С‹ РёР·Р±РµР¶Р°С‚СЊ СЂРµР№С‚-Р»РёРјРёС‚РѕРІ РЅР° IP
        if not force and self.credential.last_check_at:
            now = datetime.now(timezone.utc)
            last_check = self.credential.last_check_at
            if last_check.tzinfo is None:
                last_check = last_check.replace(tzinfo=timezone.utc)
            if now - last_check < timedelta(minutes=15) and self.credential.status in ("active", "exhausted"):
                tier = "unknown"
                load_error = None
                quota_error = None
                try:
                    secret_data = decrypt_secret(self.credential.encrypted_secret)
                    secret_dict = json.loads(secret_data)
                    if isinstance(secret_dict, dict):
                        tier = secret_dict.get("tier", "unknown")
                        load_error = secret_dict.get("load_error")
                        quota_error = secret_dict.get("quota_error")
                except Exception:
                    pass
                
                remaining_fraction = 1.0
                if self.credential.quota_total_tokens and self.credential.quota_used_tokens is not None:
                    remaining_fraction = 1 - (self.credential.quota_used_tokens / self.credential.quota_total_tokens)
                
                return {
                    "tier": tier,
                    "remaining_fraction": remaining_fraction,
                    "quota_total_tokens": self.credential.quota_total_tokens or 1000000,
                    "quota_used_tokens": self.credential.quota_used_tokens or 0,
                    "remaining_pct": round(remaining_fraction * 100, 1),
                    "reset_at": self.credential.reset_at.isoformat() if self.credential.reset_at else None,
                    "model_quotas": self.credential.model_quotas or {},
                    "status": self.credential.status or "active",
                    "load_error": load_error,
                    "quota_error": quota_error,
                    "cached": True
                }

        load_resp = None
        quota_resp = None
        tier = "unknown"
        load_data = {}
        quota_data = {}
        uq_data = None
        for attempt in range(2):
            try:
                access_token = await self.get_access_token(force_refresh=(attempt > 0))
            except Exception as e:
                if attempt == 1 and "invalid_grant" in str(e).lower():
                    await self._mark_reauth_required()
                    return {"error": str(e), "load_error": str(e), "status": "reauth_required"}
                if attempt == 1:
                    async with AsyncSessionLocal() as db:
                        stmt = (
                            update(Credential)
                            .where(
                                Credential.id == self.credential.id,
                                Credential.status.notin_(["reauth_required", "disabled", "exhausted"]),
                            )
                            .values(
                                status="degraded",
                                last_check_at=datetime.now(timezone.utc),
                            )
                        )
                        await db.execute(stmt)
                        await db.commit()
                    await self._save_quota_metadata(tier="unknown", load_error=str(e))
                    return {"error": f"Failed to get access token: {str(e)}", "load_error": str(e), "status": "error"}
                continue
            headers = _antigravity_headers(access_token)
            async with httpx.AsyncClient(timeout=15.0) as client:
                try:
                    project_id = await self._resolve_project_id(client, headers)
                    load_resp = await client.post(
                        f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:loadCodeAssist",
                        headers=headers,
                        json={}
                    )
                    if load_resp.status_code in (401, 403):
                        if attempt == 0:
                            cache_key = get_credential_access_token_key(self.credential.id)
                            await redis_client.delete(cache_key)
                            continue
                        if load_resp.status_code == 401:
                            await self._mark_reauth_required()
                            return {"error": f"Auth error: HTTP {load_resp.status_code}", "status": "reauth_required"}
                        async with AsyncSessionLocal() as db:
                            stmt = (
                                update(Credential)
                                .where(
                                    Credential.id == self.credential.id,
                                    Credential.status.notin_(["reauth_required", "disabled", "exhausted"]),
                                )
                                .values(status="degraded", last_check_at=datetime.now(timezone.utc))
                            )
                            await db.execute(stmt)
                            await db.commit()
                        return {"error": f"Permission error: HTTP {load_resp.status_code}", "status": "degraded"}
                    model_payload = {
                        "project": project_id
                    }
                    quota_resp = await client.post(
                        f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:fetchAvailableModels",
                        headers=headers,
                        json=model_payload
                    )
                    if quota_resp.status_code in (401, 403):
                        if attempt == 0:
                            cache_key = get_credential_access_token_key(self.credential.id)
                            await redis_client.delete(cache_key)
                            continue
                        if quota_resp.status_code == 401:
                            await self._mark_reauth_required()
                            return {"error": f"Auth error: HTTP {quota_resp.status_code}", "status": "reauth_required"}
                        async with AsyncSessionLocal() as db:
                            stmt = (
                                update(Credential)
                                .where(
                                    Credential.id == self.credential.id,
                                    Credential.status.notin_(["reauth_required", "disabled", "exhausted"]),
                                )
                                .values(status="degraded", last_check_at=datetime.now(timezone.utc))
                            )
                            await db.execute(stmt)
                            await db.commit()
                        return {"error": f"Permission error: HTTP {quota_resp.status_code}", "status": "degraded"}
                    try:
                        uq_resp = await client.post(
                            f"{GOOGLE_CLOUD_CODE_ENDPOINT}/v1internal:retrieveUserQuotaSummary",
                            headers=headers,
                            json={}
                        )
                        if uq_resp.status_code == 200:
                            uq_data = uq_resp.json()
                    except Exception as e:
                        logger.warning("Error fetching user quota summary: %s", e)
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    is_retryable_auth = (
                        "http 401" in err_str
                        or "unauthorized" in err_str
                        or err_str.startswith("auth error: http 401")
                        or err_str.startswith("auth error: http 403")
                    )
                    if is_retryable_auth and attempt == 0:
                        cache_key = get_credential_access_token_key(self.credential.id)
                        await redis_client.delete(cache_key)
                        continue
                    if attempt == 1 and "invalid_grant" in err_str:
                        await self._mark_reauth_required()
                        return {"error": str(e), "load_error": str(e), "status": "reauth_required"}
                    if attempt == 1:
                        async with AsyncSessionLocal() as db:
                            stmt = (
                                update(Credential)
                                .where(
                                    Credential.id == self.credential.id,
                                    Credential.status.notin_(["reauth_required", "disabled", "exhausted"]),
                                )
                                .values(
                                    status="degraded",
                                    last_check_at=datetime.now(timezone.utc),
                                )
                            )
                            await db.execute(stmt)
                            await db.commit()
                        await self._save_quota_metadata(tier="unknown", load_error=str(e))
                        return {"error": f"Project resolution failed: {str(e)}", "load_error": str(e), "status": "error"}
                    continue

        load_ok = (load_resp is not None and load_resp.status_code == 200)
        quota_ok = (quota_resp is not None and quota_resp.status_code == 200)

        load_data = load_resp.json() if load_ok else {}
        quota_data = quota_resp.json() if quota_ok else {}

        tier = load_data.get("tier", load_data.get("userTier", "unknown"))

        remaining_fraction = None
        quota_details = {}
        reset_at_val = None

        if quota_ok:
            import re

            def matches_model(name1: str, name2: str) -> bool:
                w1 = set(re.findall(r'[a-z0-9]+', name1.replace(".", "").lower()))
                w2 = set(re.findall(r'[a-z0-9]+', name2.replace(".", "").lower()))
                if not w1 or not w2:
                    return False
                return w1.issubset(w2) or w2.issubset(w1)

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
                    quota_details[m_id] = frac
                    for model in (self.credential.models or []):
                        if matches_model(model, display_name) or matches_model(model, m_id):
                            quota_details[model] = frac

                    if min_fraction is None or frac < min_fraction:
                        min_fraction = frac

            groups = quota_data.get("groups", [])
            for group in groups:
                buckets = group.get("buckets", [])
                for bucket in buckets:
                    display_name = bucket.get("displayName", bucket.get("bucketId", "unknown"))
                    bucket_id = bucket.get("bucketId", "unknown")
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
                    quota_details[bucket_id] = frac
                    for model in (self.credential.models or []):
                        if matches_model(model, display_name) or matches_model(model, bucket_id):
                            quota_details[model] = frac

                    if min_fraction is None or frac < min_fraction:
                        min_fraction = frac

            # РџРѕР»СѓС‡Р°РµРј РґРµС‚Р°Р»СЊРЅС‹Рµ РєРІРѕС‚С‹ (РЅРµРґРµР»СЊРЅС‹Рµ, 5-С‡Р°СЃРѕРІС‹Рµ)
            if uq_data:
                for group in uq_data.get("groups", []):
                    for bucket in group.get("buckets", []):
                        b_id = bucket.get("bucketId")
                        b_frac = bucket.get("remainingFraction")
                        if b_id and b_frac is not None:
                            quota_details[b_id] = float(b_frac)
                            quota_details[f"{b_id}:reset"] = bucket.get("resetTime")
                            if min_fraction is None or float(b_frac) < min_fraction:
                                min_fraction = float(b_frac)

            if earliest_reset:
                reset_at_val = earliest_reset

        # --- Per-group fraction aggregation (credential's own models only) ---
        # Aggregating over EVERY bucket in the API response let a single
        # exhausted model the credential doesn't even serve zero out the
        # whole group and block live models from routing (#1)
        from app.core.constants import get_model_quota_group

        group_fractions: dict[str, float | None] = {"gemini": None, "others": None}

        cred_models = [m for m in (self.credential.models or []) if isinstance(m, str)]
        for model in cred_models:
            frac_val = quota_details.get(model)
            if not isinstance(frac_val, (int, float)):
                continue
            group = get_model_quota_group(model)
            current = group_fractions[group]
            if current is None or float(frac_val) < current:
                group_fractions[group] = float(frac_val)

        # Fallback: none of the credential's models appeared in the API
        # response (e.g. empty models list) - aggregate over everything
        if all(v is None for v in group_fractions.values()):
            for key, frac_val in list(quota_details.items()):
                if key.endswith(":reset") or key.startswith("_group:"):
                    continue
                if not isinstance(frac_val, (int, float)):
                    continue
                group = get_model_quota_group(key)
                current = group_fractions[group]
                if current is None or float(frac_val) < current:
                    group_fractions[group] = float(frac_val)

        # Write synthetic group keys
        for grp, grp_frac in group_fractions.items():
            if grp_frac is not None:
                quota_details[f"_group:{grp}"] = grp_frac

        # Compute overall min_fraction (for display / backward compat)
        known_fracs = [f for f in group_fractions.values() if f is not None]
        if known_fracs:
            min_fraction = min(known_fracs)

        if remaining_fraction is None:
            remaining_fraction = min_fraction if min_fraction is not None else 1.0

        status_val = "active"
        # Set exhausted ONLY when ALL groups are known and explicitly at zero.
        # If any group is unknown (None) or > 0.0, we do not mark as exhausted.
        # Unknown groups must never mark the credential exhausted - the global
        # minimum may come from a model this credential does not serve (#1)
        all_groups_known = all(v is not None for v in group_fractions.values())
        if all_groups_known and all(v <= 0.0 for v in group_fractions.values()):
            status_val = "exhausted"

        existing_status = self.credential.status or "active"

        if existing_status in {"reauth_required", "disabled"}:
            status_val = existing_status
            quota_details = dict(self.credential.model_quotas or quota_details)
        elif existing_status == "cooldown":
            # Cooldown expiry is tracked in Redis; do not treat reset_at as
            # cooldown expiry (#6, N1)
            cooldown_active = await redis_client.get(get_credential_cooldown_key(self.credential.id))
            if cooldown_active:
                status_val = "cooldown"
                quota_details = dict(self.credential.model_quotas or quota_details)
        elif not load_ok or not quota_ok:
            # Probe failure is not quota exhaustion - keep last known quotas for UI
            # and avoid cascading cooldown->exhausted from synthetic zeros.
            status_val = "degraded"
            quota_details = dict(self.credential.model_quotas or {})
            if remaining_fraction is None:
                remaining_fraction = 1.0


        total_tokens = 1_000_000
        used_tokens = int(total_tokens * (1 - remaining_fraction))

        if status_val in {"reauth_required", "disabled"}:
            reset_at_val = None
        elif reset_at_val is None:
            reset_at_val = datetime.now(timezone.utc) + timedelta(hours=24)

        discovered_models = None
        if quota_ok:
            from app.core.constants import build_antigravity_models_from_available
            models_dict = quota_data.get("models") or {}
            if isinstance(models_dict, dict) and models_dict:
                discovered_models = build_antigravity_models_from_available(models_dict.keys())

        update_values = {
            "quota_total_tokens": total_tokens,
            "quota_used_tokens": used_tokens,
            "last_check_at": datetime.now(timezone.utc),
            "reset_at": reset_at_val,
            "model_quotas": quota_details,
            "status": status_val,
        }
        if discovered_models:
            update_values["models"] = discovered_models

        from app.routing.selector import CredentialSelector
        state_token = await CredentialSelector._acquire_credential_state_lock(self.credential.id)
        if state_token:
            try:
                async with AsyncSessionLocal() as db:
                    stmt = (
                        update(Credential)
                        .where(
                            Credential.id == self.credential.id,
                            Credential.status == existing_status,
                        )
                        .values(**update_values)
                    )
                    await db.execute(stmt)
                    await db.commit()
            finally:
                await CredentialSelector._release_credential_state_lock(self.credential.id, state_token)
        else:
            logger.warning("Could not acquire credential state lock while saving quota for %s", self.credential.id)

        if discovered_models:
            self.credential.models = discovered_models
        self.credential.model_quotas = quota_details
        self.credential.status = status_val
        self.credential.quota_total_tokens = total_tokens
        self.credential.quota_used_tokens = used_tokens
        self.credential.reset_at = reset_at_val
        self.credential.last_check_at = update_values["last_check_at"]

        result = {
            "tier": tier,
            "remaining_fraction": remaining_fraction,
            "quota_total_tokens": total_tokens,
            "quota_used_tokens": used_tokens,
            "remaining_pct": round(remaining_fraction * 100, 1),
            "reset_at": reset_at_val.isoformat() if reset_at_val else None,
            "model_quotas": quota_details,
            "status": status_val,
            "models": discovered_models or self.credential.models,
            "raw_load": load_data,
            "raw_quota": quota_data,
        }

        def extract_validation_url(text: str) -> str:
            try:
                data = json.loads(text)
                details = data.get("error", {}).get("details", [])
                for detail in details:
                    if detail.get("reason") == "VALIDATION_REQUIRED" or detail.get("metadata", {}).get("validation_url"):
                        metadata = detail.get("metadata", {})
                        val_url = metadata.get("validation_url")
                        if val_url:
                            return val_url
            except Exception:
                pass
            return None

        if load_resp is not None and load_resp.status_code != 200:
            val_url = extract_validation_url(load_resp.text)
            if val_url:
                result["load_error"] = f"Verify your account to continue: {val_url}"
            else:
                result["load_error"] = f"HTTP {load_resp.status_code}: {load_resp.text[:200]}"
        if quota_resp is not None and quota_resp.status_code != 200:
            val_url = extract_validation_url(quota_resp.text)
            if val_url:
                result["quota_error"] = f"Verify your account to continue: {val_url}"
            else:
                result["quota_error"] = f"HTTP {quota_resp.status_code}: {quota_resp.text[:200]}"

        await self._save_quota_metadata(
            tier=tier,
            load_error=result.get("load_error"),
            quota_error=result.get("quota_error")
        )

        return result

