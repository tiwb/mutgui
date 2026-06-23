# renderBatch 批量渲染消息

**状态**：✅ 已完成
**日期**：2026-06-23
**类型**：功能设计

## 需求

1. VirtualList 当前 `itemIds`/`viewportStart` 和 item View 内容分多条 WebSocket 消息到达，导致 item 高度在 pending → resolved 间跳变，引发 scrollHeight 抖动
2. 需要在同一帧渲染消息中同时下发 VirtualList 的树和所有子 item View 的树，消除消息层面的分叉
3. 不改变现有 `render` / `command` 消息格式，不影响非 VirtualList 场景的渲染路径

## 关键参考

- `mutgui/src/mutgui/_viewport_impl.py` — `vp_push_render`、`_filter_overlays_by_channel`、`_extract_view_refs`、子 ViewPort 生命周期管理
- `mutgui/src/mutgui/_view_impl.py` — `_render_and_cache`、`_deferred_render`、`_process_node`/`_process_value`
- `mutgui/src/mutgui/_virtual_list_impl.py` — `virtual_list_render`、`_refresh_visible`、`_vl_for_vp`
- `mutgui/frontend/src/core.tsx` — `createConnection`、`InboundMessage`、`handleMessage`
- `mutgui/frontend/src/core/renderer.tsx` — `MutguiView`（`data-view-pending`、`useState(null)` 初始状态）
- `mutgui/frontend/src/core/context.tsx` — `MutguiConnection` 接口
- `mutgui/frontend/src/components/virtual-list.tsx` — VirtualList 前端组件（`displayedRange`/`viewportStart` 解耦、ResizeObserver pending 检测）

## 设计方案

### 消息格式

将 `render` 消息从单帧改为多帧批量下发，消除 itemIds 与 item 内容的分叉到达：

```json
{
  "type": "render",
  "frames": [
    { "viewId": [],     "tree": [...] },
    { "viewId": ["a"],  "tree": [...] },
    { "viewId": ["b"],  "tree": [...] }
  ]
}
```

- `viewId`、`tree` 语义不变，消息类型名保持 `render`
- `frames` 顺序保证：父 View 的帧一定在其引用的子 View 帧之前（前端处理时 cache 先写完整再统一通知 subscriber）
- 所有场景统一走此格式：单帧 View 的 `frames` 数组仅一个元素，行为等价

### 后端：重构 `vp_push_render`

`vp_push_render` 改为一次收集全部帧 → 一条 `render` 消息下发，删除原逐帧发送逻辑。

```
vp_collect_frames(vp, frames)
  - 取 wire_tree（缓存命中 / 补 render）
  - filter overlays（per-channel）
  - extract view refs
  - frames.append((path, tree))
  - 子 VP reconciliation（create/reuse/detach）
  - 递归收集子 ViewPort 帧

vp_push_render(vp)
  - frames = []
  - vp_collect_frames(vp, frames)
  - await channel.send({type:"render", frames: [...]})
```

`_deferred_render` 统一调用 `vp_push_render`，所有 View 均走批处理路径。

### 前端：三处改动

**`context.tsx`** — `MutguiConnection` 接口新增 `peekCache`：

```typescript
export interface MutguiConnection {
    send(data: string): void;
    subscribe(viewId: ViewPath, callback: RenderCallback): () => void;
    peekCache(viewId: ViewPath): unknown[] | undefined;  // 新增
    teardown?(): void;
}
```

**`core.tsx`** — `createConnection` 实现 `peekCache` + `renderBatch` 分支：

```typescript
// peekCache 实现
peekCache: (viewId) => cache.get(JSON.stringify(viewId)),

// handleMessage render 分支改为批量处理
if (msg.type === 'render') {
    const frames = msg.frames as Array<{viewId?: ViewPath; tree?: unknown[]}>;
    for (const {viewId, tree} of frames) {
        cache.set(JSON.stringify(viewId ?? []), tree ?? []);
    }
    for (const {viewId, tree} of frames) {
        subs.get(JSON.stringify(viewId ?? []))?.(tree ?? []);
    }
    return;
}
```

**`renderer.tsx`** — `MutguiView` 从 cache 初始化：

```typescript
const [tree, setTree] = useState<ComponentSchema[] | null>(
    () => conn.peekCache(fullPath) ?? null
);
```

`renderBatch` 先写完整所有帧的 cache 再通知 subscriber，React 18 自动批处理同一同步块内的多个 `setState`。子 MutguiView mount 时 `useState` 初始化即命中 cache，一次 commit 完成。

### MutguiView：从 cache 初始化 state

`MutguiView` 改为从 connection cache 初始化 `tree` 状态：

1. `MutguiConnection` 接口新增 `peekCache(viewId: ViewPath): unknown[] | undefined` 同步方法
2. `MutguiView` 中 `useState(null)` 改为 `useState(() => conn.peekCache(fullPath) ?? null)`

`vp_push_render` 先收集全部帧并写入 cache，再通知 subscriber。子 MutguiView mount 时 `useState` 初始化即命中 cache，**一次 commit 完成渲染**。

所有场景统一走此路径：单帧 View 的 `frames` 仅一个元素，行为与原先逐帧下发完全等价。

### 兼容性

- 老前端收到 `frames` 格式的 `render`：`handleMessage` 按旧格式解析 `msg.viewId` 为 `undefined`，忽略该消息。需确保前后端同步部署
- 老后端仍发旧格式 `render`（无 `frames`）：新前端的 `frames` 为 `undefined`，直接 `return` 忽略。前后端版本不匹配时渲染停摆
- `InboundMessage` 类型定义直接替换，TypeScript 编译时覆盖

## 待定问题

### QUEST Q1: 多帧渲染中是否允许混杂不同 ViewPort 的帧？

**问题**：当前所有 View 共享同一个 Channel，`frames` 中的 `viewId` 路径都在这个 Channel 内。未来如果多 ViewPort 的帧合入同一条 render，前端 `cache` 是否冲突？

**建议**：当前仅同 Channel 内的帧。不做跨 Channel 批处理。如有未来需求，render 格式可扩展 `channelId` 字段，前端按 channel 分 cache 实例。现阶段不引入此复杂度。

### QUEST Q2: 多帧渲染中某帧 render 失败如何处理？

**问题**：`vp_collect_frames` 递归收集过程中，某个子 View 的 `_render_and_cache` 抛异常。当前 `vp_push_render` 遇到此情况跳过该帧继续收集，还是整个 batch 失败？

**建议**：与现有行为一致——跳过失败的帧，继续收集其余帧。即 render 的 `frames` 数可能少于全量子 VP 数，这是合法的。前端按实际到达的帧处理即可。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| VirtualList 前端 | VL render 到达时子 item 内容同步到达 | render 包含 VL + item views | 单次 scroll → 不再出现 "仅 itemIds 到但 item 内容未到" |
| 所有 View | 任意 View 的渲染 | render 的 `frames` 包含全部子帧 | 现有测试全量通过，DockPanel/Menu/Toolbar/Forms 渲染正常 |

## 实施步骤清单

- [x] 后端：提取 `vp_collect_frames`，`vp_push_render` 改为批量下发（`_viewport_impl.py`）
- [x] 后端：`_deferred_render` 统一调用 `vp_push_render`，删除 prefer_batch_push 分流（`_view_impl.py`）
- [x] 后端：VirtualList 不再需要设 prefer_batch_push（`_virtual_list_impl.py`）
- [x] 前端：`MutguiConnection` 接口加 `peekCache`（`context.tsx`）
- [x] 前端：`render` handler 改为批量格式，删除 renderBatch 分支（`core.tsx`）
- [x] 前端：`MutguiView` 从 `peekCache` 初始化 `tree`（`renderer.tsx`）
- [x] 测试：更新 MockChannel 解析新 `render` 格式，全量通过
