import hashlib
import re
from typing import Dict, Iterable, List, Set

# Bootstrap catalog used only until the first successful
# fetchAvailableModels() sync. Prefer upstream Antigravity IDs
# (same style as CLIProxyAPI models.json) plus our legacy aliases.
DEFAULT_ANTIGRAVITY_MODELS = [
    "gemini-3.6-flash-high",
    "gemini-3.1-flash-image",
    "gemini-3.5-flash-medium",
    "gemini-3.5-flash-low",
    "gemini-3.5-flash-high",
    "gemini-3.5-flash-extra-low",
    "gemini-3-flash-agent",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-low",
    "gemini-3-flash",
    "gemini-3.1-pro-high",
    "gemini-pro-agent",
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6-thinking",
    "claude-sonnet-4-6",
    "gpt-oss-120b-medium",
]

# Client/public alias -> upstream Antigravity model id used in API requests.
# Identity entries keep exact upstream IDs routable.
ANTIGRAVITY_MODEL_ALIASES: Dict[str, str] = {
    # Claude
    "Claude Sonnet 4.6 (Thinking)": "claude-sonnet-4-6",
    "Claude Opus 4.6 (Thinking)": "claude-opus-4-6-thinking",
    "claude-sonnet-4.6-thinking": "claude-sonnet-4-6",
    "claude-sonnet-4-6-thinking": "claude-sonnet-4-6",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4.6-thinking": "claude-opus-4-6-thinking",
    "claude-opus-4-6-thinking": "claude-opus-4-6-thinking",
    "claude-4.6-sonnet": "claude-sonnet-4-6",
    "claude-4.6-opus-thinking": "claude-opus-4-6-thinking",
    # Gemini display names (Antigravity UI)
    "Gemini 3.6 Flash": "gemini-3.6-flash-high",
    "Gemini 3.6 Flash (High)": "gemini-3.6-flash-high",
    "Gemini 3.5 Flash (Low)": "gemini-3.5-flash-extra-low",
    "Gemini 3.5 Flash (Medium)": "gemini-3.5-flash-low",
    "Gemini 3.5 Flash (High)": "gemini-3-flash-agent",
    "Gemini 3.1 Pro (Low)": "gemini-3.1-pro-low",
    "Gemini 3.1 Pro (High)": "gemini-pro-agent",
    "Gemini 3.1 Flash Lite": "gemini-3.1-flash-lite",
    "Gemini 3.1 Flash Image": "gemini-3.1-flash-image",
    "Gemini 3 Flash": "gemini-3-flash",
    "GPT-OSS 120B (Medium)": "gpt-oss-120b-medium",
    # Legacy public aliases we historically exposed via /v1/models
    "gemini-3.6-flash": "gemini-3.6-flash-high",
    "gemini-3.6-flash-high": "gemini-3.6-flash-high",
    "gemini-3.5-flash-medium": "gemini-3.5-flash-extra-low",
    "gemini-3.5-flash-low": "gemini-3.5-flash-low",
    "gemini-3.5-flash-high": "gemini-3-flash-agent",
    "gemini-3.5-flash-extra-low": "gemini-3.5-flash-extra-low",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3-flash": "gemini-3-flash",
    "gemini-3.1-flash-image": "gemini-3.1-flash-image",
    "gemini-3.1-pro-low": "gemini-3.1-pro-low",
    "gemini-3.1-pro-high": "gemini-pro-agent",
    "gemini-3.1-pro-low-high": "gemini-pro-agent",
    "gemini-3-flash-agent": "gemini-3-flash-agent",
    "gemini-pro-agent": "gemini-pro-agent",
    "gpt-oss-120b-medium": "gpt-oss-120b-medium",
}

REDIS_KEY_VKEY_RPM = "gateway:vkey:{vkey_id}:rpm"
REDIS_KEY_VKEY_TOKENS = "gateway:vkey:{vkey_id}:tokens_used"
REDIS_KEY_CREDENTIAL_ACCESS_TOKEN = "gateway:credential:{credential_id}:access_token"
REDIS_KEY_CREDENTIAL_TOKENS = "gateway:credential:{credential_id}:tokens_used"
REDIS_KEY_CREDENTIAL_CONCURRENCY = "gateway:credential:{credential_id}:concurrency"
REDIS_KEY_LOCK_CREDENTIAL = "gateway:lock:credential:{credential_id}"
REDIS_KEY_CREDENTIAL_COOLDOWN = "gateway:credential:{credential_id}:cooldown"
SESSION_BINDING_TTL_SECONDS = 24 * 60 * 60
SESSION_BINDING_LOCK_TTL_SECONDS = 15
CONVERSATION_TIP_TTL_SECONDS = SESSION_BINDING_TTL_SECONDS

_VERSIONED_MODEL_RE = re.compile(r"(gemini|claude|gpt).*\d", re.IGNORECASE)


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


def get_credential_cooldown_key(credential_id) -> str:
    """Ephemeral cooldown marker. Lives only in Redis (with TTL) so a 429
    never overwrites the credential's quota-window reset_at in the DB."""
    return REDIS_KEY_CREDENTIAL_COOLDOWN.format(credential_id=credential_id)


def _binding_part(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def get_session_binding_key(provider: str, user_id, session_id: str, model_name: str) -> str:
    """Return a non-sensitive, namespaced account binding key.

    Shape: gateway:session_binding:{provider}:{user_id}:{sha256(session)}:{sha256(model)}.
    Session comes from X-Session-ID / body session_id / tip-hash sticky fallback.
    """
    return (
        f"gateway:session_binding:{provider}:{user_id}:"
        f"{_binding_part(session_id)}:{_binding_part(model_name.lower())}"
    )


def get_session_binding_lock_key(user_id, session_id: str, model_name: str) -> str:
    """Serialize first-bind and failover decisions for one conversation."""
    return (
        f"gateway:session_binding_lock:{user_id}:"
        f"{_binding_part(session_id)}:{_binding_part(model_name.lower())}"
    )


def resolve_antigravity_upstream_model(model_name: str) -> str:
    """Map a client/public model name to the upstream Antigravity model id."""
    if not model_name:
        return model_name
    if model_name in ANTIGRAVITY_MODEL_ALIASES:
        return ANTIGRAVITY_MODEL_ALIASES[model_name]
    lower = model_name.lower()
    for alias, upstream in ANTIGRAVITY_MODEL_ALIASES.items():
        if alias.lower() == lower:
            return upstream
    return model_name


def build_antigravity_models_from_available(available_ids: Iterable[str]) -> List[str]:
    """Build the public Credential.models list from fetchAvailableModels keys.

    Includes upstream IDs plus any known aliases that resolve into that set,
    so legacy clients keep working while new models appear automatically.
    """
    available: Set[str] = {m for m in available_ids if isinstance(m, str) and m.strip()}
    if not available:
        return list(DEFAULT_ANTIGRAVITY_MODELS)

    available_lower = {m.lower(): m for m in available}
    public: List[str] = []
    seen: Set[str] = set()

    def _add(name: str) -> None:
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        public.append(name)

    for upstream in sorted(available):
        _add(upstream)

    for alias, upstream in ANTIGRAVITY_MODEL_ALIASES.items():
        # Skip display-name style aliases with spaces from /v1/models catalog
        if " " in alias:
            continue
        if upstream in available or upstream.lower() in available_lower or alias.lower() in available_lower:
            _add(alias)

    return public


def map_model_name(model_name: str) -> str:
    """Normalize a client model request for credential matching.

    Exact/versioned IDs pass through. Only generic nicknames are fuzzy-mapped,
    so gemini-3.6-* is never collapsed into gemini-3.5-*.
    """
    if not model_name:
        return model_name

    raw = model_name.strip()
    m = raw.lower()

    if "embedding" in m or m.startswith("text-embedding"):
        return "text-embedding-3-small"

    # Exact known alias / upstream id
    for alias, upstream in ANTIGRAVITY_MODEL_ALIASES.items():
        if alias.lower() == m:
            return alias
        if upstream.lower() == m:
            return upstream

    # Concrete versioned IDs: never fuzzy-remap
    if _VERSIONED_MODEL_RE.search(m):
        return raw

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
        if "3.6" in m:
            return "gemini-3.6-flash-high"
        if "medium" in m or "extra-low" in m or "extra_low" in m:
            return "gemini-3.5-flash-medium"
        if "high" in m or "agent" in m:
            return "gemini-3.5-flash-high"
        return "gemini-3.5-flash-low"
    if "gpt-4" in m or "gpt-4o" in m:
        return "claude-sonnet-4-6-thinking"
    if "gpt-3" in m:
        return "gemini-3.5-flash-low"
    return raw


def get_model_quota_group(model_name: str) -> str:
    """Classify a model into its quota group: 'gemini' or 'others'."""
    if not model_name:
        return "others"
    m = model_name.lower()
    if m.startswith("gemini") or "gemini" in m:
        return "gemini"
    # Claude, GPT-OSS, and everything else falls into "others"
    return "others"
