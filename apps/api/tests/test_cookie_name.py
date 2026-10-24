"""
ログインCookie名が環境変数 COOKIE_NAME で変更できること。

dev/stg/prd/demoは .openisec.com 配下でCookieを共有するため、環境ごとに
名前を分けないと別環境のログインで上書きされる。未指定なら従来の
"access_token" のままで、既存環境の挙動は変わらない。
"""
import os
import subprocess
import sys

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = "from app.core.deps import ACCESS_TOKEN_COOKIE_NAME as n; print(n)"


def _cookie_name(**env):
    base = {k: v for k, v in os.environ.items() if k != "COOKIE_NAME"}
    result = subprocess.run(
        [sys.executable, "-c", CODE],
        cwd=API_DIR,
        env={**base, **env},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_cookie_name_defaults_to_access_token():
    assert _cookie_name() == "access_token"


def test_cookie_name_is_overridable_per_environment():
    assert _cookie_name(COOKIE_NAME="access_token_stg") == "access_token_stg"
