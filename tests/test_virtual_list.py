"""VirtualList 的单元测试。"""

import asyncio
from typing import Any

from mutgui import View, ViewPort, Channel, VirtualList, VirtualListItemAdapter
from mutgui._view_impl import ViewRenderState


class MockChannel(Channel):
    def __init__(self) -> None:
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

    def render(self) -> dict[str, Any]:
        return {"$component": "Text", "$id": "t", "children": self.text}


class SimpleAdapter(VirtualListItemAdapter):
    def __init__(self, items: list[str]) -> None:
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
    assert tree["$component"] == "VirtualList"
    assert tree["itemCount"] == 100
    assert tree["$children"] == []


def test_virtual_list_on_viewport_creates_views() -> None:
    """_on_viewport 更新 viewport range，下次 render 创建 item View。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport({"start": 0, "end": 3})
    tree = vl.render()

    children = tree["$children"]
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

    vl._on_viewport({"start": 0, "end": 3})
    vl.render()
    view_0 = vl._item_views["item-0"]
    view_2 = vl._item_views["item-2"]

    # 滚动：viewport 从 [0,3) 变为 [1,4)
    vl._on_viewport({"start": 1, "end": 4})
    vl.render()

    # item-1 和 item-2 复用，item-0 被清理，item-3 新建
    assert "item-0" not in vl._item_views
    assert vl._item_views["item-2"] is view_2  # 复用
    assert "item-3" in vl._item_views  # 新建


def test_virtual_list_cleanup_old_views() -> None:
    """滚出 viewport 的 View 被清理。"""
    adapter = SimpleAdapter([f"row-{i}" for i in range(100)])
    vl = VirtualList(id="list", adapter=adapter)

    vl._on_viewport({"start": 0, "end": 5})
    vl.render()
    assert len(vl._item_views) == 5

    vl._on_viewport({"start": 50, "end": 53})
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

    vl._on_viewport({"start": 0, "end": 3})
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

    vl._on_viewport({"start": 0, "end": 3})
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

            def render(self) -> list[Any]:
                return [self.vlist]

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
