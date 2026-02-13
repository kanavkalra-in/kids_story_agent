import httpx
import asyncio
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize webhook service with retry configuration.
        
        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def send_webhook(
        self, 
        webhook_url: str, 
        payload: Dict[str, Any],
        timeout: float = 30.0
    ) -> bool:
        """
        Send webhook POST request.
        
        Args:
            webhook_url: URL to send webhook to
            payload: JSON payload to send
            timeout: Request timeout in seconds
            
        Returns:
            True if successful
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(f"Webhook sent successfully to {webhook_url}")
            return True

    async def send_webhook_sync(
        self,
        webhook_url: str,
        payload: Dict[str, Any],
        timeout: float = 30.0
    ) -> bool:
        """
        Synchronous wrapper for send_webhook (for use in Celery tasks).
        Creates a new event loop if needed.
        """
        loop = asyncio.get_event_loop()
        
        return await self.send_webhook(webhook_url, payload, timeout)


# Singleton instance
webhook_service = WebhookService()
