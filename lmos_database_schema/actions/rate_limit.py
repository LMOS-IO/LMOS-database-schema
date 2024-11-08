from redis.asyncio.client import Redis
import time
from typing import NamedTuple

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_PREFIX = "RateLimits"

class CurrentUsage(NamedTuple):
    requests: int
    resources: int
    remaining_seconds: int

def _get_window_key(key_hash: str, model_name: str) -> str:
    # Round to nearest minute
    current_window = int(time.time() / RATE_LIMIT_WINDOW) * RATE_LIMIT_WINDOW
    return f"{RATE_LIMIT_PREFIX}:{key_hash}:{model_name}:{current_window}"

async def record_ratelimit_usage(
    redis_client: Redis,
    key_hash: str,
    model_name: str,
    resources: int
) -> None:
    """
    Record usage for both requests and resources for the current minute window.
    
    Args:
        redis_client: Redis client instance
        key_hash: The API key hash
        model_name: Name of the model being accessed
        resources: Amount of resources being used (tokens, seconds, etc.)
    """
    window_key = _get_window_key(key_hash, model_name)
    
    async with redis_client.pipeline(transaction=True) as pipe:
        # Create hash if it doesn't exist with TTL
        await pipe.hsetnx(window_key, "requests", 0)
        await pipe.hsetnx(window_key, "resources", 0)
        await pipe.expire(window_key, RATE_LIMIT_WINDOW)
        
        # Increment both values
        await pipe.hincrby(window_key, "requests", 1)
        await pipe.hincrby(window_key, "resources", resources)
        
        await pipe.execute()

async def get_current_limits(
    redis_client: Redis,
    key_hash: str,
    model_name: str
) -> CurrentUsage:
    """
    Get current usage for the current minute window.
    
    Args:
        redis_client: Redis client instance
        key_hash: The API key hash
        model_name: Name of the model being accessed
        
    Returns:
        CurrentUsage with requests, resources, and seconds remaining in window
    """
    window_key = _get_window_key(key_hash, model_name)
    
    try:
        # Get current values
        requests = await redis_client.hget(window_key, 'requests')
        resources = await redis_client.hget(window_key, 'resources')
        
        # Calculate remaining time in window
        current_time = time.time()
        current_window_start = int(current_time / RATE_LIMIT_WINDOW) * RATE_LIMIT_WINDOW
        remaining_seconds = RATE_LIMIT_WINDOW - (int(current_time) - current_window_start)
        
        return CurrentUsage(
            requests=int(requests) if requests else 0,
            resources=int(resources) if resources else 0,
            remaining_seconds=remaining_seconds
        )
        
    except Exception as e:
        raise Exception(f"Failed to get current rate limits: {str(e)}")