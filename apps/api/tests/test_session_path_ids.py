"""
パスの {session_id} / {message_id} がUUIDとして宣言されていることの確認。

DAST(ZAP)が GET /sessions/1909291848751298795 のような不正なIDを送ったところ、
UUID列との比較で例外になり500エラーになった。UUIDとして宣言しておけば、
不正なIDは入口で422として拒否される。
"""
from app.main import app


def test_all_session_and_message_id_path_params_are_uuid():
    spec = app.openapi()
    checked = 0
    for path, item in spec["paths"].items():
        for method, op in item.items():
            for p in op.get("parameters", []):
                if p["in"] == "path" and p["name"] in ("session_id", "message_id"):
                    schema = p["schema"]
                    assert schema.get("format") == "uuid", f"{method.upper()} {path} {p['name']}: {schema}"
                    checked += 1
    assert checked >= 10
