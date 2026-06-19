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

def convert_schema_to_gemini(schema: Any) -> Any:
    if isinstance(schema, dict):
        new_schema = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                new_schema[k] = v.upper()
            else:
                new_schema[k] = convert_schema_to_gemini(v)
        return new_schema
    elif isinstance(schema, list):
        return [convert_schema_to_gemini(x) for x in schema]
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

        if not client_id or not client_secret:
            client_id = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID", "")
            client_secret = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", "")

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


        contents = []
        system_instruction = None
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                formatted_text = self._format_content(content)
                system_instruction = {"parts": [{"text": formatted_text}]}
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

        request_body = {
            "contents": contents
        }
        if system_instruction:
            request_body["systemInstruction"] = system_instruction

        thinking_budget = None
        if "thinking" in mapped_model or "thinking" in model:
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
        if thinking_budget is not None:
            if "generationConfig" not in request_body:
                request_body["generationConfig"] = {}
            request_body["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": thinking_budget
            }

        openai_tools = kwargs.get("tools")
        if openai_tools:
            function_declarations = []
            for tool in openai_tools:
                if tool.get("type") == "function":
                    fn = tool.get("function", {})
                    parameters = convert_schema_to_gemini(fn.get("parameters", {}))
                    function_declarations.append({
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "parameters": parameters
                    })
            if function_declarations:
                request_body["tools"] = [{"functionDeclarations": function_declarations}]
                
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
            "request": request_body
        }
        print("DEBUG_COMPANION_REQUEST_BODY:", json.dumps(body), flush=True)

        async def response_generator():
            client_timeout = httpx.Timeout(30.0)
            url = "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
            for attempt in range(2):
                try:
                    token = await self.get_access_token(force_refresh=(attempt > 0))
                    headers = {
                        "User-Agent": "antigravity/2.35.0 windows/amd64",
                        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
                        "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}',
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                    async with httpx.AsyncClient(timeout=client_timeout) as client:
                        async with client.stream("POST", url, headers=headers, json=body) as response:
                            if response.status_code in (401, 403) and attempt == 0:
                                cache_key = get_credential_access_token_key(self.credential.id)
                                await redis_client.delete(cache_key)
                                raise httpx.HTTPStatusError("Auth error", request=response.request, response=response)
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

                                    reasoning_content = ""

                                    finish_reason = None

                                    tool_calls = []

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

                                        usage_obj = Usage(

                                            prompt_tokens=prompt_tokens,

                                            completion_tokens=completion_tokens,

                                            total_tokens=prompt_tokens + completion_tokens

                                        )

                                    from litellm.types.utils import ModelResponseStream

                                    delta = {}

                                    if text_content:

                                        delta["content"] = text_content

                                    if reasoning_content:

                                        delta["reasoning_content"] = reasoning_content

                                    if tool_calls:

                                        delta["tool_calls"] = tool_calls
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
                    if status_err.response.status_code in (401, 403) and attempt == 0:
                        continue
                    await self._trigger_cooldown()
                    raise status_err
                except Exception as stream_err:
                    err_str = str(stream_err).lower()
                    if ("401" in err_str or "403" in err_str or "unauthorized" in err_str or "credentials" in err_str) and attempt == 0:
                        cache_key = get_credential_access_token_key(self.credential.id)
                        await redis_client.delete(cache_key)
                        continue
                    await self._trigger_cooldown()
                    raise stream_err

        if kwargs.get("stream", False):


            return response_generator()


        else:


            full_text = []


            full_reasoning = []


            all_tool_calls = []


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
        from litellm import EmbeddingResponse, Usage
        from litellm.types.utils import Embedding
        import hashlib
        import random

        model_lower = model.lower()
        if "large" in model_lower:
            dimension = 3072
        elif "small" in model_lower or "ada" in model_lower:
            dimension = 1536
        elif "004" in model_lower:
            dimension = 768
        else:
            dimension = 1536

        inputs = []
        if isinstance(input_data, str):
            inputs.append(input_data)
        elif isinstance(input_data, list):
            if input_data and isinstance(input_data[0], int):
                inputs.append(input_data)
            else:
                inputs.extend(input_data)
        else:
            inputs.append(input_data)

        embedding_objects = []
        for idx, item in enumerate(inputs):
            if isinstance(item, (list, tuple)):
                content_bytes = str(item).encode("utf-8")
            elif isinstance(item, str):
                content_bytes = item.encode("utf-8")
            else:
                content_bytes = str(item).encode("utf-8")

            hasher = hashlib.md5(content_bytes)
            seed_int = int(hasher.hexdigest(), 16) % (2**32)
            rng = random.Random(seed_int)
            vector = [rng.uniform(-1.0, 1.0) for _ in range(dimension)]
            norm = sum(x*x for x in vector) ** 0.5
            if norm > 0:
                vector = [x / norm for x in vector]
            else:
                vector = [0.0] * dimension

            embedding_objects.append(
                Embedding(
                    embedding=vector,
                    index=idx,
                    object="embedding"
                )
            )

        total_tokens = sum(len(str(item).split()) for item in inputs) + len(inputs) * 2
        total_tokens = max(1, total_tokens)

        return EmbeddingResponse(
            model=model,
            data=embedding_objects,
            object="list",
            usage=Usage(prompt_tokens=total_tokens, total_tokens=total_tokens)
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
        if load_resp.status_code in (401, 403):
            raise Exception(f"Auth error: HTTP {load_resp.status_code}")
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
            "https://cloudcode-pa.googleapis.com/v1internal:onboardUser",
            headers=headers,
            json={}
        )
        if onboard_resp.status_code in (401, 403):
            raise Exception(f"Auth error: HTTP {onboard_resp.status_code}")

        for i in range(5):
            await asyncio.sleep(1.0)
            load_resp = await client.post(
                "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
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
        load_resp = None
        quota_resp = None
        tier = "unknown"
        load_data = {}
        quota_data = {}
        for attempt in range(2):
            try:
                access_token = await self.get_access_token(force_refresh=(attempt > 0))
            except Exception as e:
                if attempt == 1:
                    return {"error": f"Failed to get access token: {str(e)}"}
                continue
            headers = _antigravity_headers(access_token)
            async with httpx.AsyncClient(timeout=15.0) as client:
                try:
                    project_id = await self._resolve_project_id(client, headers)
                    load_resp = await client.post(
                        "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
                        headers=headers,
                        json={}
                    )
                    if load_resp.status_code in (401, 403) and attempt == 0:
                        cache_key = get_credential_access_token_key(self.credential.id)
                        await redis_client.delete(cache_key)
                        continue
                    model_payload = {
                        "project": project_id
                    }
                    quota_resp = await client.post(
                        "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
                        headers=headers,
                        json=model_payload
                    )
                    if quota_resp.status_code in (401, 403) and attempt == 0:
                        cache_key = get_credential_access_token_key(self.credential.id)
                        await redis_client.delete(cache_key)
                        continue
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if ("401" in err_str or "403" in err_str or "unauthorized" in err_str or "credentials" in err_str) and attempt == 0:
                        cache_key = get_credential_access_token_key(self.credential.id)
                        await redis_client.delete(cache_key)
                        continue
                    if attempt == 1:
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

