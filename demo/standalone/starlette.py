"""Starlette + uvicorn 集成示例。

展示 mutgui 的 transport-agnostic 特性 — Channel 接口可适配任何 Web 框架。
这个文件独立运行，不依赖 demo/framework。

启动::

    pip install starlette uvicorn
    python demo/standalone/starlette.py

然后打开 http://localhost:8080
"""
from __future__ import annotations

import json
import os
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from mutgui import ModuleRegistry, View, ViewBlock, Callback, Channel, ViewPort


# ---------------------------------------------------------------------------
# Channel 适配 Starlette WebSocket
# ---------------------------------------------------------------------------

class StarletteChannel(Channel):
    def __init__(self, ws: WebSocket) -> None:
        super().__init__()
        self.ws = ws

    async def send(self, message: dict[str, Any]) -> None:
        await self.ws.send_json(message)


# ---------------------------------------------------------------------------
# 一个简单的 View
# ---------------------------------------------------------------------------

class HelloView(View):
    count: int = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3, "children": "mutgui + Starlette"},
            {"$component": "antd.Typography.Text", "$id": "desc",
             "type": "secondary",
             "children": "This demo uses Starlette + uvicorn, not mutio.net."},
            {"$component": "antd.Button", "$id": "btn",
             "type": "primary", "size": "large",
             "style": {"marginTop": 16},
             "children": f"Clicked {self.count} times",
             "onClick": Callback(self._on_click)},
        ])

    def _on_click(self) -> None:
        self.count += 1
        self.invalidate()


# ---------------------------------------------------------------------------
# Starlette 路由
# ---------------------------------------------------------------------------

view = HelloView()
viewports: list[ViewPort] = []


async def ws_handler(websocket: WebSocket) -> None:
    await websocket.accept()
    first = await websocket.receive_json()
    if first.get("type") != "mount.attach":
        await websocket.close(code=4400, reason="expected mount.attach")
        return
    runtime_manifest = REGISTRY.runtime_manifest()
    for href in runtime_manifest["css"]:
        await websocket.send_json({"type": "runtime.css", "href": href})
    await websocket.send_json({"type": "runtime.import", "module": "@mutgui/antd"})
    await websocket.send_json({"type": "runtime.install", "module": "@mutgui/theme-dark"})
    await websocket.send_json({"type": "runtime.mount"})
    vp = ViewPort(view, StarletteChannel(websocket))
    viewports.append(vp)
    await vp.initialize()
    await view.rendered()
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            await vp.handle_event(event)
    except Exception:
        pass
    finally:
        vp.detach()
        viewports.remove(vp)


REGISTRY = ModuleRegistry()
REGISTRY.add_from_package("mutgui")


def _json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _index_html() -> str:
    runtime_manifest = REGISTRY.runtime_manifest()
    import_map = {"imports": runtime_manifest["importMap"]}
    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mutgui + Starlette</title>
</head>
  <body>
  <div style="max-width: 600px; margin: 40px auto; font-family: sans-serif;">
    <div id="app" data-mutgui-app data-ws-url="/ws"></div>
  </div>
  <script type="importmap">{_json_script(import_map)}</script>
  <script src="{REGISTRY.url_for("mutgui", "boot.js")}"></script>
</body>
</html>
"""


async def index(_request: Any) -> HTMLResponse:
    return HTMLResponse(_index_html())


routes = [
    Route("/", index),
    WebSocketRoute("/ws", ws_handler),
]
for path, directory in REGISTRY.static_mounts():
    routes.append(Mount(path, StaticFiles(directory=str(directory))))

app = Starlette(routes=routes)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="127.0.0.1", port=port)
