"""Redis queue/event/rate-limit and S3-compatible storage adapters."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import boto3
from arq.connections import RedisSettings, create_pool
from redis.asyncio import Redis
from sqlalchemy import text

from app.config import Settings, settings


class RedisInfrastructure:
    """Shared Redis primitives for queues, events, and fixed-window rate limits."""

    def __init__(self, url: str) -> None:
        if not url:
            raise ValueError("redis_url is required")
        self.url = url
        self.client = Redis.from_url(url, decode_responses=True)

    async def enqueue(self, job_id: str, queue_name: str) -> None:
        """Enqueue a job in an isolated arq queue."""
        pool = await create_pool(RedisSettings.from_dsn(self.url))
        try:
            await pool.enqueue_job("execute_job", job_id, _queue_name=queue_name, _job_id=job_id)
        finally:
            await pool.aclose()

    async def publish_event(self, job_id: str, payload: str) -> None:
        """Publish a job event for cross-process subscribers."""
        await self.client.publish(f"jobs:events:{job_id}", payload)

    async def allow_request(self, identity: str, limit: int) -> bool:
        """Apply an atomic one-minute fixed-window request limit."""
        key = f"rate:{identity}"
        script = """
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        return count
        """
        count = await self.client.eval(script, 1, key, 60)
        return int(count) <= limit

    async def close(self) -> None:
        """Close Redis connections."""
        await self.client.aclose()


class S3Storage:
    """S3-compatible artifact storage with content hashes."""

    def __init__(self, config: Settings = settings) -> None:
        if not all(
            (
                config.s3_endpoint_url,
                config.s3_bucket,
                config.s3_access_key,
                config.s3_secret_key,
            )
        ):
            raise ValueError("S3 storage configuration is incomplete")
        self.bucket = config.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=config.s3_endpoint_url,
            aws_access_key_id=config.s3_access_key,
            aws_secret_access_key=config.s3_secret_key,
        )

    async def put_bytes(self, key: str, data: bytes, media_type: str) -> str:
        """Store bytes and return their SHA-256 digest."""
        digest = hashlib.sha256(data).hexdigest()
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=media_type,
            Metadata={"sha256": digest},
        )
        return digest

    async def get_bytes(self, key: str) -> bytes:
        """Read an object from the configured bucket."""
        response = await asyncio.to_thread(
            self.client.get_object,
            Bucket=self.bucket,
            Key=key,
        )
        return await asyncio.to_thread(response["Body"].read)

    async def check(self) -> None:
        """Verify that the configured bucket is reachable."""
        await asyncio.to_thread(self.client.head_bucket, Bucket=self.bucket)


class LocalArtifactStorage:
    """Explicit local development fallback."""

    def __init__(self, root: Path) -> None:
        self.root = root

    async def put_bytes(self, key: str, data: bytes, media_type: str) -> str:
        """Store bytes below the configured local root."""
        del media_type
        destination = (self.root / key).resolve()
        if self.root.resolve() not in destination.parents:
            raise ValueError("invalid storage key")
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(destination.write_bytes, data)
        return hashlib.sha256(data).hexdigest()

    async def get_bytes(self, key: str) -> bytes:
        """Read bytes below the configured local root."""
        source = (self.root / key).resolve()
        if self.root.resolve() not in source.parents:
            raise ValueError("invalid storage key")
        return await asyncio.to_thread(source.read_bytes)


async def check_production_dependencies(config: Settings = settings) -> None:
    """Fail startup if PostgreSQL, Redis, or object storage is unavailable."""
    if config.environment != "production":
        return
    from app.production.models import create_engine

    engine = create_engine(config)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()

    redis = RedisInfrastructure(config.redis_url)
    try:
        await redis.client.ping()
    finally:
        await redis.close()
    await S3Storage(config).check()
