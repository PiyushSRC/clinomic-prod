from cryptography.fernet import Fernet
from app.core.config import settings

class CryptoManager:
    def __init__(self):
        # In a real app, this key should come from a secure secret store
        # and be rotated. distinct from JWT secret.
        # reusing SECRET_KEY for demo/scaffold if distinct master key unset
        key = settings.SECRET_KEY 
        # Fernet requires 32 url-safe base64-encoded bytes. 
        # We'll just generate one if not provided or handle it safely.
        # For this scaffold, we assume SECRET_KEY is valid base64 or we pad it.
        # To avoid "ValueError: Fernet key must be 32 url-safe base64-encoded bytes":
        try:
           self.fernet = Fernet(key)
        except Exception:
           # Fallback for dev/scaffold - DANGEROUS in PROD
           # Generate a temporary valid key if the config one is bad (just to make app run)
           # In Prod, this should start with a Raise.
           if settings.APP_ENV == "dev":
               self.fernet = Fernet(Fernet.generate_key())
           else:
               raise ValueError("Invalid encryption key for Production")

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self.fernet.decrypt(token.encode()).decode()

crypto = CryptoManager()
