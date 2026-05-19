"""Integration test fixtures — TestApp + Playwright + browser modes."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from mutio.net.server import (
    Server, View as NetView, WebSocketView, StaticView,
    WebSocketConnection, WebSocketDisconnect,
    Request, Response, HTMLResponse,
)

from mutgui import ModuleRegistry, View, ViewPort, Channel


# ---------------------------------------------------------------------------
# TestApp — 测试用 Web 服务器（基于 mutio.net）
# ---------------------------------------------------------------------------

REGISTRY = ModuleRegistry()
REGISTRY.add_from_package("mutgui")


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _html_template(view_id: str) -> str:
    runtime_manifest = REGISTRY.runtime_manifest()
    import_map = {"imports": runtime_manifest["importMap"]}
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>mutgui test</title></head>
<body>
  <div id="app" data-mutgui-app data-ws-url="/ws/{view_id}"></div>
  <script type="importmap">{_json_script(import_map)}</script>
  <script src="{REGISTRY.url_for("mutgui", "boot.js")}"></script>
</body>
</html>
"""


class _TestChannel(Channel):
    def __init__(self, ws: WebSocketConnection) -> None:
        super().__init__()
        self._ws = ws

    async def send(self, message: dict[str, Any]) -> None:
        await self._ws.send_json(message)


class TestApp:
    """测试用 mutgui 服务器。支持动态 mount View，通过通配路由访问。"""

    def __init__(self) -> None:
        super().__init__()
        self._views: dict[str, View] = {}
        self._viewports: list[ViewPort] = []
        self._server: Server | None = None
        self.port: int = 0

    def mount(self, view: View, view_id: str | None = None) -> str:
        view_id = view_id or uuid.uuid4().hex[:8]
        self._views[view_id] = view
        return f"http://127.0.0.1:{self.port}/view/{view_id}"

    async def start(self) -> None:
        test_app = self
        static_views = tuple(
            type(
                f"_Static{index}",
                (StaticView,),
                {"path": path, "directory": str(directory)},
            )
            for index, (path, directory) in enumerate(REGISTRY.static_mounts())
        )

        class _PageView(NetView):
            path = "/view/{view_id}"
            async def get(self, request: Request) -> Response:
                view_id = request.path_params["view_id"]
                if view_id not in test_app._views:
                    return HTMLResponse("View not found", status_code=404)
                return HTMLResponse(_html_template(view_id))

        class _WSView(WebSocketView):
            path = "/ws/{view_id}"
            async def connect(self, ws: WebSocketConnection) -> None:
                view_id = ws.path_params["view_id"]
                view = test_app._views.get(view_id)
                if view is None:
                    await ws.close(code=4004, reason="View not found")
                    return
                await ws.accept()
                first = await ws.receive_json()
                if first.get("type") != "mount.attach":
                    await ws.close(code=4400, reason="expected mount.attach")
                    return
                client = first.get("client") if isinstance(first.get("client"), dict) else None
                runtime_manifest = REGISTRY.runtime_manifest()
                for href in runtime_manifest["css"]:
                    await ws.send_json({"type": "runtime.css", "href": href})
                await ws.send_json({"type": "runtime.import", "module": "@mutgui/antd"})
                await ws.send_json({"type": "runtime.mount"})
                channel = _TestChannel(ws)
                vp = ViewPort(view, channel, _client=client)
                test_app._viewports.append(vp)
                await vp.initialize()
                await view.rendered()
                try:
                    while True:
                        event = await ws.receive_json()
                        await vp.handle_event(event)
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass
                finally:
                    vp.detach()
                    if vp in test_app._viewports:
                        test_app._viewports.remove(vp)

        server = Server(
            host="127.0.0.1", port=0,
            views=(_PageView, _WSView, *static_views),
        )
        self._server = server
        await server.start()

        from mutio.net._server_impl import ServerExt
        ext = ServerExt.get_or_create(server)
        if ext.asgi_server:
            ports = ext.asgi_server.ports()
            if ports:
                self.port = ports[0]

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.stop()


# ---------------------------------------------------------------------------
# pytest options
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--headed", action="store_true", default=False,
                     help="Force headed mode (requires Chrome with CDP on port 9222)")
    parser.addoption("--headless", action="store_true", default=False,
                     help="Force headless mode (requires playwright install chromium)")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def pw():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        yield p


@pytest.fixture(scope="session")
async def browser(request: pytest.FixtureRequest, pw: Any):
    headed = request.config.getoption("--headed")
    headless = request.config.getoption("--headless")

    if headed:
        b = await pw.chromium.connect_over_cdp("http://localhost:9222")
    elif headless:
        b = await pw.chromium.launch(headless=True)
    else:
        try:
            b = await pw.chromium.launch(headless=True)
        except Exception:
            try:
                b = await pw.chromium.connect_over_cdp("http://localhost:9222")
            except Exception:
                pytest.skip("No browser available (Chromium not installed, CDP 9222 unreachable)")
                return
    yield b
    await b.close()


@pytest.fixture(scope="session")
async def app():
    server = TestApp()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
async def page(browser: Any):
    ctx = await browser.new_context()
    p = await ctx.new_page()
    yield p
    await ctx.close()


@pytest.fixture
async def pages(browser: Any):
    ctx1 = await browser.new_context()
    ctx2 = await browser.new_context()
    p1 = await ctx1.new_page()
    p2 = await ctx2.new_page()
    yield p1, p2
    await ctx1.close()
    await ctx2.close()
