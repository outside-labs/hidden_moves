"""Actual loopback HTTP clients exercise authorization, budgets and shutdown."""

import asyncio
import json
import socket
import threading
import unittest
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx2
import uvicorn
from hidden_moves_mcp import MCPAdapter, create_http_app
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.types import INVALID_PARAMS

from hidden_moves import MoveAnnotations, Moves
from hidden_moves.adapters import CapabilityCatalog

_HEADERS = {"authorization": "Bearer synthetic-local-http-fixture"}


async def authorize(request):
    return request.headers.get("authorization") == _HEADERS["authorization"]


def catalog_for(operation, **options):
    moves = Moves()
    moves.learn(operation, name="operation", namespace="example", **options)
    return CapabilityCatalog(moves, ["example.operation"])


def echo(value: str) -> str:
    return value


@dataclass
class Note:
    title: str
    labels: list[str]


@asynccontextmanager
async def live_app(app):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(32)
        listener.setblocking(False)
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                lifespan="on",
                access_log=False,
                log_level="warning",
                proxy_headers=False,
                timeout_graceful_shutdown=2,
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("HTTP fixture stopped before startup")
                    await asyncio.sleep(0.005)
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 5)
            if not task.done():
                raise AssertionError("HTTP fixture did not shut down")


@asynccontextmanager
async def http_client(url, *, mode="auto"):
    async with httpx2.AsyncClient(headers=_HEADERS, timeout=5, trust_env=False) as http:
        async with Client(
            streamable_http_client(url, http_client=http),
            mode=mode,
            read_timeout_seconds=5,
        ) as client:
            yield client


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_initialize_list_call_matches_python_and_stdio_adapter(self):
        calls = []

        def operation(note: Note) -> Note:
            calls.append(note)
            return note

        catalog = catalog_for(
            operation, annotations=MoveAnnotations(read_only=True, external=False)
        )
        arguments = {"note": {"title": "Héllo", "labels": ["a", "b"]}}
        expected = catalog.serialize_result(
            "example.operation", catalog.invoke("example.operation", arguments)
        )
        async with Client(MCPAdapter(catalog).server()) as client:
            direct = await client.call_tool("example.operation", arguments)
        async with live_app(create_http_app(catalog, authorize=authorize)) as url:
            for mode, protocol in [("legacy", "2025-11-25"), ("auto", "2026-07-28")]:
                async with http_client(url, mode=mode) as client:
                    self.assertEqual(client.protocol_version, protocol)
                    listing = await client.list_tools()
                    self.assertEqual(
                        [tool.name for tool in listing.tools], ["example.operation"]
                    )
                    self.assertTrue(listing.tools[0].annotations.read_only_hint)
                    result = await client.call_tool("example.operation", arguments)
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content, {"result": expected})
                    self.assertEqual(
                        result.structured_content, direct.structured_content
                    )
                    self.assertEqual(
                        json.loads(result.content[0].text), result.structured_content
                    )
                    with self.assertRaises(MCPError) as caught:
                        await client.call_tool("example.unselected", arguments)
                    self.assertEqual(caught.exception.code, INVALID_PARAMS)
                    invalid = await client.call_tool(
                        "example.operation", {"note": {"title": True}}
                    )
                    self.assertTrue(invalid.is_error)
        self.assertEqual(len(calls), 4)
        # The server task and SDK lifespan completed, and the listener was closed.
        with self.assertRaises(OSError):
            await asyncio.to_thread(
                socket.create_connection,
                ("127.0.0.1", int(url.split(":")[2].split("/")[0])),
                1,
            )

    async def test_unauthorized_requests_cannot_dispatch_protocol_or_invoke(self):
        calls = []

        def operation(value: str) -> str:
            calls.append(value)
            return value

        async with live_app(
            create_http_app(catalog_for(operation), authorize=authorize)
        ) as url:
            async with httpx2.AsyncClient(timeout=5, trust_env=False) as client:
                for headers in ({}, {"authorization": "Bearer rejected-private-value"}):
                    response = await client.post(
                        url, headers=headers, content=b"not-json"
                    )
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn("rejected-private-value", response.text)
        self.assertEqual(calls, [])

    async def test_authorizer_errors_fail_closed_without_private_error_text(self):
        async def broken(_request):
            raise RuntimeError("private-identity-state")

        async with live_app(
            create_http_app(catalog_for(echo), authorize=broken)
        ) as url:
            async with httpx2.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.post(url, json={})
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("private-identity-state", response.text)

    async def test_sdk_rejects_oversized_body_host_and_origin(self):
        app = create_http_app(
            catalog_for(echo), authorize=authorize, max_request_body_size=1024
        )
        async with live_app(app) as url:
            async with httpx2.AsyncClient(
                headers=_HEADERS, timeout=5, trust_env=False
            ) as client:
                response = await client.post(url, content=b"x" * 2048)
                self.assertEqual(response.status_code, 413)
                response = await client.post(
                    url, headers={"host": "untrusted.example"}, json={}
                )
                self.assertEqual(response.status_code, 421)
                response = await client.post(
                    url, headers={"origin": "https://untrusted.example"}, json={}
                )
                self.assertEqual(response.status_code, 403)

    async def test_async_call_deadline_cancels_the_handler_and_host_stays_usable(self):
        cancelled = asyncio.Event()

        async def operation(wait: bool) -> str:
            if wait:
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return "ready"

        app = create_http_app(
            catalog_for(operation), authorize=authorize, call_timeout=0.1
        )
        async with live_app(app) as url:
            async with http_client(url) as client:
                result = await client.call_tool("example.operation", {"wait": True})
                self.assertTrue(result.is_error)
                self.assertIn("TimeoutError", result.content[0].text)
                await asyncio.wait_for(cancelled.wait(), 1)
                result = await client.call_tool("example.operation", {"wait": False})
                self.assertEqual(result.structured_content, {"result": "ready"})

    async def test_synchronous_io_is_offloaded_and_does_not_block_other_requests(self):
        entered = threading.Event()
        release = threading.Event()
        thread_ids = []

        def operation() -> str:
            thread_ids.append(threading.get_ident())
            entered.set()
            if not release.wait(3):
                raise TimeoutError("fixture release did not arrive")
            return "finished"

        app = create_http_app(catalog_for(operation), authorize=authorize)
        async with live_app(app) as url:
            async with http_client(url) as first, http_client(url) as second:
                call = asyncio.create_task(first.call_tool("example.operation", {}))
                try:
                    async with asyncio.timeout(2):
                        while not entered.is_set():
                            await asyncio.sleep(0.005)
                    # Listing must finish while the synchronous call is still waiting.
                    async with asyncio.timeout(1):
                        listing = await second.list_tools()
                    self.assertEqual(len(listing.tools), 1)
                    self.assertFalse(call.done())
                    self.assertNotEqual(thread_ids, [threading.get_ident()])
                finally:
                    release.set()
                    result = await call
                self.assertEqual(result.structured_content, {"result": "finished"})

    async def test_synchronous_deadline_returns_without_claiming_to_stop_the_worker(
        self,
    ):
        entered = threading.Event()
        release = threading.Event()
        completed = threading.Event()

        def operation() -> str:
            entered.set()
            release.wait(3)
            completed.set()
            return "finished"

        app = create_http_app(
            catalog_for(operation), authorize=authorize, call_timeout=0.1
        )
        async with live_app(app) as url:
            async with http_client(url) as client:
                try:
                    result = await client.call_tool("example.operation", {})
                    self.assertTrue(entered.is_set())
                    self.assertTrue(result.is_error)
                    self.assertIn("TimeoutError", result.content[0].text)
                    self.assertFalse(completed.is_set())
                finally:
                    release.set()
                    async with asyncio.timeout(1):
                        while not completed.is_set():
                            await asyncio.sleep(0.005)

    async def test_request_deadline_bounds_a_stalled_authorizer(self):
        async def stalled(_request):
            await asyncio.Event().wait()
            return True

        app = create_http_app(
            catalog_for(echo), authorize=stalled, call_timeout=0.05, request_timeout=0.1
        )
        async with live_app(app) as url:
            async with httpx2.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.post(url, json={})
                self.assertEqual(response.status_code, 504)

    async def test_concurrency_budget_rejects_excess_requests_then_releases_capacity(
        self,
    ):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def waiting(request):
            if request.headers.get("x-hold"):
                entered.set()
                await release.wait()
            return False

        app = create_http_app(catalog_for(echo), authorize=waiting, max_concurrency=1)
        async with live_app(app) as url:
            async with httpx2.AsyncClient(timeout=5, trust_env=False) as client:
                first = asyncio.create_task(
                    client.post(url, headers={"x-hold": "1"}, json={})
                )
                try:
                    await asyncio.wait_for(entered.wait(), 2)
                    rejected = await client.post(url, json={})
                    self.assertEqual(rejected.status_code, 503)
                finally:
                    release.set()
                    finished = await first
                self.assertEqual(finished.status_code, 401)
                response = await client.post(url, json={})
                self.assertEqual(response.status_code, 401)

    def test_configuration_requires_explicit_authorization_and_finite_budgets(self):
        catalog = catalog_for(echo)
        for options in (
            {"authorize": None},
            {"request_timeout": float("nan")},
            {"request_timeout": True},
            {"request_timeout": 121},
            {"call_timeout": None},
            {"call_timeout": float("inf")},
            {"call_timeout": 31},
            {"max_concurrency": 0},
            {"max_concurrency": True},
            {"max_request_body_size": 0},
            {"max_request_body_size": 4 * 1024 * 1024 + 1},
            {"offload_sync": "yes"},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                create_http_app(catalog, **({"authorize": authorize} | options))
