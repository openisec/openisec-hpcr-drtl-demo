import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi.responses import JSONResponse
import time

from app.core.config import get_settings
from app.api.v1.router import api_router
from app.core.rate_limit import limiter

# Root logger defaults to WARNING, which silently drops logger.info() calls
# throughout the app (e.g. app.services.model_armor_service's "which filter
# triggered" log). Cloud Run ships stdout to Cloud Logging automatically, so
# raising the level here is sufficient - no handler/formatter config needed.
logging.basicConfig(level=logging.INFO)

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,  # Disable Swagger in production
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# Rate limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
_additional_origins = [
    o.strip() for o in settings.ADDITIONAL_CORS_ORIGINS.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        settings.FRONTEND_URL,
        *_additional_origins,
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Request-ID", "Authorization"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Validation error handler (strip Pydantic's "Value error, " prefix)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        msg = err.get("msg", "")
        prefix = "Value error, "
        if msg.startswith(prefix):
            msg = msg[len(prefix):]
        errors.append({"loc": err.get("loc"), "msg": msg, "type": err.get("type")})
    return JSONResponse(status_code=422, content={"detail": errors})


# Global error handler (don't leak internal details)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception("Unhandled exception in request: %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.APP_VERSION}
