"""浏览器系统事件集成测试——mount.attach 握手 + $hashchange 事件。"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from playwright.async_api import expect

from mutgui import View, ViewBlock, Callback
from mutgui.events import Event
from mutgui._view_impl import render_ext


pytestmark = pytest.mark.integration


class HashTrackerView(View):
    """记录所有收到的 $hashchange 事件，并提供 setHash 按钮。"""

    id = "hash-tracker"

    def __init__(self) -> None:
        super().__init__()
        self.hash_events: list[dict[str, Any]] = []

    def render(self) -> ViewBlock:
        latest = self.hash_events[-1] if self.hash_events else {"hash": "", "cause": "none"}
        return ViewBlock([
            {
                "$component": "div",
                "$id": "current-hash",
                "data-testid": "current-hash",
                "children": str(latest.get("hash", "")),
            },
            {
                "$component": "div",
                "$id": "current-cause",
                "data-testid": "current-cause",
                "children": str(latest.get("cause", "none")),
            },
            {
                "$component": "div",
                "$id": "event-count",
                "data-testid": "event-count",
                "children": str(len(self.hash_events)),
            },
            {
                "$component": "button",
                "$id": "go-foo-btn",
                "data-testid": "go-foo-btn",
                "children": "Go foo",
                "onClick": Callback(self._go_foo),
            },
            {
                "$component": "button",
                "$id": "go-bar-btn",
                "data-testid": "go-bar-btn",
                "children": "Go bar",
                "onClick": Callback(self._go_bar),
            },
        ])

    async def on_event(self, event: Event) -> bool:
        if event.name == "$hashchange":
            self.hash_events.append({**event.data})
            self.invalidate()
            return True
        # 非系统事件：走默认 handler 分派逻辑
        ext = render_ext(self)
        handler = ext.handlers.get((event.component_id, event.name))
        if handler is not None:
            return await handler.handle(self, event)
        return False

    async def _go_foo(self) -> None:
        await self.send_command("mutgui.setHash", hash="#/foo")

    async def _go_bar(self) -> None:
        await self.send_command("mutgui.setHash", hash="#/bar")


async def test_initial_hash_handshake_sends_initial_event(app, page):
    """首屏带 hash 加载 → 后端首次 on_event 收到 cause=initial, previousHash=null。"""
    view = HashTrackerView()
    url = app.mount(view)

    await page.goto(url + "#/initial-route")

    # 等待首屏 render 反映初始事件
    await expect(page.get_by_test_id("current-hash")).to_have_text("#/initial-route")
    await expect(page.get_by_test_id("current-cause")).to_have_text("initial")
    await expect(page.get_by_test_id("event-count")).to_have_text("1")

    # 后端状态验证
    assert len(view.hash_events) == 1
    evt = view.hash_events[0]
    assert evt["hash"] == "#/initial-route"
    assert evt["previousHash"] is None
    assert evt["cause"] == "initial"


async def test_initial_empty_hash_still_sends_initial_event(app, page):
    """初始 hash 为空也发送 cause=initial, hash="" 事件。"""
    view = HashTrackerView()
    url = app.mount(view)

    await page.goto(url)

    await expect(page.get_by_test_id("current-cause")).to_have_text("initial")
    await expect(page.get_by_test_id("event-count")).to_have_text("1")

    assert view.hash_events[0]["hash"] == ""
    assert view.hash_events[0]["previousHash"] is None
    assert view.hash_events[0]["cause"] == "initial"


async def test_user_hashchange_sends_user_event(app, page):
    """模拟用户改地址栏 hash → 后端收到 cause=user, previousHash=<old>。"""
    view = HashTrackerView()
    url = app.mount(view)

    await page.goto(url + "#/start")
    await expect(page.get_by_test_id("event-count")).to_have_text("1")

    # 通过 location.hash 赋值模拟用户手动改地址栏 hash
    await page.evaluate("location.hash = '#/changed'")
    await expect(page.get_by_test_id("current-hash")).to_have_text("#/changed")
    await expect(page.get_by_test_id("current-cause")).to_have_text("user")
    await expect(page.get_by_test_id("event-count")).to_have_text("2")

    last = view.hash_events[-1]
    assert last["hash"] == "#/changed"
    assert last["previousHash"] == "#/start"
    assert last["cause"] == "user"


async def test_set_hash_then_back_completes_round_trip_without_dup(app, page):
    """setHash 后再 history.go(-1) 触发 hashchange——验证闭环且不重复发事件。

    重点：
    - setHash (pushState) **不**触发任何 hashchange 事件（W3C 规范，防循环基础）
    - back 后只触发一次 $hashchange (cause=user)，popstate 不会导致重复
    """
    view = HashTrackerView()
    url = app.mount(view)

    await page.goto(url)
    await expect(page.get_by_test_id("event-count")).to_have_text("1")  # initial

    # 后端 setHash → URL 变，但不产生 $hashchange（pushState 不触发）
    await page.get_by_test_id("go-foo-btn").click()
    await page.wait_for_function("() => location.hash === '#/foo'")

    # 给点时间让可能的循环事件被捕获（如果有的话）
    await asyncio.sleep(0.15)
    assert len(view.hash_events) == 1, (
        f"setHash 不应触发 $hashchange，实际 events={view.hash_events}"
    )

    # 再 push 一次为后续 back 准备
    await page.get_by_test_id("go-bar-btn").click()
    await page.wait_for_function("() => location.hash === '#/bar'")
    await asyncio.sleep(0.15)
    assert len(view.hash_events) == 1

    # 点 back：#/bar → #/foo，触发一次 hashchange (cause=user)
    await page.go_back()
    await page.wait_for_function("() => location.hash === '#/foo'")
    await expect(page.get_by_test_id("event-count")).to_have_text("2")

    last = view.hash_events[-1]
    assert last["cause"] == "user"
    assert last["hash"] == "#/foo"
    assert last["previousHash"] == "#/bar"

    # 再给些时间验证 popstate 不会导致额外事件
    await asyncio.sleep(0.15)
    assert len(view.hash_events) == 2
