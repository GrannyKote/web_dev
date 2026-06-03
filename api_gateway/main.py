import os

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://127.0.0.1:8002").rstrip("/")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://127.0.0.1:8000").rstrip("/")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")
ADMIN_SERVICE_URL = os.getenv("ADMIN_SERVICE_URL", "http://127.0.0.1:8003").rstrip("/")

ROUTE_MAP: dict[str, str] = {
    "auth": AUTH_SERVICE_URL,
    "catalog": CATALOG_SERVICE_URL,
    "order": ORDER_SERVICE_URL,
    "admin": ADMIN_SERVICE_URL,
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}

app = FastAPI(title="API Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    client: httpx.AsyncClient | None = getattr(app.state, "client", None)
    if client is not None:
        await client.aclose()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "services": list(ROUTE_MAP.keys())}


async def _proxy(request: Request, target_base: str, target_path: str) -> Response:
    client: httpx.AsyncClient = request.app.state.client
    url = f"{target_base}/{target_path.lstrip('/')}"

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    body = await request.body()

    try:
        upstream = await client.request(
            method=request.method,
            url=url,
            params=request.query_params,
            headers=headers,
            content=body,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream service unavailable: {exc}",
        ) from exc

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


@app.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy_with_path(service: str, path: str, request: Request) -> Response:
    target_base = ROUTE_MAP.get(service)
    if target_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown service prefix: {service}",
        )
    return await _proxy(request, target_base, f"{service}/{path}")


@app.api_route(
    "/{service}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy_root(service: str, request: Request) -> Response:
    target_base = ROUTE_MAP.get(service)
    if target_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown service prefix: {service}",
        )
    return await _proxy(request, target_base, service)
