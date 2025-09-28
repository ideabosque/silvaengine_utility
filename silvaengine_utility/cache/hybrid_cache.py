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
from typing import Any, Dict, Optional, Union

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False


class HybridCacheEngine:
    """Generic hybrid cache with Redis primary and disk fallback."""

    _instances: Dict[str, "HybridCacheEngine"] = {}

    def __new__(cls, cache_name: str = "default") -> "HybridCacheEngine":
        if cache_name not in cls._instances:
            cls._instances[cache_name] = super().__new__(cls)
            cls._instances[cache_name]._initialized = False
        return cls._instances[cache_name]

    def __init__(self, cache_name: str = "default"):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.cache_name = cache_name
        self.logger = logging.getLogger(f"HybridCache.{cache_name}")
        self._redis_client: Optional[redis.Redis] = None
        self._redis_available = False
        self._disk_cache_dir: Optional[Path] = None

        if self._redis_client:
            self._setup_redis()
        else:
            self._setup_disk_cache()
        self._initialized = True

    def _setup_redis(self):
        """Initialize Redis with connection pooling and health checks."""
        if not REDIS_AVAILABLE:
            self._redis_available = False
            self.logger.info(
                f"Redis module not available, using disk-only cache for {self.cache_name}"
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

            # Add password if provided
            if os.environ.get("REDIS_PASSWORD"):
                redis_config["password"] = os.environ.get("REDIS_PASSWORD")

            self._redis_client = redis.Redis(**redis_config)
            self._redis_client.ping()
            self._redis_available = True
            self.logger.debug(f"Redis connected for cache: {self.cache_name}")

        except Exception as e:
            self._redis_available = False
            self.logger.warning(f"Redis unavailable for {self.cache_name}: {e}")

    def _setup_disk_cache(self):
        """Setup disk cache with proper permissions."""
        # Use platform-appropriate temporary directory
        import platform
        import tempfile

        if os.environ.get("CACHE_DIR"):
            base_dir = os.environ.get("CACHE_DIR")
        elif platform.system() == "Windows":
            # On Windows, use TEMP directory
            base_dir = os.path.join(tempfile.gettempdir(), "silvaengine_cache")
        else:
            # On Unix-like systems, use /tmp
            base_dir = "/tmp/silvaengine_cache"

        self._disk_cache_dir = Path(base_dir) / self.cache_name

        try:
            self._disk_cache_dir.mkdir(parents=True, exist_ok=True)
            # Test write permissions
            test_file = self._disk_cache_dir / ".test"
            test_file.touch()
            test_file.unlink()
            self.logger.debug(f"Disk cache ready: {self._disk_cache_dir}")
        except Exception as e:
            self.logger.error(f"Disk cache setup failed for {self.cache_name}: {e}")
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
        """Get safe disk cache file path."""
        if not self._disk_cache_dir:
            return None

        # Cache keys are already short and safe, use them directly as filenames
        # Replace colons with underscores for filesystem compatibility
        safe_filename = f"{key.replace(':', '_')}.cache"
        return self._disk_cache_dir / safe_filename

    def _is_disk_expired(self, file_path: Path, ttl: int) -> bool:
        """Check if disk cache file is expired."""
        if not file_path.exists():
            return True
        file_age = time.time() - file_path.stat().st_mtime
        return file_age > ttl

    def get(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get value from cache (Redis first, disk fallback)."""
        cache_key = self._generate_key("cache", key)

        # Try Redis first
        if self._redis_available:
            try:
                data = self._redis_client.get(cache_key)
                if data:
                    return pickle.loads(data)
            except Exception as e:
                self.logger.warning(f"Redis get error: {e}")
                self._redis_available = False

        # Fallback to disk
        disk_path = self._get_disk_path(cache_key)
        if disk_path and not self._is_disk_expired(disk_path, ttl):
            try:
                with open(disk_path, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                self.logger.debug(f"Disk cache read error: {e}")

        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache (Redis primary, disk fallback)."""
        cache_key = self._generate_key("cache", key)

        # Try Redis first
        if self._redis_available:
            try:
                data = pickle.dumps(value)
                self._redis_client.setex(cache_key, ttl, data)
                return True
            except Exception as e:
                self.logger.warning(f"Redis set error: {e}")
                self._redis_available = False

        # Fallback to disk cache only if Redis failed
        # Clean expired cache entries when using disk storage
        self.clear_expired(ttl)

        disk_path = self._get_disk_path(cache_key)
        if disk_path:
            try:
                with open(disk_path, "wb") as f:
                    pickle.dump(value, f)
                return True
            except Exception as e:
                self.logger.warning(f"Disk cache write error: {e}")

        return False

    def delete(self, key: str) -> bool:
        """Delete from both caches."""
        cache_key = self._generate_key("cache", key)
        success = False

        # Delete from Redis
        if self._redis_available:
            try:
                success |= bool(self._redis_client.delete(cache_key))
            except Exception:
                pass

        # Delete from disk
        disk_path = self._get_disk_path(cache_key)
        if disk_path and disk_path.exists():
            try:
                disk_path.unlink()
                success = True
            except Exception:
                pass

        return success

    def clear_expired(self, ttl: int = 300) -> int:
        """Clear expired cache entries from disk storage."""
        count = 0

        if not self._disk_cache_dir:
            return count

        try:
            for file_path in self._disk_cache_dir.glob("*.cache"):
                if self._is_disk_expired(file_path, ttl):
                    file_path.unlink()
                    count += 1
        except Exception as e:
            self.logger.debug(f"Error clearing expired cache: {e}")

        return count

    def clear(self, pattern: str = "*") -> int:
        """Clear cache entries matching pattern."""
        count = 0

        # Clear Redis
        if self._redis_available:
            try:
                keys = self._redis_client.keys(f"{self.cache_name}:{pattern}")
                if keys:
                    count += self._redis_client.delete(*keys)
            except Exception:
                pass

        # Clear disk
        if self._disk_cache_dir:
            try:
                for file_path in self._disk_cache_dir.glob("*.cache"):
                    file_path.unlink()
                    count += 1
            except Exception:
                pass

        return count

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_name": self.cache_name,
            "redis_available": self._redis_available,
            "disk_available": self._disk_cache_dir is not None,
            "disk_path": str(self._disk_cache_dir) if self._disk_cache_dir else None,
        }


# Default cache instance
default_cache = HybridCacheEngine()
