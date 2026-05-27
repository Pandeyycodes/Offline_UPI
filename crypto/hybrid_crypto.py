import os
import json
import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from crypto.key_holder import ServerKeyHolder

class HybridCryptoService:

    @staticmethod
    def encrypt(payload: dict) -> str:
        """Encrypt a dict payload. Returns base64 ciphertext."""
        key_holder = ServerKeyHolder.get()

        # 1. Generate fresh AES-256 key + nonce
        aes_key = os.urandom(32)
        nonce = os.urandom(12)

        # 2. AES-GCM encrypt the payload
        aesgcm = AESGCM(aes_key)
        plaintext = json.dumps(payload).encode()
        ct = aesgcm.encrypt(nonce, plaintext, None)

        # 3. RSA-OAEP encrypt the AES key
        enc_aes_key = key_holder.public_key.encrypt(
            aes_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        # 4. Pack everything: [enc_key_len(4)] + [enc_key] + [nonce(12)] + [ct]
        packed = (
            len(enc_aes_key).to_bytes(4, "big")
            + enc_aes_key
            + nonce
            + ct
        )
        return base64.b64encode(packed).decode()

    @staticmethod
    def decrypt(ciphertext_b64: str) -> dict:
        """Decrypt base64 ciphertext. Returns the original dict."""
        key_holder = ServerKeyHolder.get()
        packed = base64.b64decode(ciphertext_b64)

        # Unpack
        key_len = int.from_bytes(packed[:4], "big")
        enc_aes_key = packed[4: 4 + key_len]
        nonce = packed[4 + key_len: 4 + key_len + 12]
        ct = packed[4 + key_len + 12:]

        # Decrypt AES key
        aes_key = key_holder.private_key.decrypt(
            enc_aes_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        # Decrypt payload
        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(nonce, ct, None)
        return json.loads(plaintext.decode())

    @staticmethod
    def hash_ciphertext(ciphertext_b64: str) -> str:
        """SHA-256 of the raw ciphertext bytes."""
        raw = base64.b64decode(ciphertext_b64)
        return hashlib.sha256(raw).hexdigest()
