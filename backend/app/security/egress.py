import socket
import asyncio
import ipaddress
from urllib.parse import urlparse
from typing import List, Dict, Any

async def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        
        loop = asyncio.get_running_loop()
        addr_info = await loop.getaddrinfo(hostname, None)
        
        for info in addr_info:
            ip_str = info[4][0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip_str == "169.254.169.254"
            ):
                return False
        return True
    except Exception:
        return False

def sanitize_headers(credential_headers: Dict[str, str]) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    for k, v in credential_headers.items():
        headers[k.lower()] = v
    return headers

import re

SECRET_PATTERNS = [
    # OpenAI API Keys
    re.compile(r"\bsk-[a-zA-Z0-9]{48}\b"),
    re.compile(r"\bsk-[a-zA-Z0-9]{20,60}\b"),
    # Anthropic (Claude) API Keys
    re.compile(r"\bsk-ant-[a-zA-Z0-9-_]{40,150}\b"),
    # Google API Keys
    re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"),
    # GitHub Personal Access Tokens
    re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"),
    re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{36,255}\b"),
    # Slack Tokens
    re.compile(r"\bxox[pboar]-[0-9a-zA-Z-]{10,150}\b"),
    # Private Keys (RSA, SSH, etc.)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
]

def scan_for_regex_leaks(body: str) -> bool:
    if not body:
        return False
    for pattern in SECRET_PATTERNS:
        if pattern.search(body):
            return True
    return False

def scan_for_leak(headers: Dict[str, str], body: str, secrets: List[str]) -> bool:
    for secret in secrets:
        if not secret or len(secret) < 6:
            continue
        if secret in body:
            return True
        for val in headers.values():
            if secret in val:
                return True
    return False
