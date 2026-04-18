"""mutgui demo — View 嵌套 + VirtualList 演示。

两个独立 View 并排（Profile + Subscription），
底部 VirtualList 显示记录列表（预填充 3000 条，可追加）。

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

from mutgui import (
    View, ViewBlock, ViewPort, Channel, Bind, Callback,
    VirtualList, VirtualListItemAdapter,
)


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

    def render(self) -> ViewBlock:
        self._render_count += 1
        return ViewBlock([
            {"$component": "Form", "$id": "form", "layout": "vertical",
             "$children": [
                 {"$component": "Form.Item", "$id": "fi-name", "label": "Name",
                  "$children": [
                      {"$component": "Input", "$id": "name", "value": self.name,
                       "placeholder": "Your name",
                       "onChange": Bind(self, "name", "$0.target.value")},
                  ]},
                 {"$component": "Form.Item", "$id": "fi-age", "label": "Age",
                  "$children": [
                      {"$component": "InputNumber", "$id": "age",
                       "value": self.age, "min": 0, "max": 150,
                       "onChange": Bind(self, "age", "$0")},
                  ]},
             ]},
            {"$component": "Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"render #{self._render_count}"},
        ])
# ---------------------------------------------------------------------------
# 子 View：订阅信息
# ---------------------------------------------------------------------------

class SubscriptionView(View):
    id = "subscription"

    def __init__(self) -> None:
        self.subscribe = False
        self.email = ""
        self.plan = "free"
        self._render_count = 0

    def render(self) -> ViewBlock:
        self._render_count += 1
        items: list[dict[str, Any]] = [
            {"$component": "Form.Item", "$id": "fi-sub", "label": "Subscribe",
             "$children": [
                 {"$component": "Checkbox", "$id": "subscribe",
                  "checked": self.subscribe,
                  "onChange": Bind(self, "subscribe", "$0.target.checked")},
             ]},
        ]

        if self.subscribe:
            items.append(
                {"$component": "Form.Item", "$id": "fi-email", "label": "Email",
                 "$children": [
                     {"$component": "Input", "$id": "email",
                      "value": self.email, "placeholder": "you@example.com",
                      "onChange": Bind(self, "email", "$0.target.value")},
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
                  "onChange": Bind(self, "plan", "$0")},
             ]}
        )

        return ViewBlock([
            {"$component": "Form", "$id": "form", "layout": "vertical",
             "$children": items},
            {"$component": "Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"render #{self._render_count}"},
        ])


# ---------------------------------------------------------------------------
# 记录列表 — VirtualList 演示
# ---------------------------------------------------------------------------

class RecordItemView(View):
    """单条记录的 View — 分列显示 + Edit/Delete 按钮。"""

    def __init__(self, index: int, name: str, age: int, plan: str,
                 on_edit: Any = None, on_delete: Any = None) -> None:
        self.index = index
        self.name = name
        self.age = age
        self.plan = plan
        self.on_edit = on_edit
        self.on_delete = on_delete

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "Row", "$id": "row",
            "wrap": False,
            "style": {"lineHeight": "32px", "flexWrap": "nowrap"},
            "$children": [
                {"$component": "Col", "$id": "c-idx", "flex": "50px",
                 "$children": [
                     {"$component": "Typography.Text", "$id": "idx",
                      "type": "secondary", "children": f"#{self.index}"},
                 ]},
                {"$component": "Col", "$id": "c-name", "flex": "auto",
                 "$children": [
                     {"$component": "Typography.Text", "$id": "name",
                      "children": self.name},
                 ]},
                {"$component": "Col", "$id": "c-age", "flex": "60px",
                 "$children": [
                     {"$component": "Typography.Text", "$id": "age",
                      "children": str(self.age)},
                 ]},
                {"$component": "Col", "$id": "c-plan", "flex": "100px",
                 "$children": [
                     {"$component": "Typography.Text", "$id": "plan",
                      "children": self.plan},
                 ]},
                {"$component": "Col", "$id": "c-actions", "flex": "none",
                 "$children": [
                     {"$component": "Space", "$id": "btns", "size": 4,
                      "$children": [
                          {"$component": "Button", "$id": "edit",
                           "size": "small", "children": "Edit",
                           "onClick": Callback(self._do_edit)},
                          {"$component": "Button", "$id": "del",
                           "size": "small", "danger": True,
                           "children": "Del",
                           "onClick": Callback(self._do_delete)},
                      ]},
                 ]},
            ],
        }])

    def _do_edit(self) -> None:
        if self.on_edit:
            self.on_edit(self.index)

    def _do_delete(self) -> None:
        if self.on_delete:
            self.on_delete(self.index)


class RecordAdapter(VirtualListItemAdapter):
    """记录列表的 adapter。"""

    def __init__(self, on_edit: Any = None, on_delete: Any = None) -> None:
        self.records: list[tuple[int, str, int, str]] = []  # (uid, name, age, plan)
        self.on_edit = on_edit
        self.on_delete = on_delete
        self._next_uid = 0
        # 预填充 100 条
        plans = ["Free", "Pro", "Enterprise"]
        for i in range(100):
            self._add(f"User-{i}", 18 + (i % 50), plans[i % 3])

    def _add(self, name: str, age: int, plan: str) -> None:
        self.records.append((self._next_uid, name, age, plan))
        self._next_uid += 1

    @property
    def item_count(self) -> int:
        return len(self.records)

    def item_id(self, index: int) -> str:
        return f"rec-{self.records[index][0]}"  # stable uid

    def create_item_view(self, index: int) -> View:
        uid, name, age, plan = self.records[index]
        return RecordItemView(
            index, name, age, plan,
            on_edit=self.on_edit, on_delete=self.on_delete,
        )

    def add_record(self, name: str, age: int, plan: str) -> None:
        self._add(name, age, plan)
        self.invalidate()

    def update_record(self, index: int, name: str, age: int, plan: str) -> None:
        uid = self.records[index][0]
        self.records[index] = (uid, name, age, plan)
        # 清除缓存的 View，下次 render 时用新数据重建
        item_id = self.item_id(index)
        if self._virtual_list and item_id in self._virtual_list._item_views:
            del self._virtual_list._item_views[item_id]
        self.invalidate()

    def delete_record(self, index: int) -> None:
        self.records.pop(index)
        self.invalidate()


# ---------------------------------------------------------------------------
# 根 View：两个子 View 并排 + VirtualList
# ---------------------------------------------------------------------------

class RootView(View):
    def __init__(self) -> None:
        self.profile = ProfileView()
        self.subscription = SubscriptionView()
        self.record_adapter = RecordAdapter(
            on_edit=self.on_edit, on_delete=self.on_delete,
        )
        self.record_list = VirtualList(
            id="records",
            adapter=self.record_adapter,
        )
        self.editing_index: int | None = None  # None=新增模式, int=编辑模式
        self.message = ""
        self._render_count = 0

    def on_edit(self, index: int) -> None:
        """Edit 按钮回调：加载记录到表单。"""
        _uid, name, age, plan = self.record_adapter.records[index]
        self.profile.name = name
        self.profile.age = age
        self.subscription.plan = plan
        self.editing_index = index
        self.message = f"Editing #{index}"
        self.profile.invalidate()
        self.subscription.invalidate()
        self.invalidate()

    def render(self) -> ViewBlock:
        self._render_count += 1
        is_editing = self.editing_index is not None
        btn_label = "Save" if is_editing else "Add"

        items: list[dict[str, Any]] = [
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
            {"$component": "Card", "$id": "card-add",
             "title": f"Records ({self.record_adapter.item_count})",
             "style": {"marginTop": 16},
             "bodyStyle": {"height": 400, "display": "flex",
                           "flexDirection": "column"},
             "$children": [
                 {"$component": "Space", "$id": "actions",
                  "$children": [
                      {"$component": "Button", "$id": "add",
                       "type": "primary", "children": btn_label,
                       "onClick": Callback(self.on_save)},
                  ]},
                 {"$component": "Divider", "$id": "div",
                  "style": {"margin": "12px 0"}},
                 self.record_list,
             ]},
        ]

        if is_editing:
            items[-1]["$children"][0]["$children"].append(
                {"$component": "Button", "$id": "cancel",
                 "children": "Cancel",
                 "onClick": Callback(self.on_cancel)},
            )

        if self.message:
            items[-1]["$children"][0]["$children"].append(
                {"$component": "Typography.Text", "$id": "msg",
                 "type": "success", "children": self.message},
            )

        items.append(
            {"$component": "Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"render #{self._render_count}"},
        )
        return ViewBlock(items)
    def on_save(self) -> None:
        p = self.profile
        s = self.subscription
        name = p.name or "Anonymous"
        if self.editing_index is not None:
            self.record_adapter.update_record(
                self.editing_index, name, p.age, s.plan,
            )
            self.message = f"Updated #{self.editing_index}"
            self.editing_index = None
        else:
            self.record_adapter.add_record(name, p.age, s.plan)
            self.message = f"Added: {name}, {p.age}, {s.plan}"
        self.invalidate()

    def on_cancel(self) -> None:
        self.editing_index = None
        self.message = ""
        self.invalidate()

    def on_delete(self, index: int) -> None:
        """Delete 按钮回调。"""
        if self.editing_index == index:
            self.editing_index = None
        elif self.editing_index is not None and self.editing_index > index:
            self.editing_index -= 1
        self.record_adapter.delete_record(index)
        self.message = f"Deleted #{index}"
        self.invalidate()


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
    await view.rendered()
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            await vp.handle_event(event)
            # invalidate() 自动 schedule render 并 push 给所有 ViewPort
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
  <title>mutgui demo — View Nesting + VirtualList</title>
</head>
<body>
  <div style="max-width: 800px; margin: 40px auto; font-family: sans-serif;">
    <h2>mutgui — View Nesting + VirtualList Demo</h2>
    <p style="color: #888; font-size: 13px;">
      Two independent Views side by side + a VirtualList with 3000 records.
      Click "Add" to append. Scroll the list to see virtual scrolling.
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
