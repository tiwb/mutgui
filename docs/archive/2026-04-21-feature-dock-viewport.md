# DockPanel per-viewport 独立状态 设计规范

**状态**：✅ 已完成
**日期**：2026-04-21
**类型**：功能设计

## 需求

1. DockPanel 多客户端连接时，每个 viewport 应有独立的容器尺寸和坍缩状态
2. 当前问题：多个浏览器窗口大小不同时，resize 事件交替更新同一个 `_container_size`，导致反复坍缩/恢复翻转
3. 需要 per-viewport 布局计算和 wire tree 推送

### 前置依赖

- `feature-dock-panel.md` — DockPanel 基础功能（✅ 已完成）
- `feature-session-sharing.md` — 多客户端支持与 ViewChildFilter
- `feature-virtual-list.md` — per-viewport 状态追踪模式参考

## 关键参考

### 问题现象

多个浏览器窗口大小不同时，viewport A（宽屏）和 viewport B（窄屏）交替发送 resize 事件，后端 `_container_size` 在两个尺寸间翻转，导致坍缩状态不断切换。

### 内部实现

- **VirtualList per-viewport 模式** — `src/mutgui/virtual_list.py`，`_viewports: dict[channel_id, tuple]` + `render_viewport` override + `_refresh_visible()` 计算可见集合并集
- **VP push 机制** — `src/mutgui/_viewport_impl.py`，`_vp_push_render` 调用 `view.render_viewport(wire_tree, channel_id)` 获取 per-viewport wire tree
- **DockPanel 现有实现** — `src/mutgui/dock_panel.py`，`_container_size` 为单一 tuple，`_compute_layout` 一次计算
- **坍缩机制** — `_compute_layout` 返回临时树（不修改 `_layout`），坍缩 TabSetNode 复用原 SplitNode 的 ID。坍缩态 active tab 存在 `_collapsed_active`，tab 顺序存在 `_collapsed_orders`

## 设计方案

### 核心思路

View 基类提供 `render_viewport(wire_tree, channel_id)` 虚函数。`render()` 产出模板树（一次），`render_viewport()` 在每次 push 时为每个 viewport 调用，返回该 viewport 应收到的 wire tree。默认原样返回，子类覆写实现 per-viewport 差异化。

这是 `render()` 的自然延伸——render 产出"应该长什么样"，render_viewport 产出"对这个 viewport 应该长什么样"。

### 状态共享模型

**共享**（存在 `_layout` 原始树上，一个 viewport 改动所有 viewport 可见）：
- 布局树结构（SplitNode/TabSetNode 嵌套关系）
- 面板归属（哪个面板在哪个 TabSet）
- 分割比例（SplitNode.ratio）
- 非坍缩态的活跃 tab（TabSetNode.active_id）

对应事件：tab_move、tab_dock、edge_dock、split_resize、tab_switch（非坍缩态）、tab_reorder（非坍缩态）

**per-viewport 隔离**（各自独立，互不影响）：
- 容器尺寸（window/container size）
- 坍缩状态（由尺寸 + ratio + collapse_below 计算得出，不需额外存储）
- 坍缩态活跃 tab（坍缩合并后的 TabSet 里用户选中了哪个）
- 坍缩态 tab 顺序（坍缩合并后用户重排的顺序）

对应事件：resize、tab_switch（坍缩态）、tab_reorder（坍缩态）

### 框架层：render_viewport 虚函数

#### push 流程

```
render() → ViewBlock → ViewRenderState._wire_tree（单棵树，缓存）
push(viewport) → _vp_push_render:
  1. wire_tree = ViewRenderState._wire_tree
  2. wire_tree = view.render_viewport(wire_tree, channel_id)  # 虚函数调用
  3. allowed = _extract_view_refs(wire_tree)  # 从变换后的树提取 $view 引用
  4. send(wire_tree)
  5. reconcile child ViewPorts（按 allowed 过滤）
```

子 ViewPort 的 allowed 集合从变换后的 wire tree 中提取所有 `$view` 引用推导，保证"wire tree 里有什么 $view，就推送什么子 View"的一致性。

#### 使用方式

- **默认**：不覆写 `render_viewport` 的 View，wire tree 原样推送，所有子 View 都推送
- **VirtualList**：覆写 `render_viewport`，按该 viewport 的可见范围过滤 `$children` 中的 `$view` 引用
- **DockPanel**：覆写 `render_viewport`，根据该 viewport 的尺寸计算坍缩树，生成不同结构的 wire tree

### DockPanel 后端改动

#### 数据结构变更

```python
# 现有（单一状态）
_container_size: tuple[int, int] | None = None
_collapsed_active: dict[str, str] = {}       # split_id → panel_id
_collapsed_orders: dict[str, list[str]] = {}  # split_id → panel_ids

# 改为（per-viewport）
_viewport_sizes: dict[int, tuple[int, int]] = {}             # channel_id → (w, h)
_viewport_collapsed_active: dict[int, dict[str, str]] = {}   # channel_id → {split_id → panel_id}
_viewport_collapsed_orders: dict[int, dict[str, list[str]]] = {}  # channel_id → {split_id → panel_ids}
```

#### render() 变更

`render()` 仍调用一次，但不再调 `_compute_layout`。wire tree 基于原始 `_layout` 生成（全部展开状态），作为 "模板树"。per-viewport 的坍缩在 transform 钩子中处理。

子 View 集合 = 所有面板的 View（并集，因为不同 viewport 可能看到不同面板）。

#### render_viewport 实现

```python
def render_viewport(self, wire_tree, channel_id):
    size = self._viewport_sizes.get(channel_id)
    if not size:
        return wire_tree
    # 基于该 viewport 的尺寸计算坍缩
    render_tree = self._compute_layout(self._layout, *size, channel_id)
    return [{...wire_tree[0], "$children": [self._build_wire_node(render_tree)]}]
```

`_compute_layout` 增加 `channel_id` 参数，查找该 viewport 的 `_collapsed_active` 和 `_collapsed_orders`。

#### 事件处理变更

| 事件 | 现有行为 | per-viewport 行为 |
|------|----------|------------------|
| resize | 更新 `_container_size` | 更新 `_viewport_sizes[viewport_id]` |
| tab_switch（非坍缩） | 改 `TabSetNode.active_id` | 不变（共享） |
| tab_switch（坍缩态） | 改 `_collapsed_active[split_id]` | 改 `_viewport_collapsed_active[viewport_id][split_id]` |
| tab_reorder（非坍缩） | 改 `TabSetNode.panel_ids` | 不变（共享） |
| tab_reorder（坍缩态） | 改 `_collapsed_orders[split_id]` | 改 `_viewport_collapsed_orders[viewport_id][split_id]` |
| tab_move/dock/edge_dock | 改 `_layout` 树 | 不变（共享） |
| split_resize | 改 `SplitNode.ratio` | 不变（共享） |

tab_switch 和 tab_reorder 需要区分"当前是否坍缩态"。判断方法：`find_node(self._layout, tabsetId)` 返回 SplitNode 说明是坍缩态（该 ID 在原始树中是 SplitNode，但前端看到的是坍缩后的 TabSetNode）。这个判断逻辑已存在于现有代码中。

#### viewport 清理

参照 VirtualList 的 `_refresh_visible()`，在 render/transform 时清理已断开 viewport 的状态条目，避免泄漏。

### 不需要改动的部分

- **前端**：仍然是哑渲染器，收什么画什么。每个 viewport 收到适合自己尺寸的 wire tree
- **`_layout` 原始树**：结构性操作（tab_move/dock/edge_dock/split_resize）的处理逻辑完全不变
- **坍缩算法**（`_compute_layout`）：逻辑不变，只是接入 per-viewport 的 collapsed_active/orders

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| mutbot | 多设备同时访问 IDE 布局 | per-viewport 独立坍缩 | 手机和桌面同时打开，各自坍缩状态独立，结构变更共享 |
| mutgui demo | 多窗口调试 | 不再翻转坍缩 | 两个不同大小窗口同时连接，布局稳定 |
| 框架通用 | `render_viewport` 虚函数 | 任意 View 可 per-viewport 定制 wire tree | VirtualList、DockPanel 均通过 override 实现 |

## 实施步骤清单

### 框架层

- [x] 在 `view.py` 添加 `render_viewport(wire_tree, channel_id)` 虚函数（默认原样返回）
- [x] 在 `_viewport_impl.py` 添加 `_extract_view_refs` 辅助函数（从 wire tree 递归提取所有 `$view` 引用 ID）
- [x] 简化 `_vp_push_render`：统一调用 `view.render_viewport()`，从返回的 wire tree 提取 allowed 集合
- [x] 删除 `ViewChildFilter` 和 `ViewWireTransform` Extension 类

### DockPanel 后端

- [x] 数据结构改为 per-viewport：`_viewport_sizes`、`_viewport_collapsed_active`、`_viewport_collapsed_orders`；移除 `_container_size`、`_collapsed_active`、`_collapsed_orders`、`_collapsed_node_ids`
- [x] `render()` 改为模板模式：不调 `_compute_layout`，基于 `_layout` 原始树生成，所有面板 View 作为 children 并集
- [x] 覆写 `render_viewport`：根据 channel_id 的尺寸计算坍缩树，生成 per-viewport wire tree
- [x] 修改 `_compute_layout`：增加 `channel_id` 参数，从 per-viewport dict 读取 `collapsed_active`/`collapsed_orders`
- [x] 修改事件处理器：`_on_resize` 更新 `_viewport_sizes[viewport_id]`；`_on_tab_switch`/`_on_tab_reorder` 的坍缩态分支更新 per-viewport dict
- [x] 添加 viewport 清理：参照 VirtualList `_refresh_visible()`，在 render 时清除已断开 viewport 的状态条目

### VirtualList 适配

- [x] 覆写 `render_viewport`：按该 viewport 的可见范围过滤 `$children`
- [x] 将 `_viewport_item_ids` 从 ViewChildFilter Extension 迁移为实例属性

### 测试

- [x] 添加 DockPanel per-viewport 单元测试：两个 MockChannel 模拟不同尺寸 viewport，验证独立坍缩和共享结构变更
