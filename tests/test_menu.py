"""菜单系统单元测试。"""

import asyncio
from typing import Any

from mutgui import (
    View, ViewBlock, ViewPort, Channel, Callback,
    MenuView, MenuTrigger,
)
from mutgui._view_impl import ViewRenderState


class MockChannel(Channel):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[dict[str, Any]] = []

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
    assert mt.to_wire() == {"$handler": {"$menu": True}}


def test_menu_trigger_to_wire_with_context() -> None:
    mt = MenuTrigger(_Menu, item_id="$0.target.dataset.id")
    assert mt.to_wire() == {
        "$handler": {"$menu": True, "item_id": "$0.target.dataset.id"},
    }


def test_menu_trigger_to_wire_with_placement() -> None:
    mt = MenuTrigger(_Menu, placement="bottom-start")
    assert mt.to_wire() == {
        "$handler": {"$menu": True, "$placement": "bottom-start"},
    }


def test_menu_trigger_to_wire_with_additional_placements() -> None:
    mt = MenuTrigger(_Menu, placement="right-start")
    assert mt.to_wire() == {
        "$handler": {"$menu": True, "$placement": "right-start"},
    }

    mt = MenuTrigger(_Menu, placement="top-end")
    assert mt.to_wire() == {
        "$handler": {"$menu": True, "$placement": "top-end"},
    }


def test_menu_trigger_rejects_invalid_placement() -> None:
    try:
        MenuTrigger(_Menu, placement="bottom")
    except ValueError as exc:
        assert "invalid menu placement" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid placement")


def test_menu_trigger_to_wire_skips_backend_inject() -> None:
    """@-prefix 提取路径只在后端使用，不应序列化到 wire。"""
    mt = MenuTrigger(_Menu, item_id="$0.target.id", session="@view.session")
    wire = mt.to_wire()
    assert wire["$handler"]["item_id"] == "$0.target.id"
    assert "session" not in wire["$handler"]


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
            "$component": "div", "$id": "pane",
            "onContextMenu": MenuTrigger(TabMenu, item_id="$0.target.dataset.id"),
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
            "data": {"$menu": True, "item_id": "tab-42"},
        })
        await page.rendered()

        # 根 View 重新 push，含菜单 $view 引用
        root_msgs = [m for m in chan.messages if m["viewId"] == []]
        assert len(root_msgs) == 1
        assert any(node.get("$view", "").startswith("$menu:")
                   for node in root_msgs[0]["tree"])

        # 菜单 View 也 push 了
        menu_msgs = [m for m in chan.messages
                     if isinstance(m["viewId"], list) and m["viewId"]
                     and isinstance(m["viewId"][0], str)
                     and m["viewId"][0].startswith("$menu:")]
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
            "data": {"$menu": True, "item_id": "tab-1"},
        })
        await page.rendered()

        state = ViewRenderState.get(page)
        menu = list(state.overlay_children.values())[0]
        assert isinstance(menu, TabMenu)

        await vp.handle_event({
            "source": [menu.id, "del"],
            "event": "onClick",
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
            "data": {"$menu": True, "item_id": "tab-1"},
        })
        await page.rendered()

        state = ViewRenderState.get(page)
        menu_id = list(state.overlay_children.keys())[0]

        chan.messages.clear()
        await vp.handle_event({
            "source": [menu_id, ""],
            "event": "$close",
            "data": {},
        })
        await page.rendered()

        # 菜单已移除
        assert len(state.overlay_children) == 0

        # 根 View 重新 push 不含菜单引用
        root_msgs = [m for m in chan.messages if m["viewId"] == []]
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
            "data": {"$menu": True, "item_id": "tab-A"},
        })
        await page.rendered()
        state = ViewRenderState.get(page)
        first_id = list(state.overlay_children.keys())[0]

        await vp.handle_event({
            "source": ["pane"],
            "event": "onContextMenu",
            "data": {"$menu": True, "item_id": "tab-B"},
        })
        await page.rendered()

        assert len(state.overlay_children) == 1
        new_id = list(state.overlay_children.keys())[0]
        assert new_id != first_id
        new_menu = state.overlay_children[new_id]
        assert isinstance(new_menu, TabMenu) and new_menu.item_id == "tab-B"

    asyncio.run(_t())


def test_backend_inject_extract_uses_at_prefix() -> None:
    """@view 注入：MenuTrigger.handle 应把宿主 view 注入到 context。"""
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
                "$component": "div", "$id": "x",
                "onContextMenu": MenuTrigger(_M, view="@view"),
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
            "data": {"$menu": True},
        })
        await page.rendered()

        assert captured["view"] is page

    asyncio.run(_t())
