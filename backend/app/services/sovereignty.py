import httpx
import logging
from datetime import datetime
from urllib.parse import urlparse
import os

logger = logging.getLogger("sovereignx")

# Dev-config trusted list: localhost, loopbacks, and testserver only. A
# trusted remote SovereignX node ("2 lap sov") is never a hardcoded IP
# literal here -- it comes from the configured NodeRegistry (AI_NODES_CONFIG,
# see app/services/node_registry.py) via classify_network_target() below, or
# from OLLAMA_BASE_URL's own host (added dynamically just below this block).
TRUSTED_HOSTS_DEV = {"localhost", "127.0.0.1", "testserver"}

# Demo-build trusted list: ONLY localhost, loopbacks, and testserver
TRUSTED_HOSTS_DEMO = {"localhost", "127.0.0.1", "testserver"}

# Toggle trusted host configuration based on environment variable (defaults to DEMO)
IS_DEMO_BUILD = os.getenv("SOVEREIGNX_ENV", "DEMO").upper() == "DEMO"
TRUSTED_HOSTS = TRUSTED_HOSTS_DEMO if IS_DEMO_BUILD else TRUSTED_HOSTS_DEV

# Add the configured OLLAMA_BASE_URL host to the trusted hosts list dynamically
try:
    from app.config import settings
    parsed_ollama = urlparse(settings.OLLAMA_BASE_URL)
    ollama_host = parsed_ollama.hostname or parsed_ollama.netloc
    if ollama_host:
        if ":" in ollama_host:
            ollama_host = ollama_host.split(":")[0]
        TRUSTED_HOSTS_DEV.add(ollama_host.lower())
        TRUSTED_HOSTS_DEMO.add(ollama_host.lower())
except Exception as e:
    logger.error(f"Failed to parse OLLAMA_BASE_URL for trusted configuration: {e}")

class SovereigntyMonitor:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SovereigntyMonitor, cls).__new__(cls, *args, **kwargs)
            cls._instance.connections = []
            cls._instance.subscribers = []
        return cls._instance

    def log_connection(self, method: str, url: str):
        try:
            parsed = urlparse(url)
            host = parsed.hostname or parsed.netloc
            # Remove port suffix from hostname if parsed incorrectly
            if host and ":" in host:
                host = host.split(":")[0]
                
            if not host:
                host = parsed.netloc or "unknown"
                if ":" in host:
                    host = host.split(":")[0]

            port = parsed.port
            if not port:
                port = 443 if parsed.scheme == "https" else 80

            # Normalize localhost representation
            clean_host = host.lower()

            # Trusted if in the static dev/demo set OR a configured, approved
            # "2 lap sov" node (see node_registry.py) -- NOT merely because
            # it's an RFC1918 private address. An unconfigured private IP is
            # deliberately still an "alert", matching the explicit
            # sovereignty requirement that only approved nodes count as
            # trusted local infrastructure.
            is_trusted = clean_host in TRUSTED_HOSTS
            network_target = "EXTERNAL"
            if clean_host in ("localhost", "127.0.0.1", "::1"):
                network_target = "LOCALHOST"
                is_trusted = True
            elif is_trusted:
                network_target = "LOCALHOST"
            else:
                try:
                    from app.services.node_registry import classify_network_target, NetworkTarget
                    target = classify_network_target(clean_host)
                    network_target = target.value
                    if target == NetworkTarget.PRIVATE_LAN:
                        is_trusted = True
                except Exception:
                    pass

            status = "allowed" if is_trusted else "alert"

            entry = {
                "timestamp": datetime.now().isoformat(),
                "method": method,
                "url": url,
                "host": host,
                "port": port,
                "status": status,
                "network_target": network_target,
            }

            self.connections.append(entry)
            self._notify_subscribers(entry)
            
            # Keep logs size bounded (e.g. last 100 entries)
            if len(self.connections) > 100:
                self.connections.pop(0)
                
            return is_trusted
        except Exception as e:
            logger.error(f"Error in sovereignty connection logging: {e}")
            return True

    def register_subscriber(self, callback):
        if callback not in self.subscribers:
            self.subscribers.append(callback)

    def unregister_subscriber(self, callback):
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def _notify_subscribers(self, entry):
        for sub in self.subscribers:
            try:
                sub(entry)
            except Exception:
                pass

    def get_summary(self):
        total = len(self.connections)
        alerts = sum(1 for c in self.connections if c["status"] == "alert")
        status_text = "NO EXTERNAL APPLICATION CONNECTIONS DETECTED" if alerts == 0 else "EXTERNAL APPLICATION CONNECTIONS DETECTED"
        return {
            "status": status_text,
            "total_connections": total,
            "alerts": alerts,
            "log": list(reversed(self.connections))
        }

# --- Monkeypatching HTTP clients ---

# Track if patching is already done to prevent recursion
_is_patched = False

def apply_monkeypatching():
    global _is_patched
    if _is_patched:
        return
    
    logger.info(f"Initializing network sovereignty monitor interceptor (IS_DEMO_BUILD: {IS_DEMO_BUILD})")
    
    # 1. Patch httpx.AsyncClient.send
    _original_httpx_async_send = httpx.AsyncClient.send
    async def _mocked_httpx_async_send(self, request, *args, **kwargs):
        SovereigntyMonitor().log_connection(request.method, str(request.url))
        return await _original_httpx_async_send(self, request, *args, **kwargs)
    httpx.AsyncClient.send = _mocked_httpx_async_send

    # 2. Patch httpx.Client.send
    _original_httpx_sync_send = httpx.Client.send
    def _mocked_httpx_sync_send(self, request, *args, **kwargs):
        SovereigntyMonitor().log_connection(request.method, str(request.url))
        return _original_httpx_sync_send(self, request, *args, **kwargs)
    httpx.Client.send = _mocked_httpx_sync_send

    # 3. Patch requests.Session.send if requests is installed
    try:
        import requests
        _original_requests_send = requests.Session.send
        def _mocked_requests_send(self, request, *args, **kwargs):
            SovereigntyMonitor().log_connection(request.method, str(request.url))
            return _original_requests_send(self, request, *args, **kwargs)
        requests.Session.send = _mocked_requests_send
    except ImportError:
        pass

    _is_patched = True
