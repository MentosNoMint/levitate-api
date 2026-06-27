DEFAULT_ANTIGRAVITY_MODELS = [
    "gemini-3.1-flash-image",
    "gemini-3.5-flash-medium",
    "gemini-3.5-flash-low",
    "gemini-3.5-flash-high",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-low",
    "gemini-3-flash",
    "gemini-3.1-pro-high",
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6-thinking",
    "gpt-oss-120b-medium"
]

REDIS_KEY_VKEY_RPM = "gateway:vkey:{vkey_id}:rpm"
REDIS_KEY_VKEY_TOKENS = "gateway:vkey:{vkey_id}:tokens_used"
REDIS_KEY_CREDENTIAL_ACCESS_TOKEN = "gateway:credential:{credential_id}:access_token"
REDIS_KEY_CREDENTIAL_TOKENS = "gateway:credential:{credential_id}:tokens_used"
REDIS_KEY_CREDENTIAL_CONCURRENCY = "gateway:credential:{credential_id}:concurrency"
REDIS_KEY_LOCK_CREDENTIAL = "gateway:lock:credential:{credential_id}"

def get_vkey_rpm_key(vkey_id) -> str:
    return REDIS_KEY_VKEY_RPM.format(vkey_id=vkey_id)

def get_vkey_tokens_key(vkey_id) -> str:
    return REDIS_KEY_VKEY_TOKENS.format(vkey_id=vkey_id)

def get_credential_access_token_key(credential_id) -> str:
    return REDIS_KEY_CREDENTIAL_ACCESS_TOKEN.format(credential_id=credential_id)

def get_credential_tokens_key(credential_id) -> str:
    return REDIS_KEY_CREDENTIAL_TOKENS.format(credential_id=credential_id)

def get_credential_concurrency_key(credential_id) -> str:
    return REDIS_KEY_CREDENTIAL_CONCURRENCY.format(credential_id=credential_id)

def get_lock_credential_key(credential_id) -> str:
    return REDIS_KEY_LOCK_CREDENTIAL.format(credential_id=credential_id)

def map_model_name(model_name: str) -> str:
    if not model_name:
        return model_name
    m = model_name.lower()
    if "embedding" in m or m.startswith("text-embedding"):
        return "text-embedding-3-small"
    if "sonnet" in m:
        return "claude-sonnet-4-6-thinking"
    if "opus" in m:
        return "claude-opus-4-6-thinking"
    if "gpt-oss" in m or "gpt_oss" in m:
        return "gpt-oss-120b-medium"
    if "pro" in m:
        if "high" in m or "agent" in m:
            return "gemini-3.1-pro-high"
        return "gemini-3.1-pro-low"
    if "flash" in m:
        if "medium" in m or "extra-low" in m or "extra_low" in m:
            return "gemini-3.5-flash-medium"
        if "high" in m or "agent" in m:
            return "gemini-3.5-flash-high"
        return "gemini-3.5-flash-low"
    if "gpt-4" in m or "gpt-4o" in m:
        return "claude-sonnet-4-6-thinking"
    if "gpt-3" in m:
        return "gemini-3.5-flash-low"
    return model_name

def get_model_quota_group(model_name: str) -> str:
    """Classify a model into its quota group: 'gemini' or 'others'."""
    if not model_name:
        return "others"
    m = model_name.lower()
    if m.startswith("gemini") or "gemini" in m:
        return "gemini"
    # Claude, GPT-OSS, and everything else falls into "others"
    return "others"

