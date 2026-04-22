"""Shared SlowAPI Limiter (memory backend; replace with Redis in production if needed)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
