"""Shared utilities for all extractors."""
import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def get_session_with_retries(
    total_retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: tuple = (429, 500, 502, 503, 504)
) -> requests.Session:
    """
    Create a requests session with automatic retry logic.
    
    Args:
        total_retries: Number of retry attempts
        backoff_factor: Exponential backoff multiplier (1.0 = 1s, 2s, 4s...)
        status_forcelist: HTTP codes that trigger retries
        
    Returns:
        Configured requests.Session object
    """
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_status=False,  # Let us handle errors
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def download_with_retry(url: str, timeout: int = 120) -> bytes:
    """
    Download a file with automatic retries on failure.
    
    Args:
        url: URL to download
        timeout: Request timeout in seconds
        
    Returns:
        Downloaded content as bytes
        
    Raises:
        requests.RequestException: If download fails after all retries
    """
    session = get_session_with_retries()
    logger.info(f"Downloading {url}")
    
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        logger.info(f"Downloaded {len(resp.content) / 1e6:.1f} MB")
        return resp.content
    except requests.Timeout:
        logger.error(f"Timeout downloading {url} after {timeout}s")
        raise
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        raise
