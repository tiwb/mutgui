"""View.broadcast_command 单元测试。

spec: docs/specifications/feature-view-broadcast-command.md

覆盖：
- 无观察者 no-op
- 顺序遍历所有 ViewPort
- 单点失败不影响其余 ViewPort
- 不依赖 current_viewport 上下文（与 send_command 的关键差异）
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import mutobj
from mutgui import View, ViewBlock, ViewPort, Channel


class MockChannel(Channel):
    """记录所有 send 调用的 channel。"""
    messages: list[dict[str, Any]] = mutobj.field(default_factory=list)
    fail: bool

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail

    async def send(self, message: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("simulated channel failure")
        self.messages.append(message)


class EmptyView(View):
    id = "empty"

    def render(self) -> ViewBlock:
        return ViewBlock([])


# ---------------------------------------------------------------------------
# 无观察者 → no-op
# ---------------------------------------------------------------------------

def test_broadcast_no_observers_is_noop() -> None:
    view = EmptyView()

    async def run() -> None:
        # 无 ViewPort attached，应静默返回，不抛异常
        await view.broadcast_command("anything", x=1)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 顺序遍历所有 ViewPort，每个都收到命令帧
# ---------------------------------------------------------------------------

def test_broadcast_to_all_viewports() -> None:
    view = EmptyView()
    ch1 = MockChannel()
    ch2 = MockChannel()
    ch3 = MockChannel()

    async def run() -> None:
        ViewPort(view, ch1)
        ViewPort(view, ch2)
        ViewPort(view, ch3)
        await view.broadcast_command("mutgui.setHash", hash="#/x")

    asyncio.run(run())

    for ch in (ch1, ch2, ch3):
        assert len(ch.messages) == 1
        msg = ch.messages[0]
        assert msg["type"] == "command"
        assert msg["name"] == "mutgui.setHash"
        assert msg["args"] == {"hash": "#/x"}


# ---------------------------------------------------------------------------
# 单点失败：其余 ViewPort 仍收到，broadcast 自身不抛
# ---------------------------------------------------------------------------

def test_broadcast_single_failure_does_not_abort_others() -> None:
    view = EmptyView()
    ch_ok1 = MockChannel()
    ch_fail = MockChannel(fail=True)
    ch_ok2 = MockChannel()

    async def run() -> None:
        # 中间那个会抛，前后两个应该都收到
        ViewPort(view, ch_ok1)
        ViewPort(view, ch_fail)
        ViewPort(view, ch_ok2)
        # 不应该抛
        await view.broadcast_command("mutgui.setHash", hash="#/y")

    asyncio.run(run())

    assert len(ch_ok1.messages) == 1
    assert len(ch_ok2.messages) == 1
    assert ch_ok1.messages[0]["name"] == "mutgui.setHash"
    assert ch_ok2.messages[0]["name"] == "mutgui.setHash"
    # 失败的 channel 没记到 message
    assert ch_fail.messages == []


# ---------------------------------------------------------------------------
# 与 send_command 的关键差异：无 ViewPort 上下文也能调用
# ---------------------------------------------------------------------------

def test_broadcast_works_without_current_viewport_context() -> None:
    """broadcast_command 不依赖 get_current_viewport()。

    send_command 在没有 ViewPort 上下文时会抛 RuntimeError；
    broadcast_command 直接遍历 ViewObservers，可在后台任务、
    定时器、agent 回调中调用。
    """
    view = EmptyView()
    ch = MockChannel()

    async def run() -> None:
        ViewPort(view, ch)
        # 当前没有进入任何 ViewPort 上下文
        # send_command 会抛
        with pytest.raises(RuntimeError):
            await view.send_command("any", x=1)
        # broadcast_command 应正常工作
        await view.broadcast_command("any", x=1)

    asyncio.run(run())

    assert len(ch.messages) == 1
    assert ch.messages[0]["args"] == {"x": 1}
