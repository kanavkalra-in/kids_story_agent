"""
Security utilities for SSRF protection and URL validation.
"""
from urllib.parse import urlparse
import ipaddress
import socket


def validate_webhook_url_no_ssrf(webhook_url: str) -> None:
    """
    Validate that a webhook URL does not resolve to private/reserved IPs (SSRF protection).
    
    Raises ValueError if the URL is invalid or resolves to a private/reserved IP.
    This function is framework-agnostic so it can be used in both FastAPI and Celery contexts.
    
    Args:
        webhook_url: The webhook URL to validate
        
    Raises:
        ValueError: If the URL is invalid or resolves to a private IP
    """
    if not webhook_url.startswith(('http://', 'https://')):
        raise ValueError("Webhook URL must start with http:// or https://")
    
    try:
        parsed = urlparse(webhook_url)
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("No hostname in URL")
        
        # Resolve to IP and check for private/reserved ranges
        resolved_ips = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in resolved_ips:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                raise ValueError(
                    "Webhook URL must not resolve to a private or internal IP address"
                )
    except ValueError:
        raise
    except Exception:
        raise ValueError("Could not resolve webhook URL hostname")
