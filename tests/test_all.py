"""
Tests for UPI Offline Mesh backend.

Run with:
    pytest tests/test_all.py -v
"""
import threading
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.db import Base, Account
from models.schemas import MeshPacket, SendRequest
from crypto.hybrid_crypto import HybridCryptoService
from crypto.key_holder import ServerKeyHolder
from services.bridge_ingestion import BridgeIngestionService
from services.idempotency import IdempotencyService
from services.demo_service import create_packet


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_idempotency():
    """Fresh idempotency cache for every test."""
    IdempotencyService.get().reset()
    yield
    IdempotencyService.get().reset()


@pytest.fixture
def db():
    """In-memory SQLite session seeded with two accounts."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Account(vpa="alice@upi", name="Alice", balance=5000.0))
    session.add(Account(vpa="bob@upi",   name="Bob",   balance=1000.0))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def packet(db) -> MeshPacket:
    req = SendRequest(sender_vpa="alice@upi", receiver_vpa="bob@upi", amount=500.0, pin="1234")
    return create_packet(req)


# ── test 1: encrypt/decrypt round trip ───────────────────────────────────────

def test_encrypt_decrypt_round_trip():
    payload = {
        "sender_vpa": "alice@upi",
        "receiver_vpa": "bob@upi",
        "amount": 250.0,
        "pin_hash": "abc123",
        "nonce": "test-nonce",
        "signed_at": 1_700_000_000_000,
    }
    ct = HybridCryptoService.encrypt(payload)
    assert isinstance(ct, str)
    assert len(ct) > 50

    recovered = HybridCryptoService.decrypt(ct)
    assert recovered["sender_vpa"] == payload["sender_vpa"]
    assert recovered["amount"] == payload["amount"]
    assert recovered["nonce"] == payload["nonce"]


# ── test 2: tampered ciphertext is rejected ───────────────────────────────────

def test_tampered_ciphertext_is_rejected(db, packet):
    import base64
    raw = base64.b64decode(packet.ciphertext)
    # flip a byte deep in the payload
    tampered = bytearray(raw)
    tampered[len(raw) // 2] ^= 0xFF
    tampered_b64 = base64.b64encode(bytes(tampered)).decode()

    tampered_packet = MeshPacket(
        packet_id=packet.packet_id,
        ttl=packet.ttl,
        created_at=packet.created_at,
        ciphertext=tampered_b64,
    )

    resp = BridgeIngestionService.ingest(tampered_packet, db, bridge_node_id="attacker")
    assert resp.outcome == "INVALID", f"Expected INVALID, got {resp.outcome}"


# ── test 3: three bridges, one settlement ────────────────────────────────────

def test_single_packet_delivered_by_three_bridges_settles_exactly_once(db, packet):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Give each thread its own DB session against the same in-memory db
    # We need a file-based SQLite so threads share state
    engine = create_engine("sqlite:///./test_concurrent.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    # Seed fresh accounts
    s = Session()
    # clear any old data
    s.query(Account).delete()
    from models.db import Transaction
    s.query(Transaction).delete()
    s.commit()
    s.add(Account(vpa="alice@upi", name="Alice", balance=5000.0))
    s.add(Account(vpa="bob@upi",   name="Bob",   balance=1000.0))
    s.commit()
    s.close()

    outcomes = []
    lock = threading.Lock()

    def deliver():
        thread_db = Session()
        try:
            resp = BridgeIngestionService.ingest(
                packet=packet,
                db=thread_db,
                bridge_node_id="bridge-concurrent",
            )
            with lock:
                outcomes.append(resp.outcome)
        finally:
            thread_db.close()

    threads = [threading.Thread(target=deliver) for _ in range(3)]
    for t in threads: t.start()
    for t in threads: t.join()

    settled = outcomes.count("SETTLED")
    duped   = outcomes.count("DUPLICATE_DROPPED")

    assert settled == 1, f"Expected exactly 1 SETTLED, got {settled}. outcomes={outcomes}"
    assert duped == 2,   f"Expected exactly 2 DUPLICATE_DROPPED, got {duped}. outcomes={outcomes}"

    # Alice should be debited exactly once
    verify = Session()
    alice = verify.query(Account).filter_by(vpa="alice@upi").first()
    assert alice.balance == 4500.0, f"Alice balance should be 4500, got {alice.balance}"
    verify.close()

    # cleanup
    import os
    try: os.remove("./test_concurrent.db")
    except: pass


# ── test 4: insufficient funds ────────────────────────────────────────────────

def test_insufficient_funds_returns_invalid(db):
    # Bob tries to send more than he has
    req = SendRequest(sender_vpa="bob@upi", receiver_vpa="alice@upi", amount=9999.0, pin="1234")
    pkt = create_packet(req)
    resp = BridgeIngestionService.ingest(pkt, db)
    assert resp.outcome == "INVALID"
    assert "Insufficient" in (resp.reason or "")


# ── test 5: unknown VPA ───────────────────────────────────────────────────────

def test_unknown_receiver_returns_invalid(db):
    from models.schemas import PaymentInstruction
    instruction = PaymentInstruction(
        sender_vpa="alice@upi",
        receiver_vpa="ghost@upi",
        amount=100.0,
        pin_hash="x",
    )
    ct = HybridCryptoService.encrypt(instruction.model_dump())
    pkt = MeshPacket(ciphertext=ct)
    resp = BridgeIngestionService.ingest(pkt, db)
    assert resp.outcome == "INVALID"
