# ViewBlock 多 Viewport 统一渲染

**状态**：✅ 已实施
**日期**：2026-05-22
**类型**：重构

## 需求

1. 消除 `render_viewport` 独立 hook——当前 `render()` 和 `render_viewport()` 拆成两步，View 被迫在 `render_viewport` 中操作 WireTree，wire 域泄露到 View 层
2. 消除手动 `render_to_wire()` 调用——DockPanel 在 `render_viewport` 中构建 RenderComponent 后又手动调用 `self.render_to_wire()`，wire 转换不统一
3. 让 View 自己决定 per-VP 复用策略，不强制框架遍历/traverse 中间树
4. Demo 级文本替换不需要深拷贝整个 WireTree——当前三个 demo 各自复制 `_replace_children`，对 WireTree 递归深拷贝只为改一个文本节点

## 关键参考

- `src/mutgui/view.py` — View / ViewBlock / WireTree / RenderTree 类型定义
- `src/mutgui/_view_impl.py` — `_render_and_cache` / `_process_value` / `_deferred_render`
- `src/mutgui/_viewport_impl.py` — `_vp_push_render` / child ViewPort reconciliation
- `src/mutgui/dock_panel.py` + `_dock_panel_impl.py` — render_viewport 覆盖者
- `src/mutgui/virtual_list.py` + `_virtual_list_impl.py` — render_viewport 覆盖者

## 设计方案

### 核心思想

`PerViewport` —— 新增原语，标记"值在不同 viewport 下取不同内容"。同时进入 `RenderValue` 和 `RenderNode` 两个 union——既能作为 dict 值位的叶值，也能作为 RenderTree / `$children` 列表的元素，在 render 域声明任意位置的 per-VP 差异，to_wire 时统一解析。

ViewBlock 保持极简：只有 `items: RenderTree` 一个字段，不引入构造多态（决策理由：PerViewport 既然能在 list 元素位出现，整棵树 per-VP 的场景写成 `ViewBlock([PerViewport(...)])` 即可，不必给 ViewBlock 再加一个互斥字段）。

```
render() → ViewBlock(items: RenderTree) → 框架 to_wire(items, viewport_id=vp) → push
                                           ↑ PerViewport 在任何层级（值位/list 元素位）参与，to_wire 统一解析
```

**消除的旧 API**：
- `View.render_viewport(wire_tree, channel_id) → WireTree`
- `View.render_to_wire(value) → WireValue`

### 类型体系

```python
# 新增原语
class PerViewport(mutobj.Declaration):
    """包装 per-viewport 的值。类似 Callback 的参数捕获语义。"""
    def __init__(self, fn: Callable[..., RenderValue], /, *args: Any, **kwargs: Any):
        # fn: 回调 fn(viewport_id, *args, **kwargs) → RenderValue
        # viewport_id 在求值时作为第一个位置参数注入
        # *args / **kwargs 在构造期捕获，求值时原样 forward
        ...
    def get(self, viewport_id: int) -> RenderValue: ...

# Render 域：PerViewport 同时进 RenderValue 和 RenderNode
RenderValue = (
    None | bool | int | float | str
    | View | EventHandler
    | PerViewport                        # ← 新增（dict 值位 / 嵌套 list 元素位）
    | Sequence[RenderValue]
    | Mapping[str, RenderValue]
)

RenderComponent = dict[str, RenderValue]                     # 不变
RenderNode = RenderComponent | View | PerViewport            # ← 新增 PerViewport（顶层 list 元素位）
RenderTree = list[RenderNode]                                # 不变

# ViewBlock：单一字段，无构造多态
class ViewBlock:
    items: RenderTree

    def __init__(self, items: RenderTree):
        self.items = items
```

### PerViewport 的三个出现位置

| 位置 | 用法 | 示例 |
|------|------|------|
| **dict 值位** | RenderComponent 的某个 value | 叶值 per-VP 不同（文本、数字、scrollTop） |
| **顶层 list 元素位** | `ViewBlock.items` 的元素 | 整棵子树 per-VP 不同（DockPanel 坍缩、VirtualList 容器） |
| **嵌套 list 元素位** | 任意 component 的 `$children` 元素 | 局部子树 per-VP 不同（共享头部 + per-VP 主体的混合） |

同一个 `PerViewport` 原语，所有位置共享语义。to_wire 在 `_process_value` / `_process_node` 中遇到 PerViewport 实例 → 调 `value.get(viewport_id)` → 递归处理结果。

**list 元素位的语义约束**：`get(vid)` 必须返回**单个 RenderNode**，不做 splice 展开（决策理由：splice 让节点位变成 0..N，破坏 children/handlers 注册的位置稳定性；如需 per-VP 的多元素，用一个包装 component 把它们装在 `$children` 里）。dict 值位无此约束，可返回任意 RenderValue。

### 三种消费者场景

**场景 A：简单 View（共享，零改动）**

```python
def render(self) -> ViewBlock:
    return ViewBlock([{"$component": "div", "children": "hello"}])
```
`items` 全是 RenderComponent / View，没有 PerViewport 实例 → 各 VP 解析结果结构一致。

**场景 B：叶值差异 — PerViewport 在值位**

```python
def render(self) -> ViewBlock:
    return ViewBlock([{
        "$id": "connection-id",
        "children": PerViewport(lambda vid: f"viewport {vid}"),
    }])
```
不做遍历、不做深拷贝。声明式。`fn` 在 to_wire 时被调用。

**场景 C：结构差异 — PerViewport 作为 list 元素**

```python
# DockPanel — PerViewport 捕获 self + 共享数据，回调按 vid 计算坍缩后 layout
def render(self) -> ViewBlock:
    return ViewBlock([PerViewport(
        _dock_panel_children, self, all_views,
    )])

# VirtualList — PerViewport 捕获 self + 共享 props，回调按 vid 拆 itemIds / $children
def render(self) -> ViewBlock:
    _refresh_visible(self)  # precompute 一次
    return ViewBlock([PerViewport(
        _vl_for_vp, self, common,
    )])
```

回调签名 `fn(viewport_id, *args, **kwargs)`，返回**单个 RenderNode**（不是 list），由外层 `[...]` 提供 RenderTree 容器。View 不手动循环 VP——`fn` 按需计算，框架在 `_render_and_cache` 对每个活跃 VP 调用一次。

### 框架流程（概念）

```
1. block = view.render()                                 # 总是 ViewBlock

2. render-and-cache 阶段（每次 invalidate 后跑一次）：
     对每个活跃 VP：wire_per_vp[vp] = to_wire(block.items, viewport_id=vp)
     state.children / state.handlers 取所有 VP 解析结果的并集
     缓存 wire_per_vp

3. push 阶段：
     for each VP: push(vp, wire_per_vp[vp])
```

- `to_wire`：在 `_process_value` / `_process_node` 中遇到 PerViewport 实例 → `value.get(viewport_id)` → 递归处理
- `PerViewport.get(vid)`：调用注册的回调 `fn(vid, *args, **kwargs)` 返回 RenderValue
- wire 转换、overlay 过滤、child VP reconciliation 保持不变

### Children / Handlers 跨 VP 的并集语义

PerViewport 可能让不同 VP 解析出不同的子 View 引用 / EventHandler。`state.children` 和 `state.handlers` 必须是**所有活跃 VP 解析结果的并集**，否则：

- VP-A 引用 ViewX、VP-B 没引用 —— 若 ViewX 不在 `state.children` 里，从 VP-A 来的事件无法路由到 ViewX。
- 同理 EventHandler 必须跨 VP 注册到 `state.handlers`，否则 handler_id 路由失败。

**实现策略**：`_render_and_cache` 阶段对每个活跃 viewport 跑一次 `to_wire`，副作用统一注册到 `state.children` / `state.handlers`（先 `clear()` 再聚合）。每个 VP 的 wire_tree 单独缓存，push 时按 VP 取对应缓存。无 PerViewport 时各 VP 的 wire_tree 结构一致，后续可考虑"单次解析全 VP 共享"的快路径优化（当前未实施，每个 VP 独立解析）。

**PerViewport 实例的生命周期**：每次 `view.render()` 产新 ViewBlock + 新 PerViewport，旧实例 GC 即天然失效。`fn` 的计算结果缓存绑定到 PerViewport 实例本身——使用方**不应**把 PerViewport 存为成员变量跨 render() 复用，否则缓存语义会不符合预期。

### View.active_viewport_ids

新增便捷属性，让 View 在 render() 中获取当前活跃的 viewport ID 列表：

```python
class View:
    @property
    def active_viewport_ids(self) -> Sequence[int]: ...
```

内部读 `ViewObservers` → viewports → `channel.channel_id`。render 调用时必然已绑定 ViewPort，所以总是可用的。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| DockPanel | 多 VP 下 per-VP 响应式坍缩 | PerViewport 在 list 元素位 | 不同 VP 尺寸下解析出 Split/TabSet 结构正确；事件路由无遗漏 |
| VirtualList | 多 VP 下 per-VP itemIds / viewportStart 拆分 | PerViewport 在 list 元素位 | 各 VP 独立拿到自己的可见 itemIds；$children 不跨 VP 泄露 |
| mutgui Demo / 应用 View | per-VP 叶值差异（channel_id、theme 显示） | PerViewport 在 dict 值位 | 一行 `PerViewport(lambda vid: ...)` 替代深拷贝 `_replace_children` |
| 简单单 VP View | 无 per-VP 需求 | ViewBlock + RenderComponent | 零改动，render() 签名不变，框架透明处理 |

## 实施步骤清单

- [x] 在 `view.py` 中新增 `PerViewport(mutobj.Declaration)` 类
- [x] 将 `PerViewport` 加入 `RenderValue` 和 `RenderNode` 类型联合
- [x] 在 `__init__.py` 公开导出 `PerViewport`
- [x] 创建 `PerViewportState` 扩展存储 fn/args/kwargs
- [x] 实现 `PerViewport.__init__` 和 `PerViewport.get`（fn 参数捕获 + viewport_id 注入）
- [x] `View` 新增 `active_viewport_ids` 属性
- [x] `_process_value` / `_process_node` 增加 `viewport_id` 参数，遇到 `PerViewport` 时递归解析
- [x] `_render_and_cache` 改为 per-VP 缓存（`wire_tree_per_vp: dict[int, WireTree]`），跨 VP 并集 children/handlers
- [x] `_vp_push_render` 适配 `wire_tree_per_vp`，移除 `render_viewport` 调用
- [x] `ViewPort.initialize` 适配：首次 attach 同步跑 `_render_and_cache` 后推送
- [x] DockPanel 移除 `render_viewport` 覆写，`render()` 用 `PerViewport` 表达 per-VP 坍缩
- [x] VirtualList 移除 `render_viewport` 覆写，`render()` 用 `PerViewport` 表达 per-VP itemIds / $children
- [x] Demo 示例移除 `_replace_children` + `render_viewport`，改用 `PerViewport` 一行声明
- [x] 测试新增 `_resolve_for_viewport` 辅助函数
- [x] DockPanel / VirtualList / Action 测试从 `render_viewport` 迁移到 `_resolve_for_viewport`
- [x] 集成测试（command_channel）用 `PerViewport` 替代 `render_viewport` 覆写

## 遗留问题

### Overlay 系统统一

本次重构**不动** overlay 路径：`_render_and_cache` 仍然在 wire_tree 顶层 append `{"$view": id}`、`_vp_push_render` 仍然走 `_filter_overlays_by_channel` 按 `origin_channel_id` 过滤（决策理由：overlay 与 ViewBlock 解耦的现状能正常工作，与本次重构正交，不要扩大范围）。

但 PerViewport 在 list 元素位的能力天然兼容 overlay 场景——未来可以把 overlay 表达为 `ViewBlock.items` 末尾追加 `PerViewport(fn=lambda vid: overlay_view_for(vid))`，用闭包替代 `origin_channel_id` 过滤。这条**留口子**，不在本次范围。

### Per-VP 失效粒度

当前 `View.invalidate()` 触发所有 VP 重 render + 重 push（VirtualList sync_scroll 单 VP 滚动也会让所有 VP 重发 wire）。后续可加 `invalidate_viewport(vid)` 或 push 阶段做 wire 等值比较跳过未变 VP。
