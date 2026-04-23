"""Button 点击 → 后端事件触发 → 前后端状态断言。"""
from __future__ import annotations

import pytest
from playwright.async_api import expect

from mutgui import View, ViewBlock, Callback


pytestmark = pytest.mark.integration


class CounterView(View):
    id = "counter"

    def __init__(self) -> None:
        self.count = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Button", "$id": "inc",
             "data-testid": "inc-btn",
             "children": f"Count: {self.count}",
             "onClick": Callback(self._increment)},
        ])

    def _increment(self) -> None:
        self.count += 1
        self.invalidate()


async def test_button_click(app, page):
    """点击按钮，验证前端文本更新 + 后端状态变化。"""
    view = CounterView()
    url = app.mount(view)
    await page.goto(url)

    btn = page.get_by_test_id("inc-btn")
    await expect(btn).to_have_text("Count: 0")
    assert view.count == 0

    await btn.click()
    await expect(btn).to_have_text("Count: 1")
    assert view.count == 1

    await btn.click()
    await btn.click()
    await expect(btn).to_have_text("Count: 3")
    assert view.count == 3


class ToggleView(View):
    id = "toggle"

    def __init__(self) -> None:
        self.visible = False

    def render(self) -> ViewBlock:
        items: list = [
            {"$component": "antd.Button", "$id": "toggle-btn",
             "data-testid": "toggle-btn",
             "children": "Toggle",
             "onClick": Callback(self._toggle)},
        ]
        if self.visible:
            items.append(
                {"$component": "antd.Typography.Text", "$id": "secret",
                 "data-testid": "secret-text",
                 "children": "Hello World"},
            )
        return ViewBlock(items)

    def _toggle(self) -> None:
        self.visible = not self.visible
        self.invalidate()


async def test_conditional_render(app, page):
    """点击切换按钮，验证条件渲染的 DOM 元素出现/消失。"""
    view = ToggleView()
    url = app.mount(view)
    await page.goto(url)

    secret = page.get_by_test_id("secret-text")
    await expect(secret).to_have_count(0)
    assert view.visible is False

    await page.get_by_test_id("toggle-btn").click()
    await expect(secret).to_be_visible()
    assert view.visible is True

    await page.get_by_test_id("toggle-btn").click()
    await expect(secret).to_have_count(0)
    assert view.visible is False
