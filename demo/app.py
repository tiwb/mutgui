"""mutgui demo — View 嵌套演示。

两个独立 View 并排显示，各自独立更新。
每个 View 底部显示 render 次数，直观展示"改左边不影响右边"。

启动::

    cd mutgui/demo
    python app.py

然后打开 http://localhost:8080
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

from mutgui import View, ViewPort, Channel, bind, handler


# ---------------------------------------------------------------------------
# Channel 实现
# ---------------------------------------------------------------------------

class WebSocketChannel(Channel):
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws

    async def send(self, message: dict[str, Any]) -> None:
        await self.ws.send_json(message)


# ---------------------------------------------------------------------------
# 子 View：基本信息
# ---------------------------------------------------------------------------

class ProfileView(View):
    id = "profile"

    def __init__(self) -> None:
        self.name = ""
        self.age = 18
        self._render_count = 0

    def render(self) -> list[dict[str, Any]]:
        self._render_count += 1
        return [
            {"$component": "Form", "$id": "form", "layout": "vertical",
             "$children": [
                 {"$component": "Form.Item", "$id": "fi-name", "label": "Name",
                  "$children": [
                      {"$component": "Input", "$id": "name", "value": self.name,
                       "placeholder": "Your name",
                       "onChange": bind(self, "name", "$0.target.value")},
                  ]},
                 {"$component": "Form.Item", "$id": "fi-age", "label": "Age",
                  "$children": [
                      {"$component": "InputNumber", "$id": "age",
                       "value": self.age, "min": 0, "max": 150,
                       "onChange": bind(self, "age", "$0")},
                  ]},
             ]},
            {"$component": "Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"render #{self._render_count}"},
        ]


# ---------------------------------------------------------------------------
# 子 View：订阅信息
# ---------------------------------------------------------------------------

class SubscriptionView(View):
    id = "subscription"

    def __init__(self) -> None:
        self.subscribe = False
        self.email = ""
        self.plan = "free"
        self.message = ""
        self._render_count = 0

    def render(self) -> list[dict[str, Any]]:
        self._render_count += 1
        items: list[dict[str, Any]] = [
            {"$component": "Form.Item", "$id": "fi-sub", "label": "Subscribe",
             "$children": [
                 {"$component": "Checkbox", "$id": "subscribe",
                  "checked": self.subscribe,
                  "onChange": bind(self, "subscribe", "$0.target.checked")},
             ]},
        ]

        if self.subscribe:
            items.append(
                {"$component": "Form.Item", "$id": "fi-email", "label": "Email",
                 "$children": [
                     {"$component": "Input", "$id": "email",
                      "value": self.email, "placeholder": "you@example.com",
                      "onChange": bind(self, "email", "$0.target.value")},
                 ]}
            )

        items.append(
            {"$component": "Form.Item", "$id": "fi-plan", "label": "Plan",
             "$children": [
                 {"$component": "Select", "$id": "plan", "value": self.plan,
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
            {"$component": "Form.Item", "$id": "fi-submit",
             "$children": [
                 {"$component": "Button", "$id": "submit",
                  "type": "primary", "children": "Submit",
                  "onClick": handler(self.on_submit)},
             ]}
        )

        result: list[dict[str, Any]] = [
            {"$component": "Form", "$id": "form", "layout": "vertical",
             "$children": items},
        ]

        if self.message:
            result.append(
                {"$component": "Typography.Text", "$id": "msg",
                 "type": "success", "children": self.message}
            )

        result.append(
            {"$component": "Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"render #{self._render_count}"}
        )
        return result

    def on_submit(self, _data: dict[str, Any]) -> None:
        self.message = f"Plan: {self.plan}" + (
            f", email: {self.email}" if self.subscribe else ""
        )


# ---------------------------------------------------------------------------
# 根 View：两个子 View 并排
# ---------------------------------------------------------------------------

class RootView(View):
    def __init__(self) -> None:
        self.profile = ProfileView()
        self.subscription = SubscriptionView()

    def render(self) -> list[dict[str, Any]]:
        return [
            {"$component": "Row", "$id": "row", "gutter": 16,
             "$children": [
                 {"$component": "Col", "$id": "col-left", "span": 12,
                  "$children": [
                      {"$component": "Card", "$id": "card-profile",
                       "title": "Profile",
                       "$children": [self.profile]},
                  ]},
                 {"$component": "Col", "$id": "col-right", "span": 12,
                  "$children": [
                      {"$component": "Card", "$id": "card-sub",
                       "title": "Subscription",
                       "$children": [self.subscription]},
                  ]},
             ]},
        ]


# ---------------------------------------------------------------------------
# WebSocket handler — 所有连接共享同一 view，事件后自动通知
# ---------------------------------------------------------------------------

view = RootView()
viewports: list[ViewPort] = []


async def ws_handler(websocket: WebSocket) -> None:
    await websocket.accept()
    vp = ViewPort(view, WebSocketChannel(websocket))
    viewports.append(vp)
    await vp.initialize()
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            await vp.handle_event(event)
            # invalidate() 自动通知所有 ViewPort，
            # 但当前 flush 需要显式触发（异步调度待后续实现）
            for other in viewports:
                if other is not vp:
                    await other.flush()
    except Exception:
        pass
    finally:
        vp.detach()
        viewports.remove(vp)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>mutgui demo — View Nesting</title>
</head>
<body>
  <div style="max-width: 800px; margin: 40px auto; font-family: sans-serif;">
    <h2>mutgui — View Nesting Demo</h2>
    <p style="color: #888; font-size: 13px;">
      Two independent Views side by side. Editing one only re-renders that View
      (watch the render counters).
    </p>
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
