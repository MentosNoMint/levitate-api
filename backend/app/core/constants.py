DEFAULT_ANTIGRAVITY_MODELS = [
    "gemini-3.1-flash-image",
    "gemini-3.5-flash-extra-low",
    "gemini-3.5-flash-low",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-low-high",
    "gemini-3-flash-agent",
    "gemini-3-flash",
    "gemini-pro-agent",
    "claude-4.6-opus-thinking",
    "claude-4.6-sonnet"
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
