"""菜单系统单元测试。"""

import asyncio
from typing import Any
import mutobj

from mutgui import (
    View, ViewBlock, ViewPort, Channel, Callback, Expr,
    MenuView, MenuTrigger,
)
from mutgui._view_impl import ViewRenderState


class MockChannel(Channel):
    messages: list[dict[str, Any]] = mutobj.field(default_factory=list)

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


# ---------------------------------------------------------------------------
# MenuTrigger 序列化
# ---------------------------------------------------------------------------

class _Menu(MenuView):
    def render(self) -> ViewBlock:
        return ViewBlock([])


def test_menu_trigger_to_wire_minimal() -> None:
    mt = MenuTrigger(_Menu)
    assert mt.to_wire(0) == {"$handler": 0, "menu": True}


def test_menu_trigger_to_wire_with_context() -> None:
    mt = MenuTrigger(_Menu, item_id=Expr.wire("$0.target.dataset.id"))
    assert mt.to_wire(0) == {
        "$handler": 0,
        "kwargs": {"item_id": "$0.target.dataset.id"},
        "menu": True,
    }


def test_menu_trigger_to_wire_with_placement() -> None:
    mt = MenuTrigger(_Menu, placement="bottom-start")
    assert mt.to_wire(0) == {
        "$handler": 0,
        "menu": True,
        "placement": "bottom-start",
    }


def test_menu_trigger_to_wire_with_additional_placements() -> None:
    mt = MenuTrigger(_Menu, placement="right-start")
    assert mt.to_wire(0) == {
        "$handler": 0,
        "menu": True,
        "placement": "right-start",
    }

    mt = MenuTrigger(_Menu, placement="top-end")
    assert mt.to_wire(0) == {
        "$handler": 0,
        "menu": True,
        "placement": "top-end",
    }


def test_menu_trigger_to_wire_skips_direct_kwarg() -> None:
    """direct env kwarg 不序列化到 wire（只在本端 forward 给 menu_factory）。"""
    sentinel = object()
    mt = MenuTrigger(_Menu, item_id=Expr.wire("$0.target.id"), session=sentinel)
    wire = mt.to_wire(0)
    assert wire["kwargs"]["item_id"] == "$0.target.id"
    assert "session" not in wire.get("kwargs", {})


# ---------------------------------------------------------------------------
# MenuView 标识
# ---------------------------------------------------------------------------

def test_menu_view_id_has_menu_prefix() -> None:
    m = _Menu()
    assert isinstance(m.id, str) and m.id.startswith("$menu:")


def test_menu_view_ids_are_unique() -> None:
    a = _Menu()
    b = _Menu()
    assert a.id != b.id


# ---------------------------------------------------------------------------
# 完整流程：trigger → 注入 → render → close
# ---------------------------------------------------------------------------

class TabMenu(MenuView):
    item_id: str
    delete_called: bool

    def __init__(self, item_id: str = "?") -> None:
        super().__init__()
        self.item_id = item_id
        self.delete_called = False

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "mutgui.Menu.Item", "$id": "del",
             "label": f"Delete {self.item_id}",
             "onClick": Callback(self._on_delete)},
        ])

    def _on_delete(self) -> None:
        self.delete_called = True


class Page(View):
    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "html.div", "$id": "pane",
            "onContextMenu": MenuTrigger(
                TabMenu, item_id=Expr.wire("$0.target.dataset.id"),
            ),
        }])


def test_trigger_creates_and_pushes_menu() -> None:
    async def _t() -> None:
        page = Page()
        chan = MockChannel()
        vp = ViewPort(page, chan)
        await vp.initialize()
        await page.rendered()
        chan.messages.clear()

        await vp.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-42"},
        })
        await page.rendered()

        # 根 View 重新 push，含菜单 $view 引用
        root_msgs = [f for m in chan.messages if m.get("type") == "render"
                     for f in m.get("frames", []) if f["viewId"] == []]
        assert len(root_msgs) == 1
        assert any(node.get("$view", "").startswith("$menu:")
                   for node in root_msgs[0]["tree"])

        # 菜单 View 也 push 了
        menu_msgs = [f for m in chan.messages if m.get("type") == "render"
                     for f in m.get("frames", [])
                     if isinstance(f["viewId"], list) and f["viewId"]
                     and isinstance(f["viewId"][0], str)
                     and f["viewId"][0].startswith("$menu:")]
        assert len(menu_msgs) == 1
        # 菜单内容包含正确 item_id
        items = menu_msgs[0]["tree"]
        assert items[0]["label"] == "Delete tab-42"

        # overlay_children 已注册
        state = ViewRenderState.get(page)
        assert len(state.overlay_children) == 1

    asyncio.run(_t())


def test_menu_item_click_routes_to_menu_view() -> None:
    """点击菜单项 → 路由到 MenuView 内的 Callback。"""
    async def _t() -> None:
        page = Page()
        chan = MockChannel()
        vp = ViewPort(page, chan)
        await vp.initialize()
        await page.rendered()

        await vp.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-1"},
        })
        await page.rendered()

        state = ViewRenderState.get(page)
        menu = list(state.overlay_children.values())[0]
        assert isinstance(menu, TabMenu)

        await vp.handle_event({
            "source": [menu.id, "del"],
            "event": "onClick",
            "handlerId": 0,
            "data": {},
        })
        await page.rendered()

        assert menu.delete_called

    asyncio.run(_t())


def test_close_event_removes_menu() -> None:
    """$close 事件移除菜单 + 清理 ViewPort。"""
    async def _t() -> None:
        page = Page()
        chan = MockChannel()
        vp = ViewPort(page, chan)
        await vp.initialize()
        await page.rendered()

        await vp.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-1"},
        })
        await page.rendered()

        state = ViewRenderState.get(page)
        menu_id = list(state.overlay_children.keys())[0]

        chan.messages.clear()
        await vp.handle_event({
            "source": [menu_id, ""],
            "event": "$close",
            "handlerId": 0,
            "data": {},
        })
        await page.rendered()

        # 菜单已移除
        assert len(state.overlay_children) == 0

        # 根 View 重新 push 不含菜单引用
        root_msgs = [f for m in chan.messages if m.get("type") == "render"
                     for f in m.get("frames", []) if f["viewId"] == []]
        assert len(root_msgs) >= 1
        last = root_msgs[-1]
        assert not any(
            isinstance(node, dict) and str(node.get("$view", "")).startswith("$menu:")
            for node in last["tree"]
        )

    asyncio.run(_t())


def test_second_trigger_closes_first_menu() -> None:
    """连续触发：旧菜单关闭，新菜单打开。"""
    async def _t() -> None:
        page = Page()
        chan = MockChannel()
        vp = ViewPort(page, chan)
        await vp.initialize()
        await page.rendered()

        await vp.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-A"},
        })
        await page.rendered()
        state = ViewRenderState.get(page)
        first_id = list(state.overlay_children.keys())[0]

        await vp.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-B"},
        })
        await page.rendered()

        assert len(state.overlay_children) == 1
        new_id = list(state.overlay_children.keys())[0]
        assert new_id != first_id
        new_menu = state.overlay_children[new_id]
        assert isinstance(new_menu, TabMenu) and new_menu.item_id == "tab-B"

    asyncio.run(_t())


def test_direct_kwarg_passes_through_to_factory() -> None:
    """重构后：direct kwarg 透传给 menu_factory，替代旧 `view="@view"` 注入。

    原机制 (`@view` -> dispatch 期注入宿主 view) 重构后由用户在 render() 中
    直接写 `view=self` 达成，无需任何 "注入" 魔法。
    """
    captured: dict[str, Any] = {}

    class _M(MenuView):
        def __init__(self, view: Any) -> None:
            super().__init__()
            captured["view"] = view

        def render(self) -> ViewBlock:
            return ViewBlock([])

    class _P(View):
        def render(self) -> ViewBlock:
            return ViewBlock([{
                "$component": "html.div", "$id": "x",
                "onContextMenu": MenuTrigger(_M, view=self),
            }])

    async def _t() -> None:
        page = _P()
        chan = MockChannel()
        vp = ViewPort(page, chan)
        await vp.initialize()
        await page.rendered()

        await vp.handle_event({
            "source": ["x"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {},
        })
        await page.rendered()

        assert captured["view"] is page

    asyncio.run(_t())


# ---------------------------------------------------------------------------
# Per-viewport 作用域隔离
# ---------------------------------------------------------------------------

def _root_render_msg(chan: MockChannel) -> dict[str, Any] | None:
    """取最后一条发往根 View 的 render 消息的根帧 tree。"""
    for m in reversed(chan.messages):
        if m.get("type") != "render":
            continue
        for f in m.get("frames", []):
            if f.get("viewId") == []:
                return f["tree"]
    return None


def _menu_refs(tree: list[dict[str, Any]]) -> list[str]:
    """提取 wire tree 顶层 $menu: 前缀的 $view id。"""
    return [str(n["$view"]) for n in tree
            if isinstance(n, dict) and str(n.get("$view", "")).startswith("$menu:")]


def test_menu_only_renders_on_origin_viewport() -> None:
    """viewport A 触发菜单，viewport B 不应看到该菜单。"""
    async def _t() -> None:
        page = Page()
        chan_a = MockChannel()
        chan_b = MockChannel()
        vp_a = ViewPort(page, chan_a)
        vp_b = ViewPort(page, chan_b)
        await vp_a.initialize()
        await vp_b.initialize()
        await page.rendered()
        chan_a.messages.clear()
        chan_b.messages.clear()

        # A 触发菜单
        await vp_a.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-A"},
        })
        await page.rendered()

        # A 看到菜单 $view
        a_root = _root_render_msg(chan_a)
        assert a_root is not None
        assert _menu_refs(a_root)

        # B 也被重推（overlay_children 变化 → invalidate）但不包含菜单节点
        b_root = _root_render_msg(chan_b)
        assert b_root is not None
        assert _menu_refs(b_root) == []

        # 菜单 push 只在 A 的 channel上发生
        a_menu_msgs = [m for m in chan_a.messages
                       if m.get("type") == "render"
                       and any(isinstance(f.get("viewId"), list) and f["viewId"]
                               and isinstance(f["viewId"][0], str)
                               and f["viewId"][0].startswith("$menu:")
                               for f in m.get("frames", []))]
        b_menu_msgs = [m for m in chan_b.messages
                       if m.get("type") == "render"
                       and any(isinstance(f.get("viewId"), list) and f["viewId"]
                               and isinstance(f["viewId"][0], str)
                               and f["viewId"][0].startswith("$menu:")
                               for f in m.get("frames", []))]
        assert len(a_menu_msgs) == 1
        assert len(b_menu_msgs) == 0

    asyncio.run(_t())


def test_two_viewports_open_independent_menus() -> None:
    """A/B 各自触发同一菜单：不互相关闭，各看自己的。"""
    async def _t() -> None:
        page = Page()
        chan_a = MockChannel()
        chan_b = MockChannel()
        vp_a = ViewPort(page, chan_a)
        vp_b = ViewPort(page, chan_b)
        await vp_a.initialize()
        await vp_b.initialize()
        await page.rendered()

        await vp_a.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-A"},
        })
        await page.rendered()
        state = ViewRenderState.get(page)
        assert len(state.overlay_children) == 1
        menu_a_id = list(state.overlay_children.keys())[0]
        menu_a = state.overlay_children[menu_a_id]
        assert getattr(menu_a, "origin_channel_id") == chan_a.channel_id

        # B 触发同一菜单：不应关闭 A 的
        await vp_b.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-B"},
        })
        await page.rendered()

        assert len(state.overlay_children) == 2
        ids = list(state.overlay_children.keys())
        assert menu_a_id in ids
        # 另一个是 B 的
        other = next(state.overlay_children[i] for i in ids if i != menu_a_id)
        assert getattr(other, "origin_channel_id") == chan_b.channel_id

        # 取最后一次推送：A 只看到 menu_a，B 只看到 menu_b
        a_root = _root_render_msg(chan_a)
        b_root = _root_render_msg(chan_b)
        assert a_root is not None and b_root is not None
        a_refs = _menu_refs(a_root)
        b_refs = _menu_refs(b_root)
        assert a_refs == [menu_a_id]
        assert len(b_refs) == 1 and b_refs[0] != menu_a_id

    asyncio.run(_t())


def test_a_retrigger_does_not_close_b_menu() -> None:
    """A 重复触发只关闭 A 自己的菜单，B 的菜单保持不变。"""
    async def _t() -> None:
        page = Page()
        chan_a = MockChannel()
        chan_b = MockChannel()
        vp_a = ViewPort(page, chan_a)
        vp_b = ViewPort(page, chan_b)
        await vp_a.initialize()
        await vp_b.initialize()
        await page.rendered()

        # A 、B 各自触发
        await vp_a.handle_event({
            "source": ["pane"], "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-A"}})
        await page.rendered()
        await vp_b.handle_event({
            "source": ["pane"], "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-B"}})
        await page.rendered()

        state = ViewRenderState.get(page)
        b_menu = next(m for m in state.overlay_children.values()
                      if getattr(m, "origin_channel_id") == chan_b.channel_id)
        b_id = b_menu.id

        # A 再次触发
        await vp_a.handle_event({
            "source": ["pane"], "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-A2"}})
        await page.rendered()

        # B 的菜单还在
        assert b_id in state.overlay_children
        # 总数：A 的新菜单 + B 的原菜单 = 2
        assert len(state.overlay_children) == 2

    asyncio.run(_t())


def test_detach_cleans_up_origin_menus() -> None:
    """viewport detach 时关闭本 viewport 触发的菜单，不影响其他。"""
    async def _t() -> None:
        page = Page()
        chan_a = MockChannel()
        chan_b = MockChannel()
        vp_a = ViewPort(page, chan_a)
        vp_b = ViewPort(page, chan_b)
        await vp_a.initialize()
        await vp_b.initialize()
        await page.rendered()

        await vp_a.handle_event({
            "source": ["pane"], "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-A"}})
        await page.rendered()
        await vp_b.handle_event({
            "source": ["pane"], "event": "onContextMenu",
            "handlerId": 0,
            "data": {"item_id": "tab-B"}})
        await page.rendered()

        state = ViewRenderState.get(page)
        assert len(state.overlay_children) == 2

        # A 断连
        vp_a.detach()

        # 仅剩 B 的菜单
        assert len(state.overlay_children) == 1
        remaining = next(iter(state.overlay_children.values()))
        assert getattr(remaining, "origin_channel_id") == chan_b.channel_id

    asyncio.run(_t())
