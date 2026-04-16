"""mutgui demo — 纯 Python 单文件 demo。

启动::

    cd mutgui/demo
    python app.py

然后打开 http://localhost:8765
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from mutgui import View, ViewSession, Transport, bind, handler


# ---------------------------------------------------------------------------
# Transport 实现
# ---------------------------------------------------------------------------

class WebSocketTransport(Transport):
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws

    async def send(self, message: dict[str, Any]) -> None:
        await self.ws.send_json(message)


# ---------------------------------------------------------------------------
# 示例 View
# ---------------------------------------------------------------------------

class SignupView(View):
    def __init__(self) -> None:
        self.name = ""
        self.age = 18
        self.subscribe = False
        self.email = ""
        self.plan = "free"
        self.message = ""

    def render(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = [
            {"$component": "Form.Item", "id": "fi-name", "label": "Name",
             "children": [
                 {"$component": "Input", "id": "name", "value": self.name,
                  "placeholder": "Name",
                  "onChange": bind(self, "name", "$0.target.value")},
             ]},

            {"$component": "Form.Item", "id": "fi-age", "label": "Age",
             "children": [
                 {"$component": "InputNumber", "id": "age", "value": self.age,
                  "min": 0, "max": 150,
                  "onChange": bind(self, "age", "$0")},
             ]},

            {"$component": "Form.Item", "id": "fi-subscribe", "label": "Subscribe",
             "children": [
                 {"$component": "Checkbox", "id": "subscribe",
                  "checked": self.subscribe,
                  "onChange": bind(self, "subscribe", "$0.target.checked")},
             ]},
        ]

        if self.subscribe:
            items.append(
                {"$component": "Form.Item", "id": "fi-email", "label": "Email",
                 "children": [
                     {"$component": "Input", "id": "email", "value": self.email,
                      "placeholder": "Email",
                      "onChange": bind(self, "email", "$0.target.value")},
                 ]}
            )

        items.append(
            {"$component": "Form.Item", "id": "fi-plan", "label": "Plan",
             "children": [
                 {"$component": "Select", "id": "plan", "value": self.plan,
                  "style": {"width": 200},
                  "options": [
                      {"value": "free", "label": "Free"},
                      {"value": "pro", "label": "Pro"},
                      {"value": "enterprise", "label": "Enterprise"},
                  ],
                  "onChange": bind(self, "plan", "$0")},
             ]}
        )

        items.append(
            {"$component": "Form.Item", "id": "fi-submit",
             "children": [
                 {"$component": "Button", "id": "submit",
                  "type": "primary",
                  "children": "Submit",
                  "onClick": handler(self.on_submit)},
             ]}
        )

        if self.message:
            items.append(
                {"$component": "Typography.Text", "id": "msg", "children": self.message}
            )

        return [
            {"$component": "Form", "id": "form", "layout": "horizontal",
             "labelCol": {"span": 6}, "wrapperCol": {"span": 18},
             "children": items},
        ]

    def on_submit(self, _data: dict[str, Any]) -> None:
        self.message = f"Welcome {self.name} (age {self.age})! Plan: {self.plan}"


# ---------------------------------------------------------------------------
# WebSocket handler — 所有连接共享同一 view，事件后广播
# ---------------------------------------------------------------------------

view = SignupView()
sessions: list[ViewSession] = []


async def ws_handler(websocket: WebSocket) -> None:
    await websocket.accept()
    session = ViewSession(view, WebSocketTransport(websocket))
    sessions.append(session)
    await session.initialize()
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            await session.handle_event(event)
            for s in sessions:
                if s is not session:
                    try:
                        await s.push()
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        sessions.remove(session)


# ---------------------------------------------------------------------------
# HTML — 加载预构建 mutgui.js，Ant Design 真实渲染
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mutgui demo</title>
</head>
<body>
  <div style="max-width: 500px; margin: 40px auto; font-family: sans-serif;">
    <h2>mutgui demo</h2>
    <div id="app"></div>
  </div>
  <script src="/static/mutgui.js"></script>
  <script>MutguiApp.mount(document.getElementById('app'), `ws://${location.host}/ws`)</script>
</body>
</html>
"""


async def index(_request: Any) -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "mutgui" / "static"

app = Starlette(routes=[
    Route("/", index),
    WebSocketRoute("/ws", ws_handler),
    Mount("/static", StaticFiles(directory=str(STATIC_DIR))),
])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="127.0.0.1", port=port)
