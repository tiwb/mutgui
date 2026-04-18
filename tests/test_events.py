"""事件系统的单元测试。"""

import asyncio
from typing import Any

from mutgui.events import Event, EventHandler, Callback, Bind, EventFilter


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

def test_event_fields() -> None:
    e = Event("btn", "onClick", {"x": 1})
    assert e.component_id == "btn"
    assert e.name == "onClick"
    assert e.data == {"x": 1}


# ---------------------------------------------------------------------------
# EventHandler（基类，只提取不消费）
# ---------------------------------------------------------------------------

def test_event_handler_to_wire() -> None:
    h = EventHandler(value="$0.target.value")
    assert h.to_wire() == {"$handler": {"value": "$0.target.value"}}


def test_event_handler_to_wire_empty() -> None:
    h = EventHandler()
    assert h.to_wire() == {"$handler": {}}


def test_event_handler_does_not_consume() -> None:
    async def _test() -> None:
        h = EventHandler(value="$0.target.value")
        e = Event("x", "onChange", {"value": "test"})
        result = await h.handle(None, e)  # type: ignore[arg-type]
        assert result is False

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

def test_callback_to_wire_no_args() -> None:
    cb = Callback(lambda: None)
    assert cb.to_wire() == {"$handler": {}}


def test_callback_to_wire_positional() -> None:
    cb = Callback(lambda x: None, "$0.target.value")
    assert cb.to_wire() == {"$handler": {"$args": ["$0.target.value"]}}


def test_callback_to_wire_keyword() -> None:
    cb = Callback(lambda start, end: None, start="$0.start", end="$0.end")
    wire = cb.to_wire()
    assert "$handler" in wire
    inner = wire["$handler"]
    assert inner["start"] == "$0.start"
    assert inner["end"] == "$0.end"


def test_callback_to_wire_mixed() -> None:
    cb = Callback(lambda x, y, shift: None, "$0.x", "$0.y", shift="$0.shiftKey")
    wire = cb.to_wire()
    inner = wire["$handler"]
    assert inner["$args"] == ["$0.x", "$0.y"]
    assert inner["shift"] == "$0.shiftKey"


def test_callback_handle_positional() -> None:
    received: list[Any] = []

    def fn(*args: Any) -> None:
        received.extend(args)

    async def _test() -> None:
        cb = Callback(fn, "$0.target.value")
        e = Event("x", "onChange", {"$args": ["hello"]})
        result = await cb.handle(None, e)  # type: ignore[arg-type]
        assert result is True
        assert received == ["hello"]

    asyncio.run(_test())


def test_callback_handle_keyword() -> None:
    received: dict[str, Any] = {}

    def fn(**kwargs: Any) -> None:
        received.update(kwargs)

    async def _test() -> None:
        cb = Callback(fn, start="$0.start", end="$0.end")
        e = Event("x", "onViewport", {"start": 0, "end": 10})
        await cb.handle(None, e)  # type: ignore[arg-type]
        assert received == {"start": 0, "end": 10}

    asyncio.run(_test())


def test_callback_handle_no_args() -> None:
    called = [False]

    def fn() -> None:
        called[0] = True

    async def _test() -> None:
        cb = Callback(fn)
        e = Event("btn", "onClick", {})
        await cb.handle(None, e)  # type: ignore[arg-type]
        assert called[0] is True

    asyncio.run(_test())


def test_callback_handle_async() -> None:
    called = [False]

    async def fn() -> None:
        called[0] = True

    async def _test() -> None:
        cb = Callback(fn)
        e = Event("btn", "onClick", {})
        await cb.handle(None, e)  # type: ignore[arg-type]
        assert called[0] is True

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------

def test_bind_to_wire() -> None:
    obj = type("Obj", (), {"name": ""})()
    b = Bind(obj, "name", "$0.target.value")
    assert b.to_wire() == {"$handler": {"$args": ["$0.target.value"]}}


def test_bind_to_wire_default_path() -> None:
    obj = type("Obj", (), {"x": 0})()
    b = Bind(obj, "x")
    assert b.to_wire() == {"$handler": {"$args": ["$0"]}}


def test_bind_handle_setattr() -> None:
    obj = type("Obj", (), {"name": ""})()

    class FakeView:
        def invalidate(self) -> None:
            pass

    async def _test() -> None:
        b = Bind(obj, "name", "$0.target.value")
        e = Event("x", "onChange", {"$args": ["Alice"]})
        result = await b.handle(FakeView(), e)  # type: ignore[arg-type]
        assert result is True
        assert obj.name == "Alice"

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# EventFilter
# ---------------------------------------------------------------------------

def test_event_filter_default_does_not_consume() -> None:
    async def _test() -> None:
        f = EventFilter()
        e = Event("x", "onClick", {})
        result = await f.on_event_filter(None, e)  # type: ignore[arg-type]
        assert result is False

    asyncio.run(_test())
