"""Rate limiting via slowapi (in-memory token bucket, single-process).

For multi-worker deployments, swap the storage_uri to a Redis URL:
    limiter = Limiter(storage_uri="redis://localhost:6379")
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
