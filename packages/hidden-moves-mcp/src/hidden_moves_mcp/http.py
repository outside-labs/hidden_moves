"""A bounded local HTTP host; the SDK owns all MCP protocol handling."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from math import isfinite

import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hidden_moves.adapters import CapabilityCatalog

from .server import MCPAdapter

RequestAuthorizer = Callable[[Request], Awaitable[bool]]


class _RequestGuard:
    def __init__(
        self,
        app: ASGIApp,
        *,
        authorize: RequestAuthorizer,
        timeout: float,
        concurrency: int,
    ) -> None:
        self.app = app
        self.authorize = authorize
        self.timeout = timeout
        self.capacity = anyio.CapacityLimiter(concurrency)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            self.capacity.acquire_nowait()
        except anyio.WouldBlock:
            await JSONResponse({"error": "request capacity exceeded"}, status_code=503)(
                scope, receive, send
            )
            return
        started = False
        completed = False

        async def tracked_send(message: Message) -> None:
            nonlocal started, completed
            if message["type"] == "http.response.start":
                started = True
            elif message["type"] == "http.response.body":
                completed = not message.get("more_body", False)
            await send(message)

        try:
            with anyio.fail_after(self.timeout):
                try:
                    permitted = await self.authorize(Request(scope, receive))
                except Exception:
                    # Upstream identity failures may contain credentials.
                    permitted = False
                if permitted is not True:
                    await JSONResponse(
                        {"error": "request authorization required"}, status_code=401
                    )(scope, receive, tracked_send)
                    return
                await self.app(scope, receive, tracked_send)
        except TimeoutError:
            if not started:
                await JSONResponse(
                    {"error": "request deadline exceeded"}, status_code=504
                )(scope, receive, send)
            elif not completed:
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
        finally:
            self.capacity.release()


def create_http_app(
    catalog: CapabilityCatalog,
    *,
    authorize: RequestAuthorizer,
    name: str = "hidden-moves",
    version: str = "0.1.0",
    tool_names: Mapping[str, str] | None = None,
    call_timeout: float = 10,
    request_timeout: float = 30,
    max_concurrency: int = 16,
    max_request_body_size: int = 1024 * 1024,
    offload_sync: bool = True,
) -> Starlette:
    """Create a stateless, JSON-response app for explicitly authorized local use.

    The async authorizer must return exactly True for each allowed request. Its
    identity/credential policy and capability resource lifetimes belong to the
    application. Construction opens no listener and resolves no credentials.
    """
    if not callable(authorize):
        raise ValueError("An explicit asynchronous request authorizer is required.")
    if (
        isinstance(request_timeout, bool)
        or not isinstance(request_timeout, (int, float))
        or not isfinite(request_timeout)
        or not 0 < request_timeout <= 120
    ):
        raise ValueError(
            "request_timeout must be finite and between 0 and 120 seconds."
        )
    if (
        isinstance(max_concurrency, bool)
        or not isinstance(max_concurrency, int)
        or not 1 <= max_concurrency <= 64
    ):
        raise ValueError("max_concurrency must be between 1 and 64.")
    if (
        isinstance(max_request_body_size, bool)
        or not isinstance(max_request_body_size, int)
        or not 1 <= max_request_body_size <= 4 * 1024 * 1024
    ):
        raise ValueError("max_request_body_size must be between 1 byte and 4 MiB.")
    adapter = MCPAdapter(
        catalog,
        tool_names=tool_names,
        offload_sync=offload_sync,
        call_timeout=call_timeout,
    )
    if call_timeout is None or call_timeout > request_timeout:
        raise ValueError("call_timeout must not exceed request_timeout.")
    app = adapter.server(name, version=version).streamable_http_app(
        host="127.0.0.1",
        stateless_http=True,
        json_response=True,
        max_request_body_size=max_request_body_size,
        session_idle_timeout=request_timeout,
        max_sessions=max_concurrency,
    )
    app.add_middleware(
        _RequestGuard,
        authorize=authorize,
        timeout=request_timeout,
        concurrency=max_concurrency,
    )
    return app


async def serve_http(app: Starlette, *, port: int = 8000) -> None:
    """Serve the local app on IPv4 loopback until shutdown, including its lifespan."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535.")
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_level="warning",
        proxy_headers=False,
        lifespan="on",
        timeout_keep_alive=5,
        timeout_graceful_shutdown=5,
    )
    await uvicorn.Server(config).serve()
