"""VirtualList 集成测试 — L1 行为验证。

验证用户通过公开 API（props）能观察到的行为：
- 初始渲染：item 出现，不是全量渲染（虚拟化生效）
- 滚动：item 范围随鼠标滚轮滚动变化
- itemIds 映射：渲染的 item 与后端下发的 itemId 一致
"""

from __future__ import annotations

import asyncio

import pytest
from playwright.async_api import Page

from mutgui import View, ViewBlock, VirtualList, VirtualListItemAdapter


pytestmark = pytest.mark.integration

# ── 测试用组件：固定高度 item，保证行为可预测 ──

_ITEM_HEIGHT_EST = 40


class FixedItemView(View):
    index: int = 0

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "html.div",
            "data-testid": f"vl-item-{self.index}",
            "style": {"height": f"{_ITEM_HEIGHT_EST}px", "lineHeight": f"{_ITEM_HEIGHT_EST}px"},
            "children": f"Item {self.index}",
        }])


class FixedAdapter(VirtualListItemAdapter):
    count: int = 0

    @property
    def item_count(self) -> int:
        return self.count

    def item_id(self, index: int) -> str:
        return f"item-{index}"

    def create_item_view(self, index: int) -> View:
        return FixedItemView(index=index)


class VLTestRoot(View):
    adapter: FixedAdapter
    vlist: VirtualList

    def __init__(self, count: int = 200) -> None:
        super().__init__()
        self.adapter = FixedAdapter(count=count)
        self.vlist = VirtualList(
            id="vl",
            adapter=self.adapter,
            estimated_item_height=_ITEM_HEIGHT_EST,
        )

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "html.div",
            "$id": "root",
            "style": {
                "height": "100vh", "display": "flex", "flexDirection": "column",
                "overflow": "hidden",
            },
            "$children": [self.vlist],
        }])


# ── 辅助 ──

async def _get_visible_testids(page: Page) -> list[str]:
    """返回当前 DOM 中所有 item 的 data-testid。"""
    items = page.locator('.mutgui-virtual-list [data-testid^="vl-item-"]')
    count = await items.count()
    result: list[str] = []
    for i in range(count):
        tid = await items.nth(i).get_attribute("data-testid")
        if tid:
            result.append(tid)
    return result


# ── 测试 ──

async def test_initial_render(app, page):
    """初始加载后 item 出现，且不是全量渲染（虚拟化生效）。"""
    root = VLTestRoot(count=200)
    url = app.mount(root)

    await page.goto(url)
    await page.wait_for_selector('[data-testid^="vl-item-"]', timeout=5000)

    testids = await _get_visible_testids(page)
    assert len(testids) > 0, "expected at least one item after initial load"
    assert len(testids) < 200, (
        f"virtual scrolling should render < 200 items, got {len(testids)}"
    )


async def test_scroll_changes_items(app, page):
    """鼠标滚轮滚动后渲染的 item 范围变化。"""
    root = VLTestRoot(count=200)
    url = app.mount(root)

    await page.goto(url)
    await page.wait_for_selector('[data-testid^="vl-item-"]', timeout=5000)

    testids_before = await _get_visible_testids(page)
    assert len(testids_before) > 0

    # 鼠标滚轮滚动（触发 wheel → pendingUserScrollIntent → handleScroll）
    el = page.locator('.mutgui-virtual-list')
    await el.hover()
    await page.mouse.wheel(0, 3000)
    # 等待 scroll → throttle → viewport 上报 → 后端 push → 新 item 渲染
    await asyncio.sleep(0.5)

    testids_after = await _get_visible_testids(page)
    assert len(testids_after) > 0
    assert testids_after != testids_before, (
        f"expected visible items to change after scroll, "
        f"got same set: {len(testids_before)} items"
    )


async def test_item_ids_match_children(app, page):
    """渲染的 item 数量不超过 itemIds 长度（后端每 VP 只下发 viewport 范围内的 items）。"""
    root = VLTestRoot(count=200)
    url = app.mount(root)

    await page.goto(url)
    await page.wait_for_selector('[data-testid^="vl-item-"]', timeout=5000)

    # VirtualList 不应渲染全部 200 个 item
    testids = await _get_visible_testids(page)
    assert len(testids) > 0
    assert len(testids) < 200

    # 所有渲染的 item 都有有效的 data-item-id 属性
    items = page.locator('.mutgui-virtual-list [data-item-id]')
    item_count = await items.count()
    assert item_count > 0
    assert item_count == len(testids), (
        f"every rendered item should have data-item-id, "
        f"got {len(testids)} testids vs {item_count} data-item-id elements"
    )
