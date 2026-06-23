# VirtualList 文档流重构

**状态**：✅ 已完成
**日期**：2026-06-23
**类型**：重构

## 需求

1. VirtualList 绝对定位方案在反复滚动时 scrollHeight 抖动，引发 viewport 振荡（一次用户滚触发 6-10 次 viewport 上报）
2. 前端布局计算模块（~300 行纯函数）复杂度高：逐 item 累加高度、手动计算 offsetTop/totalHeight
3. 高度测量批处理流水线（pendingMeasureIds + stagedHeightUpdates + measureRaf）过于复杂
4. 需要支持可变 item 高度的虚拟滚动场景

## 设计方案

### 核心架构变更：绝对定位平移容器 → 文档流 + spacer 占位

**旧方案**：所有 item 放在 `position: absolute; transform: translateY()` 的容器中，前端自行计算 offsetTop 和 totalHeight。

**新方案**：item 保持在正常文档流中，利用浏览器原生 `overflow-anchor` 维持视觉稳定。可见范围内 item 全量渲染为完整 React 组件，远端 item 用 spacer div（基于 `estimatedItemHeight` 估算）占位。

### bufferScreens + deadzoneScreens 替代 overscan

- `bufferScreens`（默认 1.0）：视口外保留的缓冲屏数，对应旧 `overscan`
- `deadzoneScreens`（默认 0.5）：触发上报前的死区屏数，避免边界抖动
- 参数化控制缓冲/死区比例，替代固定 item 数的 `overscan`

### Viewport 上报协议升级：新增 seq 序列号

```
旧: onViewport({ start, end })
新: onViewport({ start, end, seq })
```

- 前端每次上报递增 `seq`，后端回传 `viewportSeq`
- 通过 `viewportSeq === reportSeqRef` 判断数据是否匹配当前上报
- 数据匹配时使用真实高度（`heightCache`），不匹配时用估算高度防御 mismatch

### 双路径 range 计算策略

**computeFreshRange**（初始化/大跳/失配时）：基于 `scrollTop` 估算 anchor，整窗计算范围。

**computeNextReport**（展路径）：
- 基于当前持有 item 的像素位置（`headSpacer + heldHeight`），计算头部/尾部缓冲余量
- 接近边缘时单边扩展，协同修剪另一端
- 在死区内返回 `null` 跳过上报
- 大跳检测：滚动超过一个视口高度时回退到 fresh 路径

### 上报去重与流控

- `reportInFlightRef` 防止并发上报
- `pendingReportRef` 免重复发送相同范围
- `dirtyRef` + `rafIdRef` rAF 轮询，每帧最多上报一次

### displayedRange 与 viewportStart 解耦

spacer 高度使用 `displayedRange`（上报时立即同步设置），不与 `viewportStart`（后端异步返回）耦合，避免"数据到达时 spacer 突变 → layout shift → 级联滚动"。

### force-to-bottom 机制

流式 FOLLOWING 场景下，ResizeObserver 检测到高度变化后通过 rAF 调度锚底，避免同步读 scrollHeight 引起的振荡回路。

### 移除的模块

| 移除项 | 原因 |
|--------|------|
| `indexToId` / `idToIndex` 双向映射 | item 在文档流中由 spacer 定位，不再需要跨视口查找 |
| `calculateScrollAnchor` / `calculateVirtualLayout` / `calculateViewportRange` | 被 computeFreshRange / computeNextReport 替代 |
| `resolveFollowState*` / `resolveScrollCause` / `shouldAutoRefreshViewport` 导出函数 | 内化到 handleScroll 中 |
| 高度测量 rAF 批处理流水线 | ResizeObserver 回调中直接写入 heightCacheRef |
| tier1/tier2 分级渲染 | 统一全量渲染 |

### renderer.tsx 占位 div

旧代码 `tree === null ? null` 在 VirtualList 文档流方案中会导致 item 缺失无占位。改为 `<div data-view-pending="true" />` 后经分析 `tree` 类型为 `ComponentSchema[]` 永不为 null，后续清理为直接 `renderTree(tree)`。

## 实施步骤清单

- [x] 重写 `virtual-list.tsx` — 删除绝对定位布局，改为文档流 + head/tail spacer 占位
- [x] 新增 `bufferScreens` / `deadzoneScreens` props，替代 `overscan`
- [x] 删除纯函数导出模块（~300 行：calculateScrollAnchor / calculateVirtualLayout / calculateViewportRange 等）
- [x] 实现 `computeFreshRange`（初始化/大跳/失配时的整窗计算）和 `computeNextReport`（展路径 + 协同修剪）
- [x] 实现上报去重与流控（reportInFlight + pendingReport + dirtyFlag + rAF 轮询）
- [x] `onViewport` 协议升级：新增 `seq` 序列号，后端回传 `viewportSeq`，防数据 mismatch
- [x] spacer 高度使用 `displayedRange`（即时同步），与 `viewportStart`（后端异步）解耦
- [x] 新增 `force-to-bottom` rAF 锚底机制，替代布局版本驱动的振荡方案
- [x] 移除 `indexToId` / `idToIndex` 双向映射、高度测量批处理流水线、tier1/tier2 分级
- [x] 更新 `virtual_list.py` — 新增 `buffer_screens` / `deadzone_screens` 属性，`__init__` 改为 `**kwargs`
- [x] 更新 `_virtual_list_impl.py` — 新增 `viewport_seqs` 追踪，`onViewport` callback 带回 `seq`
- [x] 更新 `demo/examples/virtual_list.py` — 扩展为可变 item 高度演示（6 种高度）
- [x] 更新 `renderer.tsx` — `tree === null` 渲染 `<div data-view-pending />`，后续清理为直接 `renderTree(tree)`
- [x] 更新前端测试 `virtual-list-layout.test.ts` — 删除已移除函数的测试用例
- [x] 新增集成测试 `tests/integration/test_virtual_list.py`

## 关键参考

- `frontend/src/components/virtual-list.tsx` — 前端组件（~600 行，重写核心逻辑）
- `frontend/src/core/renderer.tsx` — MutguiView 渲染器
- `src/mutgui/virtual_list.py` — View 声明，新增 buffer_screens / deadzone_screens 属性
- `src/mutgui/_virtual_list_impl.py` — 实现，新增 viewport_seqs 追踪 + seq 回传
- `demo/examples/virtual_list.py` — demo 扩展为可变 item 高度演示（6 种高度）
- `frontend/tests/virtual-list-layout.test.ts` — 测试简化为仅保留常量导入
- `tests/integration/test_virtual_list.py` — 新增集成测试
