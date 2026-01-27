from __future__ import annotations

import time

from fastapi import HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase


class RateLimiter:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["rate_limits"]

    async def is_rate_limited(self, key: str, limit: int, window_seconds: int) -> bool:
        """
        Check if the given key has exceeded the limit within the window.
        Uses a sliding window approach (simplified).
        """
        now = int(time.time())
        window_start = now - window_seconds

        # Clean up old entries (TTL index is better, but we can do it manually for here)
        # In production, we'd use a TTL index on 'timestamp'

        # Count requests in window
        count = await self.collection.count_documents({"key": key, "timestamp": {"$gte": window_start}})

        if count >= limit:
            return True

        # Log this request
        await self.collection.insert_one({"key": key, "timestamp": now})

        return False


async def check_rate_limit(request: Request, limit: int = 100, window: int = 60, scope: str = "ip"):
    """
    FastAPI dependency for rate limiting.
    scope: 'ip', 'user', or 'org'
    """
    from core.settings import settings

    if not settings.rate_limit_enabled:
        return

    db = request.app.state.db
    limiter = RateLimiter(db)

    key = ""
    if scope == "ip":
        key = request.client.host if request.client else "unknown"
    elif scope == "user":
        # Assumes user is already injected into request.state by auth middleware
        user = getattr(request.state, "user", None)
        key = f"user:{user.username}" if user else f"ip:{request.client.host}"
    elif scope == "org":
        user = getattr(request.state, "user", None)
        key = f"org:{user.org_id}" if user else f"ip:{request.client.host}"

    key = f"{scope}:{key}"

    if await limiter.is_rate_limited(key, limit, window):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded. Please try again later."
        )


# Pre-configured rate limit dependencies for common use cases
def rate_limit_login(request: Request):
    """Rate limit for login endpoints: 5 attempts per minute per IP."""
    return check_rate_limit(request, limit=5, window=60, scope="ip")


def rate_limit_api(request: Request):
    """Rate limit for API endpoints: 100 requests per minute per user."""
    return check_rate_limit(request, limit=100, window=60, scope="user")


def rate_limit_upload(request: Request):
    """Rate limit for upload endpoints: 20 uploads per minute per user."""
    return check_rate_limit(request, limit=20, window=60, scope="user")


def rate_limit_screening(request: Request):
    """Rate limit for screening endpoints: 50 screenings per minute per user."""
    return check_rate_limit(request, limit=50, window=60, scope="user")
