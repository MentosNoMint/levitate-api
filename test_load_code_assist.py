import sqlite3
import json
import os
import time
import httpx

# Load env variables
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

def decrypt(encrypted: str) -> str:
    return cipher.decrypt(encrypted.encode()).decode()

conn = sqlite3.connect("backend/dev.db")
cursor = conn.cursor()
cursor.execute("SELECT encrypted_secret FROM credentials WHERE type = 'antigravity'")
row = cursor.fetchone()
conn.close()

if not row:
    print("No antigravity credential found in DB.")
    exit(1)

secret_data = decrypt(row[0])
try:
    config = json.loads(secret_data)
    refresh_token = config.get("refresh_token")
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
except Exception:
    refresh_token = secret_data
    client_id = None
    client_secret = None

# If client_id/client_secret not in db, default to Antigravity IDE values
if not client_id or not client_secret:
    client_id = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("ANTIGRAVITY_OAUTH_CLIENT_SECRET", "")

payload = {
    "grant_type": "refresh_token",
    "refresh_token": refresh_token,
}
if client_id and client_secret:
    payload["client_id"] = client_id
    payload["client_secret"] = client_secret

def _antigravity_headers(token: str) -> dict:
    return {
        "User-Agent": "antigravity/1.15.8 windows/amd64",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": '{"ideType":"ANTIGRAVITY","platform":"PLATFORM_UNSPECIFIED","pluginType":"GEMINI"}',
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

with httpx.Client(timeout=15.0) as client:
    resp = client.post("https://oauth2.googleapis.com/token", data=payload)
    resp.raise_for_status()
    access_token = resp.json()["access_token"]
    
    headers = _antigravity_headers(access_token)

    print("--- 1. loadCodeAssist ---")
    response = client.post(
        "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
        headers=headers,
        json={}
    )
    print("Status:", response.status_code)
    print("Body:", response.text)
    
    project_id = None
    if response.status_code == 200:
        project_id = response.json().get("cloudaicompanionProject")
        
    if not project_id:
        print("\n--- 2. onboardUser ---")
        onboard_resp = client.post(
            "https://cloudcode-pa.googleapis.com/v1internal:onboardUser",
            headers=headers,
            json={}
        )
        print("onboardUser Status:", onboard_resp.status_code)
        print("onboardUser Body:", onboard_resp.text)
        
        # Poll loadCodeAssist
        print("\nPolling loadCodeAssist...")
        for i in range(5):
            time.sleep(1.0)
            response = client.post(
                "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
                headers=headers,
                json={}
            )
            if response.status_code == 200:
                project_id = response.json().get("cloudaicompanionProject")
                if project_id:
                    print(f"Found cloudaicompanionProject: {project_id} at poll {i+1}")
                    break
        
    if not project_id:
        print("Failed to resolve project ID!")
        exit(1)

    print(f"\nUsing Project ID: {project_id}")
    
    print("\n--- 3. fetchAvailableModels ---")
    model_payload = {
        "cloudaicompanionProject": project_id
    }
    response2 = client.post(
        "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
        headers=headers,
        json=model_payload
    )
    print("Status:", response2.status_code)
    print("Body:", response2.text)
