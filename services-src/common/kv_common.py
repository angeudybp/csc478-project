"""Shared plumbing for the KubeVision services.

Every service gets the same error envelope (M1 report §4), X-Request-Id
propagation for tracing one upload through all logs (§3.4), and the
/healthz + /readyz endpoints the probes call (§3.7).
"""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

REQUEST_ID_HEADER = "X-Request-Id"

# Error codes for HTTP errors raised by the framework itself (unknown route, bad method, ...).
_FRAMEWORK_CODES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
}

_QUIET_PATHS = ("/healthz", "/readyz", "/metrics")


class ApiError(Exception):
    """Raised by a handler to return the standard error envelope."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    rid = request_id(request)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}, "requestId": rid},
        headers={REQUEST_ID_HEADER: rid},
    )


def create_app(name: str, *, lifespan=None, ready: bool = True,
               body_limits: dict[str, int] | None = None) -> FastAPI:
    """Build a FastAPI app with the shared middleware, error handlers and health checks.

    Set ``app.state.ready`` to False while the service cannot take traffic yet;
    /readyz then answers 503 and Kubernetes keeps the pod out of the Service.
    ``body_limits`` maps a path to the largest Content-Length it accepts; bigger
    requests get a 413 before their body is read.
    """
    body_limits = body_limits or {}
    logging.basicConfig(level=logging.INFO, format=f"%(asctime)s {name} %(levelname)s %(message)s")
    log = logging.getLogger(name)

    app = FastAPI(title=name, lifespan=lifespan)
    app.state.ready = ready

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:8]
        request.state.request_id = rid
        start = time.perf_counter()
        limit = body_limits.get(request.url.path)
        length = request.headers.get("content-length", "")
        if limit is not None and length.isdigit() and int(length) > limit:
            response = error_response(request, 413, "PAYLOAD_TOO_LARGE",
                                      f"Request body exceeds {limit} bytes")
        else:
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        if request.url.path not in _QUIET_PATHS:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log.info("rid=%s %s %s -> %d (%.1f ms)", rid, request.method, request.url.path,
                     response.status_code, elapsed_ms)
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = _FRAMEWORK_CODES.get(exc.status_code, "HTTP_ERROR")
        return error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()))
        return error_response(request, 400, "BAD_REQUEST", f"{where}: {first.get('msg', 'invalid request')}")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("rid=%s unhandled error", request_id(request))
        return error_response(request, 500, "INTERNAL", "Internal server error")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request):
        if not request.app.state.ready:
            return error_response(request, 503, "NOT_READY", f"{name} is not ready")
        return {"status": "ready"}

    return app
