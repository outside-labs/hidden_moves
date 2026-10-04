"""Serve a selected example capability on loopback with a local request grant."""

import asyncio
import os
from hmac import compare_digest

from hidden_moves_example_text import repeat_text
from hidden_moves_mcp import create_http_app, serve_http
from starlette.requests import Request

from hidden_moves import Moves
from hidden_moves.adapters import CapabilityCatalog


def main() -> None:
    token = os.environ.get("HIDDEN_MOVES_LOCAL_HTTP_TOKEN", "")
    if not 32 <= len(token) <= 512 or not token.isascii() or not token.isprintable():
        raise ValueError(
            "Configure a printable ASCII local HTTP token of 32-512 characters."
        )

    async def authorize(request: Request) -> bool:
        supplied = request.headers.get("authorization", "")
        return compare_digest(supplied.encode(), f"Bearer {token}".encode())

    moves = Moves()
    moves.learn(repeat_text, name="repeat", namespace="example.text")
    catalog = CapabilityCatalog(moves, ["example.text.repeat"])
    asyncio.run(serve_http(create_http_app(catalog, authorize=authorize)))


if __name__ == "__main__":
    main()
