"""View 事件路由的单元测试 — 重点覆盖根级事件 (source=[]) 的 EventFilter 链。

bugfix: docs/specifications/bugfix-root-event-filter-chain.md
"""

import asyncio
from typing import Any

import mutobj

from mutgui import (
    View,
    ViewBlock,
    ViewPort,
    Channel,
    Event,
    EventFilter,
)


class MockChannel(Channel):
    messages: list[dict[str, Any]] = mutobj.field(default_factory=list)

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


class RootView(View):
    """根 View，记录 on_event 触发情况。"""
    events_received: list[Event] = mutobj.field(default_factory=list)

    def render(self) -> ViewBlock:
        return ViewBlock([])

    async def on_event(self, event: Event) -> bool:
        self.events_received.append(event)
        return True


class RecordingFilter(EventFilter):
    """记录所有进入的事件，并按构造参数决定是否拦截。"""

    def __init__(self, *, intercept: bool = False, label: str = "") -> None:
        self.intercept = intercept
        self.label = label
        self.events_received: list[Event] = []

    async def on_event_filter(self, watched: View, event: Event) -> bool:
        self.events_received.append(event)
        return self.intercept


# ---------------------------------------------------------------------------
# 根级事件经过 EventFilter — filter 返回 False，on_event 被调用
# ---------------------------------------------------------------------------

def test_root_event_passes_through_filter() -> None:
    """根级事件 (source=[]) 经过 EventFilter，filter 返回 False 时 on_event 仍被调用。"""

    async def _test() -> None:
        channel = MockChannel()
        view = RootView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        f = RecordingFilter(intercept=False)
        view.install_event_filter(f)

        await vp.handle_event({
            "source": [],
            "event": "$hashchange",
            "data": {"hash": "#foo"},
        })

        # filter 看到事件
        assert len(f.events_received) == 1
        assert f.events_received[0].component_id == ""
        assert f.events_received[0].name == "$hashchange"
        assert f.events_received[0].kwargs == {"hash": "#foo"}

        # on_event 也被调用
        assert len(view.events_received) == 1
        assert view.events_received[0].name == "$hashchange"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 根级事件被 EventFilter 拦截 — filter 返回 True，on_event 不被调用
# ---------------------------------------------------------------------------

def test_root_event_intercepted_by_filter() -> None:
    """EventFilter 返回 True 时根级事件不再触达 on_event。"""

    async def _test() -> None:
        channel = MockChannel()
        view = RootView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        f = RecordingFilter(intercept=True)
        view.install_event_filter(f)

        await vp.handle_event({
            "source": [],
            "event": "$hashchange",
            "data": {"hash": "#bar"},
        })

        # filter 看到事件
        assert len(f.events_received) == 1
        # on_event 未被调用
        assert view.events_received == []

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# 多个 EventFilter 串联 — 第一个返回 True 后第二个不被调用（短路语义）
# ---------------------------------------------------------------------------

def test_root_event_filter_chain_short_circuits() -> None:
    """多 filter 串联，前一个返回 True 时后续 filter 与 on_event 都不再被调用。"""

    async def _test() -> None:
        channel = MockChannel()
        view = RootView()
        vp = ViewPort(view, channel)
        await vp.initialize()
        await view.rendered()

        f1 = RecordingFilter(intercept=True, label="f1")
        f2 = RecordingFilter(intercept=False, label="f2")
        view.install_event_filter(f1)
        view.install_event_filter(f2)

        await vp.handle_event({
            "source": [],
            "event": "$hashchange",
            "data": {},
        })

        # f1 看到事件并拦截
        assert len(f1.events_received) == 1
        # f2 因为 f1 拦截而未被调用
        assert f2.events_received == []
        # on_event 未被调用
        assert view.events_received == []

    asyncio.run(_test())
