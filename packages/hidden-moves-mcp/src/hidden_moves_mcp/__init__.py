"""An optional MCP consumer of the neutral capability catalog."""

from .http import create_http_app, serve_http
from .server import MCPAdapter, serve_stdio

__all__ = ["MCPAdapter", "create_http_app", "serve_http", "serve_stdio"]
