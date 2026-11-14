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

デフォルト制限(API_RATE_LIMIT_PER_MINUTE)について:
FastAPI 0.139 では include_router したルートが app.routes に展開されず、
SlowAPIMiddleware がルートを見つけられないため、default_limits は /health にしか
効かなかった。/api/v1 配下には default_rate_limit を依存関係として付けて適用する。
(認証系4エンドポイントは従来どおり個別デコレータの制限を併用する。)
"""
from fastapi import HTTPException, Request
from limits import parse
from slowapi import Limiter

from app.core.client_ip import get_client_ip
from app.core.config import get_settings

settings = get_settings()


def _key_func(request: Request) -> str:
    return get_client_ip(request) or "unknown"


limiter = Limiter(
    key_func=_key_func,
    default_limits=[f"{settings.API_RATE_LIMIT_PER_MINUTE}/minute"],
)


def default_rate_limit(request: Request) -> None:
    """/api/v1 配下の全エンドポイントに、クライアントIP×ルート単位の制限をかける。"""
    n = settings.API_RATE_LIMIT_PER_MINUTE
    if n <= 0 or not limiter.enabled:
        return
    route = request.scope.get("route")
    scope = getattr(route, "path", None) or request.url.path
    if not limiter.limiter.hit(parse(f"{n}/minute"), _key_func(request), scope):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )
