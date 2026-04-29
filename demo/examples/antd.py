"""Ant Design 控件展示 — Form、Input、Select、Checkbox 等。"""
from __future__ import annotations

from typing import Any

from mutgui import View, ViewBlock, Bind, Callback

from demo.framework import MutguiRoute, DemoApp


class AntdFormView(View):
    name: str = ""
    age: int = 18
    subscribe: bool = False
    email: str = ""
    plan: str = "free"
    message: str = ""

    def render(self) -> ViewBlock:
        items: list[dict[str, Any]] = [
            {"$component": "antd.Form.Item", "$id": "fi-name", "label": "Name",
             "$children": [
                 {"$component": "antd.Input", "$id": "name", "value": self.name,
                  "placeholder": "Your name",
                  "onChange": Bind(self, "name", "$0.target.value")},
             ]},
            {"$component": "antd.Form.Item", "$id": "fi-age", "label": "Age",
             "$children": [
                 {"$component": "antd.InputNumber", "$id": "age",
                  "value": self.age, "min": 0, "max": 150,
                  "onChange": Bind(self, "age", "$0")},
             ]},
            {"$component": "antd.Form.Item", "$id": "fi-sub", "label": "Subscribe",
             "$children": [
                 {"$component": "antd.Checkbox", "$id": "subscribe",
                  "checked": self.subscribe,
                  "onChange": Bind(self, "subscribe", "$0.target.checked")},
             ]},
        ]

        if self.subscribe:
            items.append(
                {"$component": "antd.Form.Item", "$id": "fi-email", "label": "Email",
                 "$children": [
                     {"$component": "antd.Input", "$id": "email",
                      "value": self.email, "placeholder": "you@example.com",
                      "onChange": Bind(self, "email", "$0.target.value")},
                 ]}
            )

        items.append(
            {"$component": "antd.Form.Item", "$id": "fi-plan", "label": "Plan",
             "$children": [
                 {"$component": "antd.Select", "$id": "plan", "value": self.plan,
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
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3, "children": "mutgui — Ant Design Controls"},
            {"$component": "antd.Form", "$id": "form", "layout": "vertical",
             "$children": items},
            {"$component": "antd.Space", "$id": "actions",
             "$children": [
                 {"$component": "antd.Button", "$id": "submit",
                  "type": "primary", "children": "Submit",
                  "onClick": Callback(self._on_submit)},
             ]},
            *([{"$component": "antd.Typography.Text", "$id": "msg",
                "type": "success", "children": self.message}]
              if self.message else []),
        ])

    def _on_submit(self) -> None:
        self.message = (
            f"Submitted: {self.name}, age {self.age}, "
            f"plan={self.plan}, subscribe={self.subscribe}"
        )
        self.invalidate()


app = DemoApp([
    MutguiRoute("/", AntdFormView(), title="Ant Design Controls", layout="plain"),
])

if __name__ == "__main__":
    app.run()
