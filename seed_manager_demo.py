import sqlite3
import json
import uuid
import os
from datetime import datetime, timezone, timedelta

env_vars = {}
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env_vars[k] = v
                os.environ[k] = v

import base64
from cryptography.fernet import Fernet

key = os.getenv("ENCRYPTION_KEY")
if not key:
    key = base64.urlsafe_b64encode(b"01234567890123456789012345678901")
else:
    try:
        base64.urlsafe_b64decode(key)
    except Exception:
        key = base64.urlsafe_b64encode(key.encode().ljust(32)[:32])

cipher = Fernet(key)

def encrypt(secret: str) -> str:
    return cipher.encrypt(secret.encode()).decode()

conn = sqlite3.connect("backend/dev.db")
cursor = conn.cursor()

now = datetime.now(timezone.utc)

gemini_models = [
    "Gemini 3.1 Flash Image",
    "Gemini 3.5 Flash Extra Low",
    "Gemini 3.5 Flash Low",
    "Gemini 3.1 Flash Lite",
    "Gemini 3.1 Pro (Low/High)",
    "Gemini 3 Flash Agent",
    "Gemini 3 Flash",
    "Gemini Pro Agent"
]
gemini_reset = now + timedelta(hours=3, minutes=9)

cursor.execute("""
    UPDATE credentials 
    SET models = ?, 
        quota_total_tokens = ?, 
        quota_used_tokens = ?, 
        quota_window = ?, 
        reset_at = ? 
    WHERE provider = 'Gemini'
""", (
    json.dumps(gemini_models),
    1000000,
    850000,
    11340,
    gemini_reset.isoformat()
))

claude_models = [
    "Claude 4.6 Opus (Thinking)",
    "Claude 4.6 Sonnet"
]
claude_secret = json.dumps({"api_key": "sk-ant-12345"})
encrypted_claude = encrypt(claude_secret)
claude_reset = now + timedelta(hours=4, minutes=55)

cursor.execute("SELECT id FROM credentials WHERE provider = 'Anthropic'")
row = cursor.fetchone()
if row:
    cursor.execute("""
        UPDATE credentials 
        SET models = ?, 
            quota_total_tokens = ?, 
            quota_used_tokens = ?, 
            quota_window = ?, 
            reset_at = ? 
        WHERE provider = 'Anthropic'
    """, (
        json.dumps(claude_models),
        1000000,
        0,
        17700,
        claude_reset.isoformat()
    ))
else:
    claude_id = uuid.uuid4().hex
    cursor.execute("""
        INSERT INTO credentials (
            id, type, name, provider, encrypted_secret, base_url, models, 
            quota_total_tokens, quota_used_tokens, quota_window, reset_at, 
            rpm_limit, concurrency_limit, priority, weight, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        claude_id,
        "byo_upstream",
        "Anthropic Claude (byo)",
        "Anthropic",
        encrypted_claude,
        None,
        json.dumps(claude_models),
        1000000,
        0,
        17700,
        claude_reset.isoformat(),
        None,
        20,
        1,
        5,
        "active"
    ))

conn.commit()
conn.close()
print("Database successfully seeded.")
