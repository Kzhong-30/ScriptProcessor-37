
import time
import threading
from app.config import settings


class ModelCache:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = {}
                    cls._instance._cache_lock = threading.Lock()
        return cls._instance

    def get(self, key):
        with self._cache_lock:
            if key not in self._cache:
                return None
            value, expire_at = self._cache[key]
            if expire_at is not None and time.time() > expire_at:
                del self._cache[key]
                return None
            return value

    def set(self, key, value, ttl=None):
        if ttl is None:
            ttl = settings.CACHE_TTL_SECONDS
        expire_at = time.time() + ttl if ttl > 0 else None
        with self._cache_lock:
            self._cache[key] = (value, expire_at)

    def invalidate(self, key):
        with self._cache_lock:
            self._cache.pop(key, None)

    def invalidate_all(self):
        with self._cache_lock:
            self._cache.clear()


cache = ModelCache()
