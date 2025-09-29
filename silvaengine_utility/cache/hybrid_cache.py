#!/usr/bin/env python3
"""
Hybrid Cache Engine - Redis Primary with Disk Fallback

Provides robust caching for AWS Lambda environments with automatic failover
from Redis to local disk storage when Redis is unavailable.
"""

import hashlib
import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import redis
    from redis import Redis as RedisType

    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    RedisType = Any
    REDIS_AVAILABLE = False


class HybridCacheEngine:
    """Hybrid cache that prefers Redis with a disk-based fallback."""

    _instances: Dict[str, "HybridCacheEngine"] = {}

    def __new__(cls, cache_name: str = "default") -> "HybridCacheEngine":
        if cache_name not in cls._instances:
            cls._instances[cache_name] = super().__new__(cls)
            cls._instances[cache_name]._initialized = False
        return cls._instances[cache_name]

    def __init__(self, cache_name: str = "default") -> None:
        if getattr(self, "_initialized", False):
            return

        self.cache_name = cache_name
        self.logger = logging.getLogger(f"HybridCache.{cache_name}")
        self._redis_client: Optional[RedisType] = None
        self._redis_available = False
        self._disk_cache_dir: Optional[Path] = None

        self._setup_disk_cache()
        self._setup_redis()
        self._initialized = True

    # Redis helpers -----------------------------------------------------

    def _setup_redis(self) -> None:
        """Attempt to connect to Redis using environment configuration."""
        if not REDIS_AVAILABLE:
            self._redis_client = None
            self._redis_available = False
            self.logger.debug(
                "Redis module not available, using disk-only cache for %s",
                self.cache_name,
            )
            return

        try:
            redis_config = {
                "host": os.environ.get("REDIS_HOST", "localhost"),
                "port": int(os.environ.get("REDIS_PORT", 6379)),
                "db": int(
                    os.environ.get(
                        f"REDIS_DB_{self.cache_name.upper()}",
                        os.environ.get("REDIS_DB", 0),
                    )
                ),
                "socket_connect_timeout": 1,
                "socket_timeout": 1,
                "retry_on_timeout": True,
                "health_check_interval": 30,
                "max_connections": 10,
                "decode_responses": False,
            }

            if os.environ.get("REDIS_PASSWORD"):
                redis_config["password"] = os.environ.get("REDIS_PASSWORD")

            self._redis_client = redis.Redis(**redis_config)  # type: ignore[assignment]
            self._redis_client.ping()
            self._redis_available = True
            self.logger.debug("Redis connected for cache: %s", self.cache_name)
        except Exception as exc:  # pragma: no cover - external dependency
            self._redis_client = None
            self._redis_available = False
            self.logger.warning("Redis unavailable for %s: %s", self.cache_name, exc)

    def _ensure_redis(self) -> None:
        """Ensure Redis is ready before using it."""
        if self._redis_available and self._redis_client:
            return
        self._setup_redis()

    # Disk helpers ------------------------------------------------------

    def _setup_disk_cache(self) -> None:
        """Prepare disk cache directory."""
        import platform
        import tempfile

        if os.environ.get("CACHE_DIR"):
            base_dir = os.environ.get("CACHE_DIR")
        elif platform.system() == "Windows":
            base_dir = os.path.join(tempfile.gettempdir(), "silvaengine_cache")
        else:
            base_dir = "/tmp/silvaengine_cache"

        self._disk_cache_dir = Path(base_dir) / self.cache_name

        try:
            self._disk_cache_dir.mkdir(parents=True, exist_ok=True)
            test_file = self._disk_cache_dir / ".test"
            test_file.touch()
            test_file.unlink()
            self.logger.debug("Disk cache ready: %s", self._disk_cache_dir)
        except Exception as exc:  # pragma: no cover - depends on environment
            self.logger.error(
                "Disk cache setup failed for %s: %s", self.cache_name, exc
            )
            self._disk_cache_dir = None

    def _generate_key(self, prefix: str, key_data: Any) -> str:
        """Generate consistent, collision-resistant cache key."""
        if isinstance(key_data, str):
            key_str = key_data
        else:
            key_str = json.dumps(key_data, sort_keys=True, default=str)

        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:16]
        return f"{self.cache_name}:{prefix}:{key_hash}"

    def _get_disk_path(self, key: str) -> Optional[Path]:
        if not self._disk_cache_dir:
            return None
        safe_filename = f"{key.replace(':', '_')}.cache"
        return self._disk_cache_dir / safe_filename

    def _load_disk_record(self, file_path: Path) -> Optional[Dict[str, Any]]:
        if not file_path.exists():
            return None

        try:
            with file_path.open("rb") as handle:
                record = pickle.load(handle)
        except Exception as exc:
            self.logger.debug("Disk cache read error (%s): %s", file_path.name, exc)
            return None

        if isinstance(record, dict) and "expires_at" in record and "value" in record:
            return record

        self._safe_remove(file_path)
        return None

    def _write_disk_record(
        self, file_path: Path, value: Any, expires_at: float
    ) -> bool:
        try:
            with file_path.open("wb") as handle:
                pickle.dump({"expires_at": expires_at, "value": value}, handle)
            return True
        except Exception as exc:  # pragma: no cover - disk specific
            self.logger.warning(
                "Disk cache write error for %s: %s", file_path.name, exc
            )
            return False

    def _safe_remove(self, file_path: Path) -> bool:
        try:
            file_path.unlink()
            return True
        except FileNotFoundError:
            return False
        except Exception as exc:  # pragma: no cover - disk specific
            self.logger.debug("Disk cache delete error (%s): %s", file_path.name, exc)
            return False

    # Public API --------------------------------------------------------

    def get(self, key: str, ttl: int = 300) -> Optional[Any]:
        cache_key = self._generate_key("cache", key)

        self._ensure_redis()
        if self._redis_available and self._redis_client:
            try:
                data = self._redis_client.get(cache_key)
                if data is not None:
                    return pickle.loads(data)
            except Exception as exc:
                self.logger.warning("Redis get error for %s: %s", cache_key, exc)
                self._redis_available = False

        disk_path = self._get_disk_path(cache_key)
        if not disk_path:
            return None

        record = self._load_disk_record(disk_path)
        if not record:
            self._safe_remove(disk_path)
            return None

        if record["expires_at"] <= time.time():
            self._safe_remove(disk_path)
            return None

        return record["value"]

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        cache_key = self._generate_key("cache", key)

        self._ensure_redis()
        if self._redis_available and self._redis_client:
            try:
                data = pickle.dumps(value)
                self._redis_client.setex(cache_key, ttl, data)
                return True
            except Exception as exc:
                self.logger.warning("Redis set error for %s: %s", cache_key, exc)
                self._redis_available = False

        disk_path = self._get_disk_path(cache_key)
        if not disk_path:
            return False

        now = time.time()
        self.clear_expired(now=now)
        return self._write_disk_record(disk_path, value, now + ttl)

    def delete(self, key: str) -> bool:
        cache_key = self._generate_key("cache", key)
        success = False

        self._ensure_redis()
        if self._redis_available and self._redis_client:
            try:
                success |= bool(self._redis_client.delete(cache_key))
            except Exception as exc:
                self.logger.debug("Redis delete error for %s: %s", cache_key, exc)

        disk_path = self._get_disk_path(cache_key)
        if disk_path:
            success |= self._safe_remove(disk_path)

        return success

    def clear_expired(
        self,
        now: Optional[float] = None,
    ) -> int:
        if not self._disk_cache_dir:
            return 0

        current_time = now or time.time()
        removed = 0

        for file_path in self._disk_cache_dir.glob("*.cache"):
            record = self._load_disk_record(file_path)
            if not record or record.get("expires_at", 0) <= current_time:
                removed += int(self._safe_remove(file_path))

        return removed

    def clear(self, pattern: str = "*") -> int:
        count = 0

        self._ensure_redis()
        if self._redis_available and self._redis_client:
            try:
                keys_pattern = f"{self.cache_name}:{pattern}"
                keys = list(self._redis_client.scan_iter(match=keys_pattern))
                if keys:
                    count += self._redis_client.delete(*keys)
            except Exception as exc:
                self.logger.debug("Redis clear error for pattern %s: %s", pattern, exc)

        if self._disk_cache_dir:
            disk_pattern = f"{self.cache_name}:{pattern}".replace(":", "_")
            for file_path in self._disk_cache_dir.glob(f"{disk_pattern}.cache"):
                count += int(self._safe_remove(file_path))

        return count

    def stats(self) -> Dict[str, Any]:
        return {
            "cache_name": self.cache_name,
            "redis_available": self._redis_available,
            "disk_available": self._disk_cache_dir is not None,
            "disk_path": str(self._disk_cache_dir) if self._disk_cache_dir else None,
        }


# Default cache instance
default_cache = HybridCacheEngine()
