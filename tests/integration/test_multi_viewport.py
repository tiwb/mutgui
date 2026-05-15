"""多 viewport 测试 — 两个 page 连接同一 View，验证状态同步。

broadcast_command 集成验证：见 spec
docs/specifications/feature-view-broadcast-command.md
"""
from __future__ import annotations

import asyncio

import pytest
from playwright.async_api import expect

from mutgui import View, ViewBlock, Callback


pytestmark = pytest.mark.integration


class SharedCounterView(View):
    id = "shared-counter"

    def __init__(self) -> None:
        super().__init__()
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


# ---------------------------------------------------------------------------
# broadcast_command 集成测试
# ---------------------------------------------------------------------------

class HashBroadcastView(View):
    """点击后在后台 broadcast `mutgui.setHash` 并 invalidate。"""

    id = "hash-broadcast"

    def __init__(self) -> None:
        super().__init__()
        self.target_hash = ""

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Button", "$id": "go",
             "data-testid": "go-btn",
             "children": f"Goto {self.target_hash or 'idle'}",
             "onClick": Callback(self._goto)},
        ])

    async def _goto(self) -> None:
        self.target_hash = "#/settings/mcp"
        await self.broadcast_command("mutgui.setHash", hash=self.target_hash)
        self.invalidate()


async def test_broadcast_command_reaches_all_viewports(app, pages):
    """page1 触发 broadcast_command("mutgui.setHash", ...)，两个 page 的 URL hash 都更新。"""
    page1, page2 = pages
    view = HashBroadcastView()
    url = app.mount(view)

    await page1.goto(url)
    await page2.goto(url)
    await expect(page1.get_by_test_id("go-btn")).to_be_visible()
    await expect(page2.get_by_test_id("go-btn")).to_be_visible()

    # 初始：两个 page 的 URL hash 都为空
    assert (await page1.evaluate("location.hash")) == ""
    assert (await page2.evaluate("location.hash")) == ""

    # page1 触发后台 broadcast
    await page1.get_by_test_id("go-btn").click()

    # 两个 page 的 hash 均同步（轮询等待 WebSocket 消息到达）
    async def _wait_hash(p, expected: str, timeout: float = 3.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if (await p.evaluate("location.hash")) == expected:
                return
            await asyncio.sleep(0.05)
        actual = await p.evaluate("location.hash")
        raise AssertionError(f"hash != {expected!r}, got {actual!r}")

    await _wait_hash(page1, "#/settings/mcp")
    await _wait_hash(page2, "#/settings/mcp")


class MixedCommandView(View):
    """同时验证 send_command（仅当前）与 broadcast_command（所有）的作用域差异。

    用 mutgui.setHash 作为探针：带不同 hash 值区分两个路径，通过观察各
    page 的 location.hash 判断哪条命令送达。
    """

    id = "mixed-command"

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "antd.Button", "$id": "only-me",
             "data-testid": "only-me",
             "children": "send to me",
             "onClick": Callback(self._send_only)},
            {"$component": "antd.Button", "$id": "all",
             "data-testid": "all-btn",
             "children": "broadcast",
             "onClick": Callback(self._send_all)},
        ])

    async def _send_only(self) -> None:
        # send_command 只到当前 ViewPort
        await self.send_command("mutgui.setHash", hash="#/only-current")

    async def _send_all(self) -> None:
        await self.broadcast_command("mutgui.setHash", hash="#/everyone")


async def test_send_command_stays_on_current_viewport(app, pages):
    """回归验证：send_command 仍只发给触发那个 tab。

    触发顺序：page1 调 send_command → 只 page1 hash 变；
    再 page1 调 broadcast_command → 两个 page hash 都变。
    """
    page1, page2 = pages
    view = MixedCommandView()
    url = app.mount(view)

    await page1.goto(url)
    await page2.goto(url)
    await expect(page1.get_by_test_id("only-me")).to_be_visible()
    await expect(page2.get_by_test_id("only-me")).to_be_visible()

    async def _wait_hash(p, expected: str, timeout: float = 3.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if (await p.evaluate("location.hash")) == expected:
                return
            await asyncio.sleep(0.05)
        actual = await p.evaluate("location.hash")
        raise AssertionError(f"hash != {expected!r}, got {actual!r}")

    # 1) send_command 仅当前 viewport
    await page1.get_by_test_id("only-me").click()
    await _wait_hash(page1, "#/only-current")
    # 给 page2 一点时间（如果 bug 回归了会产生改变）
    await asyncio.sleep(0.3)
    assert (await page2.evaluate("location.hash")) == "", (
        "send_command 不应该到达 page2"
    )

    # 2) broadcast_command 两个 page 都到
    await page1.get_by_test_id("all-btn").click()
    await _wait_hash(page1, "#/everyone")
    await _wait_hash(page2, "#/everyone")


async def test_broadcast_after_one_viewport_detached(app, pages):
    """一个 page 关闭后，另一个仍能收到 broadcast。"""
    page1, page2 = pages
    view = HashBroadcastView()
    url = app.mount(view)

    await page1.goto(url)
    await page2.goto(url)
    await expect(page1.get_by_test_id("go-btn")).to_be_visible()
    await expect(page2.get_by_test_id("go-btn")).to_be_visible()

    # 关闭 page2 (detach 其 ViewPort)
    await page2.close()
    # 给后端一点时间感知 disconnect
    await asyncio.sleep(0.2)

    # page1 触发 broadcast——应仍成功（不报错）且 page1 收到
    await page1.get_by_test_id("go-btn").click()

    deadline = asyncio.get_event_loop().time() + 3.0
    while asyncio.get_event_loop().time() < deadline:
        if (await page1.evaluate("location.hash")) == "#/settings/mcp":
            break
        await asyncio.sleep(0.05)
    assert (await page1.evaluate("location.hash")) == "#/settings/mcp"
