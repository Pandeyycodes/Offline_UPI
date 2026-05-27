from pydantic import BaseModel
from typing import Optional
import uuid
import time

class PaymentInstruction(BaseModel):
    sender_vpa: str
    receiver_vpa: str
    amount: float
    pin_hash: str
    nonce: str = ""
    signed_at: int = 0

    def __init__(self, **data):
        if not data.get("nonce"):
            data["nonce"] = str(uuid.uuid4())
        if not data.get("signed_at"):
            data["signed_at"] = int(time.time() * 1000)
        super().__init__(**data)

class MeshPacket(BaseModel):
    packet_id: str = ""
    ttl: int = 5
    created_at: int = 0
    ciphertext: str  # base64-encoded

    def __init__(self, **data):
        if not data.get("packet_id"):
            data["packet_id"] = str(uuid.uuid4())
        if not data.get("created_at"):
            data["created_at"] = int(time.time() * 1000)
        super().__init__(**data)

class IngestResponse(BaseModel):
    outcome: str  # SETTLED | DUPLICATE_DROPPED | INVALID
    packet_hash: str
    reason: Optional[str] = None
    transaction_id: Optional[int] = None

class SendRequest(BaseModel):
    sender_vpa: str
    receiver_vpa: str
    amount: float
    pin: str
