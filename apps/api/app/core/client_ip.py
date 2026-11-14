"""クライアントIPの取得(レート制限・監査ログで共通)。

X-Forwarded-For は「クライアントIP, プロキシ1, プロキシ2 ...」の形で、各プロキシが
右側に追記していく。左側の値はクライアントが自由に書き換えられるため信用できない。
信頼できるのは、自分たちが管理するインフラ(Cloud Run)が追記した「右端から数えて
TRUSTED_PROXY_COUNT 番目」の値だけ。

  - Cloud Run直(カスタムドメインはドメインマッピング): TRUSTED_PROXY_COUNT=1
  - Cloud Runの前に外部ALBがある構成: 2 (右端はALB自身のIP)
  - プロキシなし(ローカル開発): 0 → X-Forwarded-For は無視し、接続元IPを使う

uvicornの --forwarded-allow-ips="*" は、左端の値(=偽装可能)を採用するため使わない。
"""
import ipaddress

from fastapi import Request

from app.core.config import get_settings

settings = get_settings()


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(request: Request) -> str | None:
    peer = request.client.host if request.client else None
    n = settings.TRUSTED_PROXY_COUNT
    if n <= 0:
        return peer
    header = request.headers.get("x-forwarded-for")
    if not header:
        return peer
    parts = [p.strip() for p in header.split(",") if p.strip()]
    if len(parts) < n:
        # 想定より経路が短い = 設定とインフラが合っていない。偽装を避けて接続元を使う。
        return peer
    return _valid_ip(parts[-n]) or peer
