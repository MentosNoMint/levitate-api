from enum import Enum
import re


class UpstreamErrorKind(str, Enum):
    QUOTA = "quota"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    TRANSIENT = "transient"
    CLIENT = "client"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


def _status_code(error: Exception) -> int | None:
    for name in ("status_code", "status"):
        value = getattr(error, name, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _error_text(error: Exception) -> str:
    parts = [str(error)]
    response = getattr(error, "response", None)
    response_text = getattr(response, "text", None)
    if response_text:
        parts.append(str(response_text))
    return " ".join(parts).lower()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _contains_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])", text) is not None


def classify_upstream_error_kind(error: Exception) -> UpstreamErrorKind:
    text = _error_text(error)
    status_code = _status_code(error)

    # Durable OAuth / credential revocation only. Generic 401/403 are handled
    # after quota and client checks so RESOURCE_EXHAUSTED-on-403 is not reauth.
    hard_auth_markers = (
        "invalid_grant",
        "refresh token",
        "token has been expired or revoked",
        "token revoked",
        "revoked refresh",
        "unauthorized_client",
    )
    if _contains_any(text, hard_auth_markers):
        return UpstreamErrorKind.AUTH

    hard_quota_markers = (
        "resource_exhausted",
        "resource exhausted",
        "quota_exhausted",
        "quota exhausted",
        "quota_exceeded",
        "quota exceeded",
        "insufficient_quota",
        "billing",
        "per day",
        "per-day",
        "per_day",
        "daily limit",
        "daily",
        "capacity exhausted",
        "capacity_exceeded",
        "capacity exceeded",
        "no capacity",
    )
    rate_markers = (
        "rate limit",
        "rate-limit",
        "rate_limit",
        "too many requests",
        "per minute",
        "per-minute",
        "per_minute",
        "rpm",
    )
    quota_context = (
        "quota",
        "capacity",
        "resource_exhausted",
        "resource exhausted",
        "billing",
    )

    negated_quota = (
        "not exhausted" in text
        or "not exceeded" in text
        or "isn't exhausted" in text
        or "is not exhausted" in text
    )
    if not negated_quota and (
        _contains_any(text, hard_quota_markers)
        or (
            _contains_any(text, quota_context)
            and not _contains_any(text, rate_markers)
            and (_contains_word(text, "exceeded") or _contains_word(text, "exhausted"))
        )
        # Bare "quota" without a rate-limit context (e.g. OpenAI "You exceeded
        # your current quota") is a hard quota error, not a transient rate
        # limit. Callers guarantee a future reset_at for window-less
        # credentials, so parking as exhausted is recoverable (#14, N2)
        or ("quota" in text and not _contains_any(text, rate_markers))
    ):
        return UpstreamErrorKind.QUOTA

    # Generic 429/rate-limit responses are temporary. A 429 containing a hard
    # quota marker was handled above and must not be put on a short cooldown.
    if (
        status_code == 429
        or _contains_any(text, rate_markers)
        or "http 429" in text
        or re.search(r"(?<![0-9])429(?![0-9])", text) is not None
    ):
        return UpstreamErrorKind.RATE_LIMIT

    # Geo blocks from Google (FAILED_PRECONDITION) are often intermittent when
    # egressing via Cloudflare Worker colo IPs. Treat as transient so the
    # gateway can retry / rotate without marking the account reauth/exhausted.
    geo_markers = (
        "user location is not supported",
        "not available in your country",
        "user_location",
        "location is not supported",
    )
    if _contains_any(text, geo_markers) or (
        "failed_precondition" in text and "location" in text
    ):
        return UpstreamErrorKind.TRANSIENT

    client_markers = (
        "unsupported model",
        "invalid model",
        "model not found",
        "invalid request",
        "invalid_argument",
        "invalid argument",
        "bad request",
        "schema",
        "malformed",
        "client disconnected",
        "client disconnect",
        "connection closed",
        "broken pipe",
        "cancelled by client",
        "canceled by client",
        "no image was generated",
        "failed to parse",
        "json_schema",
        "tool call",
        "function call",
    )
    if status_code in {400, 404, 405, 413, 415, 422} or _contains_any(text, client_markers):
        return UpstreamErrorKind.CLIENT

    # Keep CONFIGURATION as an alias of CLIENT for older call sites/tests.
    if _contains_any(text, ("configuration error", "misconfigured")):
        return UpstreamErrorKind.CONFIGURATION

    if status_code in {408, 425, 500, 502, 503, 504} or _contains_any(
        text,
        (
            "timeout",
            "timed out",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
            "temporary failure",
            "network error",
            "server error",
            "internal error",
            "unavailable",
        ),
    ):
        return UpstreamErrorKind.TRANSIENT

    # Clear unauthorized after quota/client filters. Bare 403 without quota
    # markers is usually model/permission denial for this request, not reauth.
    if status_code == 401 or _contains_any(
        text,
        ("http 401", "unauthorized", "unauthenticated", "www-authenticate"),
    ):
        return UpstreamErrorKind.AUTH

    if status_code == 403 or "http 403" in text or "permission denied" in text or "forbidden" in text:
        return UpstreamErrorKind.CLIENT

    return UpstreamErrorKind.UNKNOWN


def classify_upstream_error(error: Exception) -> tuple[bool, bool]:
    """Backward-compatible (is_rate_limit, is_quota) classification."""
    kind = classify_upstream_error_kind(error)
    return kind == UpstreamErrorKind.RATE_LIMIT, kind == UpstreamErrorKind.QUOTA


def should_mutate_credential_status(kind: UpstreamErrorKind) -> bool:
    """Whether this failure may change durable credential status."""
    return kind in {
        UpstreamErrorKind.QUOTA,
        UpstreamErrorKind.RATE_LIMIT,
        UpstreamErrorKind.AUTH,
        UpstreamErrorKind.TRANSIENT,
    }


def should_invalidate_session_binding(kind: UpstreamErrorKind) -> bool:
    """Drop sticky binding only for true failover cases.

    CLIENT / CONFIGURATION / UNKNOWN / TRANSIENT keep the dialogue→account
    sticky mapping so a bad payload or blip does not reshuffle accounts.
    """
    return kind in {
        UpstreamErrorKind.QUOTA,
        UpstreamErrorKind.RATE_LIMIT,
        UpstreamErrorKind.AUTH,
    }
