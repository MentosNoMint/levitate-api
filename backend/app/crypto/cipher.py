import os
import base64
from cryptography.fernet import Fernet

app_env = os.getenv("APP_ENV", "development").lower()
_key = os.getenv("ENCRYPTION_KEY")

if app_env == "production":
    if not _key or _key == "vwW6pdYns-N3IpM4slyoaCUl8hwdY01EizkJvvyytz8=":
        raise RuntimeError("ENCRYPTION_KEY must be securely configured in production mode!")
else:
    if not _key:
        _key = base64.urlsafe_b64encode(b"01234567890123456789012345678901")

if isinstance(_key, str):
    try:
        base64.urlsafe_b64decode(_key)
    except Exception:
        _key = base64.urlsafe_b64encode(_key.encode().ljust(32)[:32])

cipher = Fernet(_key)

def encrypt_secret(secret: str) -> str:
    return cipher.encrypt(secret.encode()).decode()

def decrypt_secret(encrypted: str) -> str:
    return cipher.decrypt(encrypted.encode()).decode()
