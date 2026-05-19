"""Auth form CAPTCHA: SVG image generation and Redis-backed one-time verification."""

from __future__ import annotations

import base64
import random
import secrets
import string
import uuid
from typing import Any

from app.config import settings
from app.exceptions import AppError

_CAPTCHA_KEY_PREFIX = "minerva:auth:captcha:"


def _redis_client() -> Any:
    """Return a synchronous Redis client using the Celery broker URL."""

    import redis

    return redis.Redis.from_url(settings.celery_broker_url, decode_responses=True)


def _random_code(length: int) -> str:
    """Build an uppercase alphanumeric challenge string."""

    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _build_captcha_svg(code: str, *, width: int = 140, height: int = 48) -> str:
    """Render a dark-theme SVG CAPTCHA and return a data-URL for ``<img src>``."""

    noise: list[str] = []
    for _ in range(8):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        noise.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="#475569" stroke-width="1" opacity="0.8"/>'
        )
    glyphs: list[str] = []
    for index, char in enumerate(code):
        x = 16 + index * 28
        y = 32 + random.randint(-4, 4)
        rotate = random.randint(-18, 18)
        glyphs.append(
            f'<text x="{x}" y="{y}" fill="#e2e8f0" font-size="24" '
            f'font-family="Consolas,monospace" font-weight="700" '
            f'transform="rotate({rotate} {x} {y})">{char}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#0f172a" rx="6"/>'
        f'{"".join(noise)}{"".join(glyphs)}</svg>'
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _captcha_key(scope: str, captcha_id: str) -> str:
    """Build Redis key for a scoped auth CAPTCHA challenge."""

    return f"{_CAPTCHA_KEY_PREFIX}{scope}:{captcha_id}"


def create_auth_captcha(scope: str) -> tuple[str, str]:
    """Issue a new CAPTCHA id and image data-URL for ``login`` or ``register``."""

    code = _random_code(settings.auth_login_captcha_length)
    captcha_id = str(uuid.uuid4())
    key = _captcha_key(scope, captcha_id)
    client = _redis_client()
    client.setex(key, settings.auth_login_captcha_ttl_seconds, code.lower())
    return captcha_id, _build_captcha_svg(code)


def create_login_captcha() -> tuple[str, str]:
    """Issue a login-form CAPTCHA."""

    return create_auth_captcha("login")


def create_register_captcha() -> tuple[str, str]:
    """Issue a register-form CAPTCHA."""

    return create_auth_captcha("register")


def verify_auth_captcha(scope: str, captcha_id: str, captcha_code: str) -> None:
    """Validate and consume a scoped CAPTCHA; raises ``AppError`` when invalid."""

    cid = (captcha_id or "").strip()
    answer = (captcha_code or "").strip()
    if not cid or not answer:
        raise AppError("auth.captcha_invalid", "Invalid or expired captcha", 400)
    key = _captcha_key(scope, cid)
    client = _redis_client()
    stored = client.get(key)
    if not stored:
        raise AppError("auth.captcha_invalid", "Invalid or expired captcha", 400)
    client.delete(key)
    if not secrets.compare_digest(str(stored), answer.lower()):
        raise AppError("auth.captcha_invalid", "Invalid or expired captcha", 400)


def verify_login_captcha(captcha_id: str, captcha_code: str) -> None:
    """Validate and consume a login CAPTCHA."""

    verify_auth_captcha("login", captcha_id, captcha_code)


def verify_register_captcha(captcha_id: str, captcha_code: str) -> None:
    """Validate and consume a register CAPTCHA."""

    verify_auth_captcha("register", captcha_id, captcha_code)
