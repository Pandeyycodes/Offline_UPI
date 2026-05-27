import hashlib
from sqlalchemy.orm import Session
from models.db import Account
from models.schemas import PaymentInstruction, MeshPacket, SendRequest
from crypto.hybrid_crypto import HybridCryptoService
from services.mesh_simulator import MeshSimulatorService


SEED_ACCOUNTS = [
    {"vpa": "alice@upi", "name": "Alice Sharma", "balance": 5000.0},
    {"vpa": "bob@upi", "name": "Bob Verma", "balance": 3000.0},
    {"vpa": "charlie@upi", "name": "Charlie Patel", "balance": 2000.0},
    {"vpa": "diana@upi", "name": "Diana Nair", "balance": 8000.0},
]


def seed_accounts(db: Session):
    existing = db.query(Account).count()
    if existing == 0:
        for acc in SEED_ACCOUNTS:
            db.add(Account(**acc))
        db.commit()


def create_packet(req: SendRequest) -> MeshPacket:
    pin_hash = hashlib.sha256(req.pin.encode()).hexdigest()
    instruction = PaymentInstruction(
        sender_vpa=req.sender_vpa,
        receiver_vpa=req.receiver_vpa,
        amount=req.amount,
        pin_hash=pin_hash,
    )
    ciphertext = HybridCryptoService.encrypt(instruction.model_dump())
    return MeshPacket(ciphertext=ciphertext)


def simulate_send(req: SendRequest) -> MeshPacket:
    packet = create_packet(req)
    mesh = MeshSimulatorService.get()
    mesh.inject(packet, target_id="phone-alice")
    return packet
