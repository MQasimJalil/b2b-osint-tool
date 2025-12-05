"""
Proxy manager for rotating proxies during discovery.
"""
from typing import List, Optional, Dict
import httpx
import asyncio
import logging
from datetime import datetime, timedelta
import random

logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages proxy rotation and health checking."""

    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        check_interval: int = 300,  # Check proxy health every 5 minutes
        timeout: int = 10
    ):
        """
        Initialize proxy manager.

        Args:
            proxies: List of proxy URLs (e.g., ["http://proxy1:8080", "http://proxy2:8080"])
            check_interval: Interval in seconds between health checks
            timeout: Timeout in seconds for proxy health checks
        """
        self.proxies = proxies or []
        self.check_interval = check_interval
        self.timeout = timeout

        # Track proxy health status
        self.proxy_health: Dict[str, Dict] = {
            proxy: {
                "healthy": True,
                "last_check": None,
                "failures": 0,
                "successes": 0
            }
            for proxy in self.proxies
        }

        self._current_index = 0
        self._lock = asyncio.Lock()
        self._health_check_task = None

    async def start(self):
        """Start the proxy manager and begin health checks."""
        if self.proxies and not self._health_check_task:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info(f"Proxy manager started with {len(self.proxies)} proxies")

    async def stop(self):
        """Stop the proxy manager and cancel health checks."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Proxy manager stopped")

    async def get_proxy(self) -> Optional[str]:
        """
        Get the next healthy proxy in rotation.

        Returns:
            Proxy URL or None if no proxies configured or all proxies are unhealthy
        """
        if not self.proxies:
            return None

        async with self._lock:
            # Try to find a healthy proxy
            attempts = 0
            max_attempts = len(self.proxies)

            while attempts < max_attempts:
                proxy = self.proxies[self._current_index]
                self._current_index = (self._current_index + 1) % len(self.proxies)

                if self.proxy_health[proxy]["healthy"]:
                    return proxy

                attempts += 1

            # All proxies unhealthy, return None
            logger.warning("All proxies are unhealthy")
            return None

    async def mark_proxy_success(self, proxy: str):
        """Mark a proxy as successful."""
        if proxy in self.proxy_health:
            async with self._lock:
                self.proxy_health[proxy]["successes"] += 1
                self.proxy_health[proxy]["failures"] = 0
                self.proxy_health[proxy]["healthy"] = True

    async def mark_proxy_failure(self, proxy: str):
        """Mark a proxy as failed."""
        if proxy in self.proxy_health:
            async with self._lock:
                self.proxy_health[proxy]["failures"] += 1

                # Mark as unhealthy after 3 consecutive failures
                if self.proxy_health[proxy]["failures"] >= 3:
                    self.proxy_health[proxy]["healthy"] = False
                    logger.warning(f"Proxy marked as unhealthy: {proxy}")

    async def _health_check_loop(self):
        """Background loop to check proxy health."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_all_proxies()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in proxy health check loop: {e}")

    async def _check_all_proxies(self):
        """Check health of all proxies."""
        tasks = [self._check_proxy_health(proxy) for proxy in self.proxies]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_proxy_health(self, proxy: str):
        """
        Check if a proxy is healthy by making a test request.

        Args:
            proxy: Proxy URL to check
        """
        try:
            async with httpx.AsyncClient(
                proxies={"http://": proxy, "https://": proxy},
                timeout=self.timeout
            ) as client:
                # Make a simple request to check connectivity
                response = await client.get("https://www.google.com")
                response.raise_for_status()

                # Mark as healthy
                async with self._lock:
                    self.proxy_health[proxy]["healthy"] = True
                    self.proxy_health[proxy]["last_check"] = datetime.utcnow()
                    self.proxy_health[proxy]["failures"] = 0
                    self.proxy_health[proxy]["successes"] += 1

                logger.debug(f"Proxy healthy: {proxy}")

        except Exception as e:
            # Mark as unhealthy
            async with self._lock:
                self.proxy_health[proxy]["failures"] += 1
                self.proxy_health[proxy]["last_check"] = datetime.utcnow()

                if self.proxy_health[proxy]["failures"] >= 3:
                    self.proxy_health[proxy]["healthy"] = False
                    logger.warning(f"Proxy unhealthy: {proxy} - {e}")

    def get_proxy_stats(self) -> Dict:
        """
        Get statistics about proxy health.

        Returns:
            Dict with proxy statistics
        """
        total_proxies = len(self.proxies)
        healthy_proxies = sum(
            1 for p in self.proxy_health.values() if p["healthy"]
        )

        return {
            "total_proxies": total_proxies,
            "healthy_proxies": healthy_proxies,
            "unhealthy_proxies": total_proxies - healthy_proxies,
            "proxies": self.proxy_health
        }


class NoProxyManager(ProxyManager):
    """Proxy manager that doesn't use any proxies (for development)."""

    def __init__(self):
        super().__init__(proxies=[])

    async def get_proxy(self) -> None:
        """Always return None (no proxy)."""
        return None


def create_proxy_manager(
    mode: str = "none",
    proxies: Optional[List[str]] = None
) -> ProxyManager:
    """
    Factory function to create a proxy manager.

    Args:
        mode: Proxy mode ('none', 'standard', 'rotating')
        proxies: List of proxy URLs

    Returns:
        ProxyManager instance
    """
    if mode == "none":
        return NoProxyManager()
    else:
        return ProxyManager(proxies=proxies or [])
