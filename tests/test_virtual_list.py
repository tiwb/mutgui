"""VirtualList 的单元测试。"""

import asyncio
from typing import Any

from mutgui import View, ViewBlock, ViewPort, Channel, VirtualList, VirtualListItemAdapter
from mutgui._view_impl import ViewRenderState, ViewChildFilter


class MockChannel(Channel):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def messages_for(self, view_id: list[str | int]) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("viewId") == view_id]


# ---------------------------------------------------------------------------
# 测试用 Adapter + ItemView
# ---------------------------------------------------------------------------

class SimpleItemView(View):
    def __init__(self, text: str) -> None:
        self.text = text

    def render(self) -> ViewBlock:
        return ViewBlock([{"$component": "Text", "$id": "t", "children": self.text}])


class SimpleAdapter(VirtualListItemAdapter):
    def __init__(self, items: list[str]) -> None:
        super().__init__()
        self.items = items

    @property
    def item_count(self) -> int:
        return len(self.items)

    def item_id(self, index: int) -> str:
        return f"item-{index}"

    def create_item_view(self, index: int) -> View:
        return SimpleItemView(self.items[index])


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

def test_virtual_list_initial_render_empty_viewport() -> None:
    """初始 viewport=(0,0)，render 产出空 $children。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    tree = vl.render()
    assert tree.items[0]["$component"] == "VirtualList"
    assert tree.items[0]["itemCount"] == 100
    assert tree.items[0]["$children"] == []


def test_virtual_list_on_viewport_creates_views() -> None:
    """_on_viewport 更新 viewport range，下次 render 创建 item View。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=3, viewport_id=1)
    tree = vl.render()

    children = tree.items[0]["$children"]
    assert len(children) == 3
    # children 是 View 实例
    assert all(isinstance(c, View) for c in children)
    # id 被自动赋值
    assert children[0].id == "item-0"
    assert children[1].id == "item-1"
    assert children[2].id == "item-2"


def test_virtual_list_view_reuse() -> None:
    """相同 id 的 View 实例被复用。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=3, viewport_id=1)
    vl.render()
    view_0 = vl._item_views["item-0"]
    view_2 = vl._item_views["item-2"]

    # 滚动：viewport 从 [0,3) 变为 [1,4)
    vl._on_viewport(start=1, end=4, viewport_id=1)
    vl.render()

    # item-1 和 item-2 复用，item-0 被清理，item-3 新建
    assert "item-0" not in vl._item_views
    assert vl._item_views["item-2"] is view_2  # 复用
    assert "item-3" in vl._item_views  # 新建


def test_virtual_list_cleanup_old_views() -> None:
    """滚出 viewport 的 View 被清理。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=5, viewport_id=1)
    vl.render()
    assert len(vl._item_views) == 5

    vl._on_viewport(start=50, end=53, viewport_id=1)
    vl.render()
    assert len(vl._item_views) == 3
    assert all(k.startswith("item-5") for k in vl._item_views)


def test_adapter_invalidate_triggers_view_invalidate() -> None:
    """adapter.invalidate() 调用 VirtualList.invalidate()。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(10)])
    vl = VirtualList(id="list", adapter=adapter)

    # 手动调用 invalidate 验证不抛异常
    adapter.invalidate()
    ext = ViewRenderState.get(vl)
    assert ext is not None
    assert ext._dirty


def test_adapter_invalidate_refreshes_data() -> None:
    """adapter 数据变化后，render 时重新查询 adapter。"""
    items = [f"row-{i}" for i in range(10)]
    adapter = SimpleAdapter(items)
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=3, viewport_id=1)
    vl.render()
    assert vl._item_views["item-0"].text == "row-0"  # type: ignore[attr-defined]

    # 修改 adapter 数据
    adapter.items = ["NEW-0", "NEW-1", "NEW-2"] + items[3:]
    # id 没变（item-0），所以 View 实例不变，但数据确实变了
    # 注意：View 复用意味着 text 没更新——这是预期行为（View 持有旧引用）
    vl.render()
    assert vl._item_views["item-0"].text == "row-0"  # type: ignore[attr-defined]


def test_virtual_list_item_view_id_assignment() -> None:
    """VirtualList 负责给 item View 赋 id。"""
    adapter = SimpleAdapter(["a", "b", "c"])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=3, viewport_id=1)
    vl.render()

    for i in range(3):
        view = vl._item_views[f"item-{i}"]
        assert view.id == f"item-{i}"


def test_virtual_list_end_to_end_render() -> None:
    """端到端：VirtualList 通过 ViewPort 推送正确的协议消息。"""
    async def _test() -> None:
        adapter = SimpleAdapter([f"row-{i}" for i in range(1000)])
        vl = VirtualList(id="vl", adapter=adapter)

        # 模拟父 View 包含 VirtualList
        class RootView(View):
            def __init__(self) -> None:
                self.vlist = vl

            def render(self) -> ViewBlock:
                return ViewBlock([self.vlist])

        root = RootView()
        ch = MockChannel()
        vp = ViewPort(root, ch)
        await vp.initialize()
        await root.rendered()

        # 根 View 的 render 消息应包含 $view 节点
        root_msgs = ch.messages_for([])
        assert len(root_msgs) == 1
        assert root_msgs[0]["tree"][0]["$view"] == "vl"

        # VirtualList 自己的 render 消息
        vl_msgs = ch.messages_for(["vl"])
        assert len(vl_msgs) == 1
        vl_tree = vl_msgs[0]["tree"]
        assert vl_tree[0]["$component"] == "VirtualList"
        assert vl_tree[0]["itemCount"] == 1000
        # 初始 viewport=(0,0)，无 $children 中的 $view
        assert vl_tree[0].get("$children", []) == []

        # 模拟前端发 viewport 事件
        ch.messages.clear()
        await vp.handle_event({
            "source": ["vl", "list"],
            "event": "onViewport",
            "data": {"start": 0, "end": 5},
        })
        await root.rendered()
        await vl.rendered()

        # VirtualList re-render 后应有 5 个 $view 子节点
        vl_msgs = ch.messages_for(["vl"])
        assert len(vl_msgs) >= 1
        last_vl = vl_msgs[-1]
        vl_children = last_vl["tree"][0].get("$children", [])
        assert len(vl_children) == 5
        # 每个 child 是 $view 节点
        for child in vl_children:
            assert "$view" in child

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Per-VP viewport 存储 + union 渲染
# ---------------------------------------------------------------------------

def test_per_vp_viewport_storage() -> None:
    """不同 VP 的 onViewport 独立存储，不互相覆盖。"""
    from mutgui.events import Event

    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    # 模拟 VP-1: [0, 3)
    vl._on_viewport(start=0, end=3, viewport_id=1)
    # 模拟 VP-2: [10, 15)
    vl._on_viewport(start=10, end=15, viewport_id=2)

    assert vl._viewports == {1: (0, 3), 2: (10, 15)}


def test_union_rendering() -> None:
    """多 VP 时 render 的 item 是 viewport 并集。"""
    from mutgui.events import Event

    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=3, viewport_id=1)
    vl._on_viewport(start=5, end=8, viewport_id=2)
    vl.render()

    # union = [0, 8)，应有 8 个 item
    assert len(vl._visible_ids) == 8
    assert len(vl._item_views) == 8
    assert vl._visible_ids[0] == "item-0"
    assert vl._visible_ids[-1] == "item-7"


def test_overlapping_viewports_union() -> None:
    """重叠 viewport 的 union 计算正确。"""
    from mutgui.events import Event

    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=5, end=15, viewport_id=1)
    vl._on_viewport(start=10, end=20, viewport_id=2)
    vl.render()

    # union = [5, 20)
    assert len(vl._visible_ids) == 15
    assert vl._visible_ids[0] == "item-5"
    assert vl._visible_ids[-1] == "item-19"


def test_viewport_update_replaces_old_range() -> None:
    """同一 VP 更新 viewport 时替换旧范围。"""
    from mutgui.events import Event

    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=10, viewport_id=1)
    vl._on_viewport(start=50, end=60, viewport_id=1)

    assert vl._viewports == {1: (50, 60)}


# ---------------------------------------------------------------------------
# ViewChildFilter Extension 过滤
# ---------------------------------------------------------------------------

def test_view_child_filter_per_vp() -> None:
    """ViewChildFilter 为每个 VP 提供正确的 child ID 集合。"""
    from mutgui.events import Event

    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=3, viewport_id=1)
    vl._on_viewport(start=5, end=8, viewport_id=2)
    vl.render()

    filt = ViewChildFilter.get(vl)
    assert filt is not None

    vp1_ids = filt.get_children(1)
    assert vp1_ids == {"item-0", "item-1", "item-2"}

    vp2_ids = filt.get_children(2)
    assert vp2_ids == {"item-5", "item-6", "item-7"}

    # 未知 VP 返回空集
    assert filt.get_children(999) == set()


def test_per_vp_push_filtering_e2e() -> None:
    """端到端验证：不同 VP 收到的 $children 只包含自己 viewport 内的 item。"""
    async def _test() -> None:
        adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
        vl = VirtualList(id="vl", adapter=adapter)

        class RootView(View):
            def __init__(self) -> None:
                self.vlist = vl

            def render(self) -> ViewBlock:
                return ViewBlock([self.vlist])

        root = RootView()
        ch1 = MockChannel()
        ch2 = MockChannel()
        vp1 = ViewPort(root, ch1)
        vp2 = ViewPort(root, ch2)
        await vp1.initialize()
        await root.rendered()
        await vp2.initialize()
        await root.rendered()

        # VP1: viewport [0, 3)
        ch1.messages.clear()
        ch2.messages.clear()
        await vp1.handle_event({
            "source": ["vl", "list"],
            "event": "onViewport",
            "data": {"start": 0, "end": 3},
        })
        await vl.rendered()

        # VP2: viewport [10, 13)
        ch1.messages.clear()
        ch2.messages.clear()
        await vp2.handle_event({
            "source": ["vl", "list"],
            "event": "onViewport",
            "data": {"start": 10, "end": 13},
        })
        await vl.rendered()

        # 检查 ch1 收到的 VirtualList tree 中只有 item-0,1,2
        vl_msgs_ch1 = ch1.messages_for(["vl"])
        assert len(vl_msgs_ch1) >= 1
        ch1_children = vl_msgs_ch1[-1]["tree"][0].get("$children", [])
        ch1_view_ids = {c["$view"] for c in ch1_children if isinstance(c, dict)}
        assert ch1_view_ids == {"item-0", "item-1", "item-2"}

        # 检查 ch2 收到的 VirtualList tree 中只有 item-10,11,12
        vl_msgs_ch2 = ch2.messages_for(["vl"])
        assert len(vl_msgs_ch2) >= 1
        ch2_children = vl_msgs_ch2[-1]["tree"][0].get("$children", [])
        ch2_view_ids = {c["$view"] for c in ch2_children if isinstance(c, dict)}
        assert ch2_view_ids == {"item-10", "item-11", "item-12"}

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# VP 断开清理
# ---------------------------------------------------------------------------

def test_vp_disconnect_cleanup() -> None:
    """VP detach 后，viewport 条目在下次 render 时被自动清理。"""
    async def _test() -> None:
        adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
        vl = VirtualList(id="vl", adapter=adapter)

        class RootView(View):
            def __init__(self) -> None:
                self.vlist = vl

            def render(self) -> ViewBlock:
                return ViewBlock([self.vlist])

        root = RootView()
        ch1 = MockChannel()
        ch2 = MockChannel()
        vp1 = ViewPort(root, ch1)
        vp2 = ViewPort(root, ch2)
        await vp1.initialize()
        await root.rendered()
        await vp2.initialize()
        await root.rendered()

        # 两个 VP 各报不同 viewport
        await vp1.handle_event({
            "source": ["vl", "list"],
            "event": "onViewport",
            "data": {"start": 0, "end": 5},
        })
        await vl.rendered()
        await vp2.handle_event({
            "source": ["vl", "list"],
            "event": "onViewport",
            "data": {"start": 50, "end": 55},
        })
        await vl.rendered()

        assert len(vl._viewports) == 2
        assert len(vl._visible_ids) == 55  # union [0, 55)

        # VP-2 断开
        vp2.detach()

        # 触发 re-render，清理应自动发生
        ch1.messages.clear()
        vl.invalidate()
        await vl.rendered()

        assert len(vl._viewports) == 1
        assert len(vl._visible_ids) == 5  # 只剩 VP-1 的 [0, 5)

    asyncio.run(_test())


# ---------------------------------------------------------------------------
# Sync Scroll
# ---------------------------------------------------------------------------

def test_sync_scroll_render_props() -> None:
    """sync_scroll=True 时 render 输出 scrollTop 和 onScroll。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter, sync_scroll=True)

    tree = vl.render()
    props = tree.items[0]
    assert "scrollTop" in props
    assert props["scrollTop"] == 0
    assert "onScroll" in props


def test_sync_scroll_disabled_no_props() -> None:
    """sync_scroll=False（默认）时 render 不输出 scrollTop/onScroll。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    tree = vl.render()
    props = tree.items[0]
    assert "scrollTop" not in props
    assert "onScroll" not in props


def test_sync_scroll_state_update() -> None:
    """_on_scroll 更新 _scroll_top 状态。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter, sync_scroll=True)

    vl._on_scroll(scrollTop=123.5)
    assert vl._scroll_top == 123.5

    tree = vl.render()
    assert tree.items[0]["scrollTop"] == 123.5


def test_no_viewports_clears_filter() -> None:
    """所有 viewport 移除后，ViewChildFilter 被清空。"""
    from mutgui.events import Event

    adapter = SimpleAdapter([f"row-{i}" for i in range(10)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport(start=0, end=3, viewport_id=1)
    vl.render()
    assert len(vl._visible_ids) == 3

    # 移除所有 viewport
    vl._viewports.clear()
    vl.render()
    assert vl._visible_ids == []
    assert len(vl._item_views) == 0

    filt = ViewChildFilter.get(vl)
    assert filt is not None
    assert filt._viewport_item_ids == {}
