import time
from sqlalchemy.orm import Session

from crypto.hybrid_crypto import HybridCryptoService
from models.schemas import MeshPacket, IngestResponse
from services.idempotency import IdempotencyService
from services.settlement import SettlementService

MAX_AGE_MS = 86_400_000  # 24 hours


class BridgeIngestionService:

    @staticmethod
    def ingest(
        packet: MeshPacket,
        db: Session,
        bridge_node_id: str = "unknown",
        hop_count: int = 0,
    ) -> IngestResponse:
        idempotency = IdempotencyService.get()

        # Step 1: Hash the ciphertext
        packet_hash = HybridCryptoService.hash_ciphertext(packet.ciphertext)

        # Step 2: Atomic claim — drop duplicates
        if not idempotency.try_claim(packet_hash):
            return IngestResponse(
                outcome="DUPLICATE_DROPPED",
                packet_hash=packet_hash,
                reason="Already seen this packet",
            )

        try:
            # Step 3: Decrypt
            try:
                payload = HybridCryptoService.decrypt(packet.ciphertext)
            except Exception as e:
                idempotency.release(packet_hash)
                return IngestResponse(
                    outcome="INVALID",
                    packet_hash=packet_hash,
                    reason=f"Decryption failed: {str(e)}",
                )

            # Step 4: Freshness check
            signed_at = payload.get("signed_at", 0)
            age_ms = int(time.time() * 1000) - signed_at
            if age_ms > MAX_AGE_MS or age_ms < 0:
                idempotency.release(packet_hash)
                return IngestResponse(
                    outcome="INVALID",
                    packet_hash=packet_hash,
                    reason=f"Stale or future-dated packet (age={age_ms}ms)",
                )

            # Step 5: Settle
            try:
                tx = SettlementService.settle(
                    db=db,
                    sender_vpa=payload["sender_vpa"],
                    receiver_vpa=payload["receiver_vpa"],
                    amount=payload["amount"],
                    packet_hash=packet_hash,
                    bridge_node_id=bridge_node_id,
                    hop_count=hop_count,
                )
                return IngestResponse(
                    outcome="SETTLED",
                    packet_hash=packet_hash,
                    transaction_id=tx.id,
                )
            except ValueError as e:
                idempotency.release(packet_hash)
                return IngestResponse(
                    outcome="INVALID",
                    packet_hash=packet_hash,
                    reason=str(e),
                )

        except Exception as e:
            idempotency.release(packet_hash)
            return IngestResponse(
                outcome="INVALID",
                packet_hash=packet_hash,
                reason=f"Unexpected error: {str(e)}",
            )
