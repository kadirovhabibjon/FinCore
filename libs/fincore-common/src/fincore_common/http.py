import ssl
from typing import Any

import httpx

# Built once per process. `httpx.AsyncClient()` otherwise builds a fresh
# SSLContext on every construction — loading the CA bundle
# synchronously, ~16ms of CPU with the event loop blocked — even when
# the target is plain http://. Services here deliberately construct a
# new client per outbound call (so tests can inject a transport, and so
# no connection pool is ever bound to one event loop and reused on
# another), which made that cost per call: payment-service's single
# event loop saturated at ~30 req/s under load, spending its time
# building SSL contexts (see README, "Load testing"). An SSLContext is
# safe to share across connections; this one is httpx's own default
# (certificate verification on), so TLS behavior is unchanged.
_SSL_CONTEXT: ssl.SSLContext = httpx.create_ssl_context()


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Drop-in replacement for `httpx.AsyncClient(...)` that reuses the
    process-wide SSL context instead of building a new one."""
    kwargs.setdefault("verify", _SSL_CONTEXT)
    return httpx.AsyncClient(**kwargs)
