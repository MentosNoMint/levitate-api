def classify_upstream_error(error: Exception) -> tuple[bool, bool]:
    """
    Analyzes an upstream error and returns (is_rate_limit, is_quota).
    
    Args:
        error: The exception raised during the API call.
        
    Returns:
        A tuple of two booleans: (is_rate_limit, is_quota).
    """
    err_str = str(error).lower()
    is_rate_limit = False
    is_quota = False
    
    if "billing" in err_str or "exhausted" in err_str or "per day" in err_str or "daily" in err_str or "per-day" in err_str:
        is_quota = True
    elif hasattr(error, "status_code") and error.status_code == 429:
        is_rate_limit = True
    elif "429" in err_str or "rate limit" in err_str or "too many requests" in err_str or "per minute" in err_str or "quota" in err_str:
        is_rate_limit = True
            
    return is_rate_limit, is_quota
