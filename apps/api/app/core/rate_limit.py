"""
Shared slowapi Limiter instance.

Kept in its own module (rather than defined in main.py) so that
app/api/v1/endpoints/auth.py can import it without creating a
circular import with app.main.

NOTE: slowapi's default in-memory storage counts per-process. On
Cloud Run with multiple instances, the effective global rate is
"configured limit x instance count" rather than a single shared
count. Acceptable for current traffic levels; a shared store
(e.g. Cloud Memorystore/Redis) would be needed for an exact
cross-instance limit. Tracked as a backlog infra item.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.API_RATE_LIMIT_PER_MINUTE}/minute"],
)
