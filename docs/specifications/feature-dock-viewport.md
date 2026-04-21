# DockPanel per-viewport 独立状态 设计规范

**状态**：📋 需求中
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

### 框架层挑战

VirtualList 的 ViewChildFilter 方案只过滤 `$children` 中的 `$view` 引用（扁平结构）。DockPanel 的 per-viewport 差异是 **树的形状不同**（SplitNode vs 坍缩后的 TabSetNode），不是简单的子 View 过滤。

现有框架 `render()` → 一棵 wire tree → ViewChildFilter 过滤子 View 引用。DockPanel per-viewport 需要每个 viewport 一棵不同结构的 wire tree。

### 内部实现

- **VirtualList per-viewport 模式** — `D:/ai/mutgui/src/mutgui/virtual_list.py`，`_viewports: dict[channel_id, tuple]` + `ViewChildFilter` + `_refresh_visible()` 计算可见集合并集
- **ViewChildFilter** — `D:/ai/mutgui/src/mutgui/_view_impl.py:44-52`，per-viewport 子 View 过滤
- **VP push 机制** — `D:/ai/mutgui/src/mutgui/_viewport_impl.py:108-160`，`_vp_push_render` 中应用 ViewChildFilter
- **DockPanel 现有实现** — `D:/ai/mutgui/src/mutgui/dock_panel.py`，`_container_size` 为单一 tuple，`_compute_layout` 一次计算

### 可能的方向

1. **扩展框架 push 机制**（正确方案，工作量大）：让 View 可为每个 viewport 生成不同 wire tree
2. **union tree + per-viewport collapse metadata**（中等方案）：wire tree 始终最大展开，附带 per-viewport 坍缩标记，前端根据标记渲染。违反"前端是哑渲染器"原则
3. **取最小 viewport 坍缩结果**（quick fix）：所有 viewport 统一用最保守的坍缩状态。体验不理想但快速解决翻转

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| mutbot | 多设备同时访问 IDE 布局 | per-viewport 独立坍缩 | 手机和桌面同时打开，各自坍缩状态独立 |
| mutgui demo | 多窗口调试 | 不再翻转坍缩 | 两个不同大小窗口同时连接，布局稳定 |
