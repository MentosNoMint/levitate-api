import hashlib
import re
from typing import Dict, Iterable, List, Set

# Bootstrap catalog used only until the first successful
# fetchAvailableModels() sync. Prefer upstream Antigravity IDs
# (same style as CLIProxyAPI models.json) plus our legacy aliases.
DEFAULT_ANTIGRAVITY_MODELS = [
    # Canonical logical IDs
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-pro",
    "gemini-3-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-image",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "gpt-oss-120b",
    # Legacy and upstream wire IDs
    "gemini-3.8-flash-tiered",
    "gemini-3.7-flash-tiered",
    "gemini-3.6-flash-high",
    "gemini-3.6-flash-tiered",
    "gemini-3.5-flash-medium",
    "gemini-3.5-flash-low",
    "gemini-3.5-flash-high",
    "gemini-3.5-flash-extra-low",
    "gemini-3-flash-agent",
    "gemini-3.1-pro-low",
    "gemini-3.1-pro-high",
    "gemini-pro-agent",
    "claude-opus-4-6-thinking",
    "claude-sonnet-4-6-thinking",
    "gpt-oss-120b-medium",
]

# Upstream models that are internal or broken on the daily endpoint
ANTIGRAVITY_DISCOVERY_DENYLIST = {
    "chat_20706",
    "chat_23310",
    "gemini-2.5-pro",
}

REVISION_FLASH_PATTERN = re.compile(
    r"^gemini-((?:[3-9]|\d{2,})(?:\.\d+)?)-flash(?:-(low|medium|high|tiered))?$",
    re.IGNORECASE,
)

# Client/public alias -> upstream Antigravity model id used in API requests.
# Identity entries keep exact upstream IDs routable.
ANTIGRAVITY_MODEL_ALIASES: Dict[str, str] = {
    # Claude
    "Claude Sonnet 4.6 (Thinking)": "claude-sonnet-4-6",
    "Claude Opus 4.6 (Thinking)": "claude-opus-4-6-thinking",
    "claude-sonnet-4.6-thinking": "claude-sonnet-4-6",
    "claude-sonnet-4-6-thinking": "claude-sonnet-4-6",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4.6-thinking": "claude-opus-4-6-thinking",
    "claude-opus-4-6-thinking": "claude-opus-4-6-thinking",
    "claude-opus-4.6": "claude-opus-4-6-thinking",
    "claude-opus-4-6": "claude-opus-4-6-thinking",
    "claude-4.6-sonnet": "claude-sonnet-4-6",
    "claude-4.6-opus-thinking": "claude-opus-4-6-thinking",
    # Gemini display names (Antigravity UI)
    "Gemini 3.8 Flash": "gemini-3.8-flash-tiered",
    "Gemini 3.7 Flash": "gemini-3.7-flash-tiered",
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
    # Canonical logical model aliases
    "gemini-3.8-flash": "gemini-3.8-flash-tiered",
    "gemini-3.8-flash-tiered": "gemini-3.8-flash-tiered",
    "gemini-3.7-flash": "gemini-3.7-flash-tiered",
    "gemini-3.7-flash-tiered": "gemini-3.7-flash-tiered",
    "gemini-3.6-flash": "gemini-3.6-flash-high",
    "gemini-3.6-flash-tiered": "gemini-3.6-flash-tiered",
    "gemini-3.5-flash": "gemini-3.5-flash-low",
    "gemini-3.1-pro": "gemini-3.1-pro-low",
    "gpt-oss-120b": "gpt-oss-120b-medium",
    # Legacy public aliases we historically exposed via /v1/models
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


def resolve_antigravity_upstream_model(model_name: str, effort: str | None = None) -> str:
    """Map a client/public model name and optional reasoning effort to the upstream Antigravity wire ID."""
    if not model_name:
        return model_name

    raw = model_name.strip()
    lower = raw.lower()
    effort_norm = effort.strip().lower() if isinstance(effort, str) and effort.strip() else None

    # Exact alias check when no effort override is specified
    if not effort_norm:
        if raw in ANTIGRAVITY_MODEL_ALIASES:
            return ANTIGRAVITY_MODEL_ALIASES[raw]
        if lower in ANTIGRAVITY_MODEL_ALIASES:
            return ANTIGRAVITY_MODEL_ALIASES[lower]

    # Check dynamic gemini-{rev}-flash pattern
    flash_match = REVISION_FLASH_PATTERN.match(raw)
    if flash_match:
        rev = flash_match.group(1)
        sub_tier = flash_match.group(2)
        # If client explicitly asked for a specific wire SKU without effort override, keep it
        if sub_tier and not effort_norm:
            return raw

        rev_parts = [int(x) for x in rev.split(".") if x.isdigit()]
        # For Gemini 3.6:
        if rev_parts == [3, 6]:
            if effort_norm in ("high", "xhigh", "max"):
                return "gemini-3.6-flash-high"
            if effort_norm == "medium":
                return "gemini-3.6-flash-medium"
            if effort_norm in ("low", "minimal"):
                return "gemini-3.6-flash-low"
            return "gemini-3.6-flash-high"

        # For Gemini 3.7, 3.8 and future revisions (>= 3.7):
        return f"gemini-{rev}-flash-tiered"

    # Static family resolution with effort
    if lower in ("gemini-3.5-flash", "gemini-3.5-flash-medium", "gemini-3.5-flash-high", "gemini-3.5-flash-low", "gemini-3.5-flash-extra-low"):
        if effort_norm in ("high", "xhigh", "max"):
            return "gemini-3-flash-agent"
        if effort_norm == "medium":
            return "gemini-3.5-flash-low"
        if effort_norm in ("low", "minimal", "off"):
            return "gemini-3.5-flash-extra-low"

    if lower in ("gemini-3.1-pro", "gemini-3.1-pro-low", "gemini-3.1-pro-high", "gemini-pro-agent"):
        if effort_norm in ("high", "xhigh", "max"):
            return "gemini-pro-agent"
        if effort_norm in ("low", "minimal", "off"):
            return "gemini-3.1-pro-low"

    if lower in (
        "claude-opus-4-6",
        "claude-opus-4.6",
        "claude-opus-4-6-thinking",
        "claude-opus-4.6-thinking",
        "claude-4.6-opus-thinking",
    ):
        return "claude-opus-4-6-thinking"

    if lower in (
        "claude-sonnet-4-6",
        "claude-sonnet-4.6",
        "claude-sonnet-4-6-thinking",
        "claude-sonnet-4.6-thinking",
        "claude-4.6-sonnet",
    ):
        return "claude-sonnet-4-6"

    if lower in ("gpt-oss-120b", "gpt-oss-120b-medium"):
        return "gpt-oss-120b-medium"

    if raw in ANTIGRAVITY_MODEL_ALIASES:
        return ANTIGRAVITY_MODEL_ALIASES[raw]

    for alias, upstream in ANTIGRAVITY_MODEL_ALIASES.items():
        if alias.lower() == lower:
            return upstream

    return raw


def is_public_antigravity_model(model_id: str) -> bool:
    """Whether an upstream model id should appear in the public picker /v1/models.

    Antigravity's fetchAvailableModels also returns IDE-internal buckets such as
    ``chat_20706`` / ``tab_flash_lite_preview``. Those are not usable chat models
    (streamGenerateContent returns INVALID_ARGUMENT) and must stay out of the UI.
    """
    if not isinstance(model_id, str):
        return False
    name = model_id.strip()
    if not name:
        return False
    lower = name.lower()
    if lower in ANTIGRAVITY_DISCOVERY_DENYLIST:
        return False
    if lower.startswith(("chat_", "tab_")):
        return False
    return True


def build_antigravity_models_from_available(available_ids: Iterable[str]) -> List[str]:
    """Build the public Credential.models list from fetchAvailableModels keys.

    Includes upstream IDs plus dynamic collapsed canonical models and known aliases,
    so legacy clients keep working while new models appear automatically.
    Filters IDE-internal chat_/tab_ buckets out of the public catalog.
    """
    available: Set[str] = {
        m for m in available_ids if isinstance(m, str) and m.strip() and is_public_antigravity_model(m)
    }
    if not available:
        return list(DEFAULT_ANTIGRAVITY_MODELS)

    available_lower = {m.lower(): m for m in available}
    public: List[str] = []
    seen: Set[str] = set()

    def _add(name: str) -> None:
        if not is_public_antigravity_model(name):
            return
        key = name.lower()
        if key in seen:
            return
        seen.add(key)
        public.append(name)

    # 1. First, collapse numbered gemini flash variants (>= 3.6) into logical models
    flash_revs: Set[str] = set()
    for m in available:
        match = REVISION_FLASH_PATTERN.match(m)
        if match:
            flash_revs.add(match.group(1))

    for rev in sorted(
        flash_revs,
        key=lambda r: [int(x) for x in r.split(".") if x.isdigit()],
        reverse=True,
    ):
        logical_flash = f"gemini-{rev}-flash"
        _add(logical_flash)

    # 2. Collapse other known families into canonical logical models
    # gemini-3.5-flash
    g35 = {
        "gemini-3.5-flash-extra-low",
        "gemini-3.5-flash-low",
        "gemini-3.5-flash-medium",
        "gemini-3.5-flash-high",
        "gemini-3-flash-agent",
        "gemini-3.5-flash",
    }
    if any(m.lower() in available_lower for m in g35):
        _add("gemini-3.5-flash")

    # gemini-3.1-pro
    g31 = {
        "gemini-3.1-pro-low",
        "gemini-3.1-pro-high",
        "gemini-pro-agent",
        "gemini-3.1-pro",
    }
    if any(m.lower() in available_lower for m in g31):
        _add("gemini-3.1-pro")

    # Claude 4.6
    if "claude-sonnet-4-6" in available_lower or "claude-sonnet-4-6-thinking" in available_lower:
        _add("claude-sonnet-4-6")
        _add("claude-sonnet-4.6")
    if "claude-opus-4-6-thinking" in available_lower or "claude-opus-4-6" in available_lower:
        _add("claude-opus-4-6")
        _add("claude-opus-4.6")

    # GPT-OSS 120B
    if "gpt-oss-120b-medium" in available_lower or "gpt-oss-120b" in available_lower:
        _add("gpt-oss-120b")

    # 3. Add upstream available models (sorted)
    for upstream in sorted(available):
        _add(upstream)

    # 4. Add aliases (excluding display names with spaces)
    for alias, upstream in ANTIGRAVITY_MODEL_ALIASES.items():
        if " " in alias:
            continue
        if (
            upstream in available
            or upstream.lower() in available_lower
            or alias.lower() in available_lower
        ):
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

    # Map dotted / canonical aliases for Claude, GPT, and versioned nicknames
    if m in ("claude-opus-4.6", "claude-opus-4-6"):
        return "claude-opus-4-6-thinking"
    if m in ("claude-sonnet-4.6", "claude-sonnet-4-6"):
        return "claude-sonnet-4-6"
    if m == "gpt-oss-120b":
        return "gpt-oss-120b-medium"
    if m in ("gemini-3.7", "gemini-3.7-flash"):
        return "gemini-3.7-flash"
    if m in ("gemini-3.8", "gemini-3.8-flash"):
        return "gemini-3.8-flash"
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
        if "3.7" in m:
            return "gemini-3.7-flash"
        if "3.8" in m:
            return "gemini-3.8-flash"
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
