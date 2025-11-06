import random
import logging

class ProxyHandler:
    def __init__(self, proxy_file_path: str):
        self.proxies = self._load_proxies(proxy_file_path)
        self.failed_proxies = set()
        self.current_proxy = None

    def _load_proxies(self, file_path):
        try:
            with open(file_path, 'r') as f:
                proxies = [line.strip() for line in f if line.strip()]
            logging.info(f"Loaded {len(proxies)} proxies from file.")
            return proxies
        except FileNotFoundError:
            logging.error(f"Proxy file not found: {file_path}")
            return []

    def get_random_proxy(self):
        available_proxies = [p for p in self.proxies if p not in self.failed_proxies]
        if not available_proxies:
            logging.warning("No working proxies left. Retrying with all proxies.")
            self.failed_proxies.clear()
            available_proxies = self.proxies[:]
        self.current_proxy = random.choice(available_proxies)
        return self.current_proxy

    def mark_failed(self, proxy):
        self.failed_proxies.add(proxy)

    def get_requests_proxy(self):
        proxy = self.get_random_proxy()
        return {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }

    def test_proxy(self, proxy, test_url="http://httpbin.org/ip"):
        import requests
        try:
            proxies = {
                "http": f"http://{proxy}",
                "https": f"http://{proxy}"
            }
            response = requests.get(test_url, proxies=proxies, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logging.warning(f"Proxy failed: {proxy} | {e}")
            return False
