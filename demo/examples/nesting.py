"""View 嵌套展示 — 父 View 包含子 View，独立渲染。"""
from __future__ import annotations

from typing import Any

import mutobj

from mutgui import View, ViewBlock, Bind

from demo.framework import MutguiRoute, DemoApp


class ProfileView(View):
    id: str | int = "profile"
    name: str = ""
    age: int = 18
    _render_count: int = 0

    def render(self) -> ViewBlock:
        self._render_count += 1
        return ViewBlock([
            {"$component": "antd.Form", "$id": "form", "layout": "vertical",
             "$children": [
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
             ]},
            {"$component": "antd.Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"render #{self._render_count}"},
        ])


class SubscriptionView(View):
    id: str | int = "subscription"
    subscribe: bool = False
    email: str = ""
    plan: str = "free"
    _render_count: int = 0

    def render(self) -> ViewBlock:
        self._render_count += 1
        items: list[dict[str, Any]] = [
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
            {"$component": "antd.Form", "$id": "form", "layout": "vertical",
             "$children": items},
            {"$component": "antd.Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"render #{self._render_count}"},
        ])


class NestingView(View):
    profile: ProfileView = mutobj.field(default_factory=ProfileView)
    subscription: SubscriptionView = mutobj.field(default_factory=SubscriptionView)
    _render_count: int = 0

    def render(self) -> ViewBlock:
        self._render_count += 1
        return ViewBlock([
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3, "children": "mutgui — View Nesting"},
            {"$component": "antd.Typography.Text", "$id": "desc",
             "type": "secondary",
             "children": "Two sub-views side by side. Each re-renders independently."},
            {"$component": "antd.Row", "$id": "row", "gutter": 16,
             "style": {"marginTop": 16},
             "$children": [
                 {"$component": "antd.Col", "$id": "col-left", "span": 12,
                  "$children": [
                      {"$component": "antd.Card", "$id": "card-profile",
                       "title": "Profile",
                       "$children": [self.profile]},
                  ]},
                 {"$component": "antd.Col", "$id": "col-right", "span": 12,
                  "$children": [
                      {"$component": "antd.Card", "$id": "card-sub",
                       "title": "Subscription",
                       "$children": [self.subscription]},
                  ]},
             ]},
            {"$component": "antd.Typography.Text", "$id": "counter",
             "type": "secondary",
             "children": f"root render #{self._render_count}"},
        ])


app = DemoApp([
    MutguiRoute("/", NestingView(), title="View Nesting", layout="plain"),
])

if __name__ == "__main__":
    app.run()
