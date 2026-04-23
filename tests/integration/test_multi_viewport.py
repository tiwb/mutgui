"""多 viewport 测试 — 两个 page 连接同一 View，验证状态同步。"""
from __future__ import annotations

import pytest
from playwright.async_api import expect

from mutgui import View, ViewBlock, Callback


pytestmark = pytest.mark.integration


class SharedCounterView(View):
    id = "shared-counter"

    def __init__(self) -> None:
        self.count = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Button", "$id": "inc",
             "data-testid": "inc-btn",
             "children": f"Count: {self.count}",
             "onClick": Callback(self._increment)},
            {"$component": "antd.Typography.Text", "$id": "display",
             "data-testid": "display",
             "children": f"Value is {self.count}"},
        ])

    def _increment(self) -> None:
        self.count += 1
        self.invalidate()


async def test_two_viewports_sync(app, pages):
    """两个浏览器页面连同一 View，一端点击另一端看到更新。"""
    page1, page2 = pages
    view = SharedCounterView()
    url = app.mount(view)

    await page1.goto(url)
    await page2.goto(url)

    btn1 = page1.get_by_test_id("inc-btn")
    btn2 = page2.get_by_test_id("inc-btn")
    await expect(btn1).to_have_text("Count: 0")
    await expect(btn2).to_have_text("Count: 0")

    # page1 点击，page2 应该同步更新
    await btn1.click()
    await expect(btn1).to_have_text("Count: 1")
    await expect(btn2).to_have_text("Count: 1")
    assert view.count == 1

    # page2 点击，page1 应该同步更新
    await btn2.click()
    await expect(btn1).to_have_text("Count: 2")
    await expect(btn2).to_have_text("Count: 2")
    assert view.count == 2
