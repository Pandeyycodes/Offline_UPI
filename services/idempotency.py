import threading
import time

class IdempotencyService:
    _instance = None

    def __init__(self):
        self._cache: dict[str, float] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = 86400  # 24 hours

    @classmethod
    def get(cls) -> "IdempotencyService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def try_claim(self, packet_hash: str) -> bool:
        """
        Atomically claim a hash. Returns True if THIS caller claimed it first.
        Returns False if already claimed (duplicate).
        """
        with self._lock:
            self._evict_expired()
            if packet_hash in self._cache:
                return False
            self._cache[packet_hash] = time.time()
            return True

    def release(self, packet_hash: str):
        """Release a claim (called on downstream failure so it can be retried)."""
        with self._lock:
            self._cache.pop(packet_hash, None)

    def reset(self):
        with self._lock:
            self._cache.clear()

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, v in self._cache.items() if now - v > self._ttl_seconds]
        for k in expired:
            del self._cache[k]

    def size(self) -> int:
        with self._lock:
            return len(self._cache)
