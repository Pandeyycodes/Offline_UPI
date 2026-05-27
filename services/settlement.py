from sqlalchemy.orm import Session
from sqlalchemy import select
from models.db import Account, Transaction
from datetime import datetime


class SettlementService:

    @staticmethod
    def settle(
        db: Session,
        sender_vpa: str,
        receiver_vpa: str,
        amount: float,
        packet_hash: str,
        bridge_node_id: str = None,
        hop_count: int = None,
    ) -> Transaction:
        """
        Debit sender, credit receiver, write ledger row — all in one transaction.
        Raises ValueError on insufficient funds or unknown VPA.
        """
        sender = db.execute(select(Account).where(Account.vpa == sender_vpa)).scalar_one_or_none()
        receiver = db.execute(select(Account).where(Account.vpa == receiver_vpa)).scalar_one_or_none()

        if sender is None:
            raise ValueError(f"Unknown sender VPA: {sender_vpa}")
        if receiver is None:
            raise ValueError(f"Unknown receiver VPA: {receiver_vpa}")
        if sender.balance < amount:
            raise ValueError(f"Insufficient funds: {sender.balance:.2f} < {amount:.2f}")

        sender.balance -= amount
        sender.version += 1

        receiver.balance += amount
        receiver.version += 1

        tx = Transaction(
            packet_hash=packet_hash,
            sender_vpa=sender_vpa,
            receiver_vpa=receiver_vpa,
            amount=amount,
            settled_at=datetime.utcnow(),
            bridge_node_id=bridge_node_id,
            hop_count=hop_count,
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return tx
