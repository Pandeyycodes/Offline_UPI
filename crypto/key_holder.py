from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import base64

class ServerKeyHolder:
    _instance = None

    def __init__(self):
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._public_key = self._private_key.public_key()

    @classmethod
    def get(cls) -> "ServerKeyHolder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def private_key(self):
        return self._private_key

    @property
    def public_key(self):
        return self._public_key

    def public_key_b64(self) -> str:
        pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return base64.b64encode(pem).decode()
