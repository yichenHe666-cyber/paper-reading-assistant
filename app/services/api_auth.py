from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.config import get_settings


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.api_key:
            return await call_next(request)

        path = request.url.path
        skip_prefixes = ["/docs", "/openapi.json", "/redoc", "/api/system/health"]
        if path == "/" or any(path.startswith(p) for p in skip_prefixes):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if api_key != settings.api_key:
            return JSONResponse(status_code=401, content={"detail": "无效的 API Key"})

        return await call_next(request)
