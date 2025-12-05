"""
Event Bus for publishing and subscribing to real-time events
Uses Redis pub/sub for cross-process communication
"""

from typing import Any, Dict, Optional, Callable
import json
import logging
from datetime import datetime
import asyncio
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)


class EventBus:
    """
    Event Bus for real-time event publishing and subscription

    Publishes events to Redis channels that can be consumed by:
    - WebSocket manager (for real-time UI updates)
    - Other backend services
    - Celery workers
    """

    def __init__(self, redis_client: Redis):
        """
        Initialize EventBus with Redis client

        Args:
            redis_client: Synchronous Redis client instance
        """
        self.redis = redis_client
        self.async_redis: Optional[AsyncRedis] = None

    async def init_async(self, redis_url: str):
        """
        Initialize async Redis client for subscriptions

        Args:
            redis_url: Redis connection URL
        """
        self.async_redis = await AsyncRedis.from_url(redis_url)
        logger.info("EventBus async Redis client initialized")

    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        team_id: Optional[str] = None
    ):
        """
        Publish event to Redis channel

        Args:
            event_type: Type of event (e.g., 'job_completed', 'company_updated')
            data: Event data payload
            user_id: Optional user ID to send to specific user
            team_id: Optional team ID to send to team members
        """
        try:
            message = {
                "event": event_type,
                "data": data,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Determine channel(s) to publish to
            channels = []

            if user_id:
                # User-specific channel
                channels.append(f"events:user:{user_id}")

            if team_id:
                # Team-specific channel
                channels.append(f"events:team:{team_id}")

            if not user_id and not team_id:
                # Global channel (all users)
                channels.append("events:global")

            # Publish to all relevant channels
            for channel in channels:
                self.redis.publish(channel, json.dumps(message))
                logger.debug(f"Published {event_type} to {channel}")

        except Exception as e:
            logger.error(f"Error publishing event {event_type}: {e}")

    def publish_sync(
        self,
        event_type: str,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        team_id: Optional[str] = None
    ):
        """
        Synchronous publish (for use in non-async contexts like Celery)

        Args:
            event_type: Type of event
            data: Event data payload
            user_id: Optional user ID
            team_id: Optional team ID
        """
        try:
            message = {
                "event": event_type,
                "data": data,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Determine channel(s)
            channels = []

            if user_id:
                channels.append(f"events:user:{user_id}")

            if team_id:
                channels.append(f"events:team:{team_id}")

            if not user_id and not team_id:
                channels.append("events:global")

            # Publish to all channels
            for channel in channels:
                self.redis.publish(channel, json.dumps(message))
                logger.debug(f"Published {event_type} to {channel}")

        except Exception as e:
            logger.error(f"Error publishing event {event_type}: {e}")

    async def subscribe(
        self,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        callback: Optional[Callable] = None
    ):
        """
        Subscribe to events from Redis channels

        Args:
            user_id: Optional user ID to subscribe to user-specific events
            team_id: Optional team ID to subscribe to team events
            callback: Optional callback function to handle messages

        Yields:
            Event messages as dictionaries
        """
        if not self.async_redis:
            raise RuntimeError("Async Redis client not initialized. Call init_async() first.")

        try:
            pubsub = self.async_redis.pubsub()

            # Determine channels to subscribe to
            channels = []

            if user_id:
                channels.append(f"events:user:{user_id}")

            if team_id:
                channels.append(f"events:team:{team_id}")

            if not user_id and not team_id:
                channels.append("events:global")

            # Subscribe to channels
            await pubsub.subscribe(*channels)
            logger.info(f"Subscribed to channels: {channels}")

            # Listen for messages
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])

                        if callback:
                            await callback(data)
                        else:
                            yield data

                    except json.JSONDecodeError as e:
                        logger.error(f"Error decoding message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

        except Exception as e:
            logger.error(f"Error in subscription: {e}")
        finally:
            await pubsub.unsubscribe()
            await pubsub.close()

    async def close(self):
        """Close async Redis connection"""
        if self.async_redis:
            await self.async_redis.close()
            logger.info("EventBus async Redis client closed")


# Helper functions for common events
def publish_job_started(event_bus: EventBus, job_id: str, job_type: str, user_id: str):
    """Publish job started event"""
    event_bus.publish_sync(
        "job_started",
        {"job_id": job_id, "job_type": job_type},
        user_id=user_id
    )


def publish_job_progress(
    event_bus: EventBus,
    job_id: str,
    progress: int,
    user_id: str,
    status_message: Optional[str] = None
):
    """Publish job progress event"""
    event_bus.publish_sync(
        "job_progress",
        {
            "job_id": job_id,
            "progress": progress,
            "status_message": status_message
        },
        user_id=user_id
    )


def publish_job_completed(
    event_bus: EventBus,
    job_id: str,
    job_type: str,
    user_id: str,
    result: Optional[Dict] = None
):
    """Publish job completed event"""
    event_bus.publish_sync(
        "job_completed",
        {
            "job_id": job_id,
            "job_type": job_type,
            "result": result
        },
        user_id=user_id
    )


def publish_job_failed(
    event_bus: EventBus,
    job_id: str,
    job_type: str,
    error: str,
    user_id: str
):
    """Publish job failed event"""
    event_bus.publish_sync(
        "job_failed",
        {
            "job_id": job_id,
            "job_type": job_type,
            "error": error
        },
        user_id=user_id
    )


def publish_company_updated(
    event_bus: EventBus,
    company_id: str,
    user_id: str,
    status: Optional[str] = None,
    fields_updated: Optional[list] = None
):
    """Publish company updated event"""
    event_bus.publish_sync(
        "company_updated",
        {
            "company_id": company_id,
            "status": status,
            "fields_updated": fields_updated
        },
        user_id=user_id
    )


def publish_notification(
    event_bus: EventBus,
    notification_id: str,
    title: str,
    message: str,
    notification_type: str,
    user_id: str,
    action_url: Optional[str] = None
):
    """Publish notification event"""
    event_bus.publish_sync(
        "notification",
        {
            "id": notification_id,
            "type": notification_type,
            "title": title,
            "message": message,
            "action_url": action_url
        },
        user_id=user_id
    )


# Global event bus instance (initialized in main.py)
event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get global event bus instance"""
    if not event_bus:
        raise RuntimeError("EventBus not initialized. Call init_event_bus() first.")
    return event_bus


def init_event_bus(redis_client: Redis) -> EventBus:
    """
    Initialize global event bus

    Args:
        redis_client: Redis client instance

    Returns:
        EventBus instance
    """
    global event_bus
    event_bus = EventBus(redis_client)
    logger.info("EventBus initialized")
    return event_bus
