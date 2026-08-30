import redis
import redis.asyncio as aioredis
from app.database.config import settings

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
async_redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
