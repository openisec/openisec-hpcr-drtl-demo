FROM python:3.12-slim

WORKDIR /app

# 全依存パッケージが wheel(コンパイル済み)で提供されるため、gcc / libpq-dev は不要。
# 不要なパッケージを入れないことで、OS 側の脆弱性(krb5・cyrus-sasl 等)の持ち込みを避ける。
# apt-get upgrade で、ベースイメージ公開後に出た OS パッケージの修正(zlib 等)を取り込む。
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]