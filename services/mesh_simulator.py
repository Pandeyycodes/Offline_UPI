import threading
from typing import Optional
from models.schemas import MeshPacket


class VirtualDevice:
    def __init__(self, device_id: str, has_internet: bool = False):
        self.device_id = device_id
        self.has_internet = has_internet
        self._packets: dict[str, MeshPacket] = {}
        self._lock = threading.Lock()

    def receive(self, packet: MeshPacket):
        with self._lock:
            if packet.packet_id not in self._packets and packet.ttl > 0:
                self._packets[packet.packet_id] = packet

    def get_packets(self) -> list[MeshPacket]:
        with self._lock:
            return list(self._packets.values())

    def clear(self):
        with self._lock:
            self._packets.clear()

    def packet_count(self) -> int:
        with self._lock:
            return len(self._packets)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "has_internet": self.has_internet,
            "packet_count": self.packet_count(),
            "packet_ids": [p.packet_id for p in self.get_packets()],
        }


class MeshSimulatorService:
    _instance: Optional["MeshSimulatorService"] = None

    def __init__(self):
        self._devices: list[VirtualDevice] = [
            VirtualDevice("phone-alice"),
            VirtualDevice("phone-bob"),
            VirtualDevice("phone-charlie"),
            VirtualDevice("phone-diana"),
            VirtualDevice("phone-bridge", has_internet=True),
        ]

    @classmethod
    def get(cls) -> "MeshSimulatorService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_device(self, device_id: str) -> Optional[VirtualDevice]:
        for d in self._devices:
            if d.device_id == device_id:
                return d
        return None

    def inject(self, packet: MeshPacket, target_id: str = "phone-alice"):
        device = self.get_device(target_id)
        if device:
            device.receive(packet)

    def gossip_round(self):
        """Each device broadcasts all its packets to every other device (TTL-1)."""
        # Snapshot current state
        snapshot: dict[str, list[MeshPacket]] = {}
        for device in self._devices:
            snapshot[device.device_id] = device.get_packets()

        for sender_id, packets in snapshot.items():
            for packet in packets:
                if packet.ttl <= 1:
                    continue
                hopped = MeshPacket(
                    packet_id=packet.packet_id,
                    ttl=packet.ttl - 1,
                    created_at=packet.created_at,
                    ciphertext=packet.ciphertext,
                )
                for device in self._devices:
                    if device.device_id != sender_id:
                        device.receive(hopped)

    def get_bridge_devices(self) -> list[VirtualDevice]:
        return [d for d in self._devices if d.has_internet]

    def state(self) -> list[dict]:
        return [d.to_dict() for d in self._devices]

    def reset(self):
        for device in self._devices:
            device.clear()
