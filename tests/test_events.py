"""事件系统的单元测试。"""

import asyncio
from typing import Any

import pytest

from mutgui.events import (
    Event,
    EventHandler,
    Callback,
    Bind,
    EventFilter,
)
from mutgui.expr import Expr
from mutgui._expr_impl import (
    parse_host_expr,
    eval_host_expr,
)


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

def test_event_fields() -> None:
    e = Event("btn", "onClick", {"x": 1})
    assert e.component_id == "btn"
    assert e.name == "onClick"
    assert e.data == {"x": 1}


# ---------------------------------------------------------------------------
# Expr 工厂 + 校验
# ---------------------------------------------------------------------------

def test_expr_wire_basic() -> None:
    e = Expr.wire("$0.target.value")
    assert e.env == "wire"
    assert e.source == "$0.target.value"


def test_expr_wire_rejects_non_str() -> None:
    with pytest.raises(TypeError):
        Expr.wire(123)  # type: ignore[arg-type]


def test_expr_wire_rejects_missing_dollar_prefix() -> None:
    with pytest.raises(ValueError):
        Expr.wire("target.value")


def test_expr_host_basic() -> None:
    e = Expr.host("event.viewport_id")
    assert e.env == "host"
    assert e.source == "event.viewport_id"


def test_expr_host_rejects_invalid_syntax() -> None:
    with pytest.raises(ValueError):
        Expr.host("event +")


def test_expr_direct_via_constructor() -> None:
    """direct 通过自动包装产生，但显式构造也合法。"""
    e = Expr(env="direct", source=42)
    assert e.env == "direct"
    assert e.source == 42


def test_expr_frozen_and_hashable() -> None:
    e1 = Expr.wire("$0.x")
    e2 = Expr.wire("$0.x")
    assert e1 == e2
    assert hash(e1) == hash(e2)
    assert {e1, e2} == {e1}


# ---------------------------------------------------------------------------
# parse_host_expr — 白名单 + 拒绝路径
# ---------------------------------------------------------------------------

def test_parse_host_expr_name_only() -> None:
    assert parse_host_expr("event") == (("name", "event"),)


def test_parse_host_expr_attribute_chain() -> None:
    assert parse_host_expr("event.viewport_id") == (
        ("name", "event"),
        ("attr", "viewport_id"),
    )


def test_parse_host_expr_with_index() -> None:
    assert parse_host_expr("event.touches[0].x") == (
        ("name", "event"),
        ("attr", "touches"),
        ("index", 0),
        ("attr", "x"),
    )


def test_parse_host_expr_rejects_string_index() -> None:
    with pytest.raises(ValueError, match="integer index"):
        parse_host_expr('event.data["key"]')


def test_parse_host_expr_rejects_negative_index() -> None:
    # -1 is UnaryOp(USub, 1), not Constant(-1)
    with pytest.raises(ValueError, match="integer index"):
        parse_host_expr("event.touches[-1]")


def test_parse_host_expr_rejects_bool_index() -> None:
    # bool is a subclass of int — explicitly excluded
    with pytest.raises(ValueError, match="integer index"):
        parse_host_expr("event.flags[True]")


def test_parse_host_expr_rejects_arithmetic() -> None:
    with pytest.raises(ValueError):
        parse_host_expr("event.x + 1")


def test_parse_host_expr_rejects_call() -> None:
    with pytest.raises(ValueError):
        parse_host_expr("event.x()")


def test_parse_host_expr_rejects_constant_root() -> None:
    with pytest.raises(ValueError, match="must start with a name"):
        parse_host_expr("42")


def test_parse_host_expr_rejects_syntax_error() -> None:
    with pytest.raises(ValueError, match="Invalid host expr"):
        parse_host_expr("event +")


# ---------------------------------------------------------------------------
# eval_host_expr
# ---------------------------------------------------------------------------

def test_eval_host_expr_attribute() -> None:
    e = Event("btn", "onClick", {}, viewport_id=7)
    assert eval_host_expr("event.viewport_id", {"event": e}) == 7


def test_eval_host_expr_index_chain() -> None:
    class Touch:
        def __init__(self, x: int) -> None:
            self.x = x

    class Payload:
        touches = [Touch(1), Touch(2), Touch(3)]

    assert eval_host_expr(
        "event.touches[1].x", {"event": Payload()}
    ) == 2


def test_eval_host_expr_unknown_name() -> None:
    with pytest.raises(NameError, match="unknown name"):
        eval_host_expr("missing.x", {"event": object()})


# ---------------------------------------------------------------------------
# EventHandler（基类，只提取不消费）
# ---------------------------------------------------------------------------

def test_event_handler_to_wire_with_wire_expr() -> None:
    h = EventHandler(value=Expr.wire("$0.target.value"))
    assert h.to_wire() == {"$handler": {"value": "$0.target.value"}}


def test_event_handler_to_wire_empty() -> None:
    h = EventHandler()
    assert h.to_wire() == {"$handler": {}}


def test_event_handler_direct_kwarg_not_in_wire() -> None:
    """direct env 的参数不写入 wire payload。"""
    h = EventHandler(view="some_obj", count=42)
    assert h.to_wire() == {"$handler": {}}


def test_event_handler_does_not_consume() -> None:
    async def _test() -> None:
        h = EventHandler(value=Expr.wire("$0.target.value"))
        e = Event("x", "onChange", {"value": "test"})
        result = await h.handle(None, e)  # type: ignore[arg-type]
        assert result is False

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Callback — to_wire
# ---------------------------------------------------------------------------

def test_callback_to_wire_no_args() -> None:
    cb = Callback(lambda: None)
    assert cb.to_wire() == {"$handler": {}}


def test_callback_to_wire_positional_wire() -> None:
    cb = Callback(lambda x: None, Expr.wire("$0.target.value"))
    assert cb.to_wire() == {"$handler": {"$args": ["$0.target.value"]}}


def test_callback_to_wire_keyword_wire() -> None:
    cb = Callback(
        lambda start, end: None,
        start=Expr.wire("$0.start"),
        end=Expr.wire("$0.end"),
    )
    inner = cb.to_wire()["$handler"]
    assert inner["start"] == "$0.start"
    assert inner["end"] == "$0.end"


def test_callback_to_wire_mixed_envs() -> None:
    """direct / host 不出现在 wire；只有 wire 写入。"""
    cb = Callback(
        lambda *a, **k: None,
        Expr.wire("$0.x"),
        "literal",  # direct positional
        Expr.wire("$0.y"),
        view="self_ref",  # direct kwarg
        viewport_id=Expr.host("event.viewport_id"),  # host kwarg
        value=Expr.wire("$0.target.value"),  # wire kwarg
    )
    wire = cb.to_wire()["$handler"]
    assert wire["$args"] == ["$0.x", "$0.y"]
    assert wire["value"] == "$0.target.value"
    assert "view" not in wire
    assert "viewport_id" not in wire


# ---------------------------------------------------------------------------
# Callback — handle
# ---------------------------------------------------------------------------

def test_callback_handle_positional_wire() -> None:
    received: list[Any] = []

    def fn(*args: Any) -> None:
        received.extend(args)

    async def _test() -> None:
        cb = Callback(fn, Expr.wire("$0.target.value"))
        e = Event("x", "onChange", {"$args": ["hello"]})
        result = await cb.handle(None, e)  # type: ignore[arg-type]
        assert result is True
        assert received == ["hello"]

    asyncio.run(_test())


def test_callback_handle_keyword_wire() -> None:
    received: dict[str, Any] = {}

    def fn(**kwargs: Any) -> None:
        received.update(kwargs)

    async def _test() -> None:
        cb = Callback(
            fn,
            start=Expr.wire("$0.start"),
            end=Expr.wire("$0.end"),
        )
        e = Event("x", "onViewport", {"start": 0, "end": 10})
        await cb.handle(None, e)  # type: ignore[arg-type]
        assert received == {"start": 0, "end": 10}

    asyncio.run(_test())


def test_callback_handle_direct_kwarg() -> None:
    """direct kwarg：直接 forward 构造时持有的值。"""
    received: dict[str, Any] = {}
    sentinel = object()

    def fn(**kwargs: Any) -> None:
        received.update(kwargs)

    async def _test() -> None:
        cb = Callback(fn, view=sentinel, count=42)
        e = Event("x", "onClick", {})
        await cb.handle(None, e)  # type: ignore[arg-type]
        assert received["view"] is sentinel
        assert received["count"] == 42

    asyncio.run(_test())


def test_callback_handle_host_kwarg() -> None:
    """host kwarg：从 dispatch context 按 expr walk。"""
    received: dict[str, Any] = {}

    def fn(**kwargs: Any) -> None:
        received.update(kwargs)

    async def _test() -> None:
        cb = Callback(fn, viewport_id=Expr.host("event.viewport_id"))
        e = Event("x", "onClick", {}, viewport_id=99)
        await cb.handle(None, e)  # type: ignore[arg-type]
        assert received == {"viewport_id": 99}

    asyncio.run(_test())


def test_callback_handle_mixed_positional() -> None:
    """direct / wire 位置参数顺序还原。"""
    received: list[Any] = []

    def fn(*args: Any) -> None:
        received.extend(args)

    async def _test() -> None:
        cb = Callback(
            fn,
            Expr.wire("$0.x"),
            "const",
            Expr.wire("$0.y"),
        )
        e = Event("x", "onMove", {"$args": [10, 20]})
        await cb.handle(None, e)  # type: ignore[arg-type]
        assert received == [10, "const", 20]

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


def test_callback_construct_does_not_validate_types() -> None:
    """重构后 Callback 接受任意类型 kwarg，无构造期类型校验。"""
    Callback(lambda **k: None, view=object(), count=42, label="x")


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------

def test_bind_to_wire_str_shorthand() -> None:
    obj = type("Obj", (), {"name": ""})()
    b = Bind(obj, "name", "$0.target.value")
    assert b.to_wire() == {"$handler": {"$args": ["$0.target.value"]}}


def test_bind_to_wire_explicit_expr() -> None:
    obj = type("Obj", (), {"name": ""})()
    b = Bind(obj, "name", Expr.wire("$0.target.value"))
    assert b.to_wire() == {"$handler": {"$args": ["$0.target.value"]}}


def test_bind_to_wire_default_path() -> None:
    obj = type("Obj", (), {"x": 0})()
    b = Bind(obj, "x")
    assert b.to_wire() == {"$handler": {"$args": ["$0"]}}


def test_bind_rejects_non_str_non_expr() -> None:
    obj = type("Obj", (), {"x": 0})()
    with pytest.raises(TypeError):
        Bind(obj, "x", 123)  # type: ignore[arg-type]


def test_bind_rejects_host_expr() -> None:
    obj = type("Obj", (), {"x": 0})()
    with pytest.raises(TypeError, match="wire"):
        Bind(obj, "x", Expr.host("event.x"))


def test_bind_rejects_str_without_dollar_prefix() -> None:
    obj = type("Obj", (), {"x": 0})()
    with pytest.raises(ValueError):
        Bind(obj, "x", "target.value")


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
