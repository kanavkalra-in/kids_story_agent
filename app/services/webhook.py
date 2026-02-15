import httpx
import logging
from app.utils.security import validate_webhook_url_no_ssrf

logger = logging.getLogger(__name__)


def send_webhook_sync(
    webhook_url: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> bool:
    """
    Send a webhook POST request synchronously (for use in Celery tasks).
    Re-validates the webhook URL for SSRF protection before sending.

    Args:
        webhook_url: URL to send webhook to
        payload: JSON payload to send
        timeout: Request timeout in seconds

    Returns:
        True if successful, False otherwise
    """
    # Re-validate webhook URL at delivery time to prevent TOCTOU attacks
    try:
        validate_webhook_url_no_ssrf(webhook_url)
    except Exception as e:
        logger.warning(f"Webhook URL validation failed for {webhook_url}: {str(e)}")
        return False
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(f"Webhook sent successfully to {webhook_url}")
            return True
    except httpx.HTTPError as e:
        logger.warning(f"Failed to send webhook to {webhook_url}: {str(e)}")
        return False
