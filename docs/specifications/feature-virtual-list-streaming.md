# VirtualList 流式聊天场景增强

**状态**：🔄 实施中
**日期**：2026-04-27
**类型**：功能设计

## 需求

为流式聊天 / 长会话场景增强 VirtualList 能力。当前 VirtualList 在普通文件列表 / 属性编辑器场景已可用，但在 agent 流式聊天场景下存在三个硬缺口，导致 mutagent.ui MessageList 无法基于现有 VirtualList 实现。

1. **真正的可变高度**：当前实现按固定 `DEFAULT_ITEM_HEIGHT = 32` 算偏移和总高度，所有 item 强制一致。聊天消息高度差异极大（一行命令 vs 5000 字 Markdown 回答），固定高度完全不可用。
2. **单 item 内容变化重测高度**：流式 token 累加进最后一条 AssistantMessage，该 item 的高度持续增长，VirtualList 必须感知并据此调整后续 item 位置和滚动条总高。
3. **stick-to-bottom 跟随策略**：聊天体验刚需，三段式：
   - 用户在底部时新内容自动跟随到底
   - 用户向上滚动后自动解除跟随，安心读历史
   - 用户重新滚到底部恢复跟随

辅助需求（非必须，可推迟）：

4. 跨 item 文本选择 / 复制 — virtual scroll 与原生选择天然冲突，首版用 AssistantMessage 自带「复制」按钮兜底，不强求。

## 关键参考

### 当前实现

- `mutgui/frontend/src/components/virtual-list.tsx`（148 行）— 固定 `DEFAULT_ITEM_HEIGHT = 32`、`DEFAULT_OVERSCAN = 5`、`VIEWPORT_THROTTLE_MS = 50`；leading + trailing throttle；programmatic scroll 防循环
- `mutgui/src/mutgui/virtual_list.py`（175 行）— `VirtualList` View + `VirtualListItemAdapter` Declaration；per-VP viewport range + union 渲染 + per-VP 裁剪
- `mutgui/docs/specifications/feature-virtual-list.md` — 基础 spec（声称"可变高度 ✅"，实际未落地，本 spec 补齐）
- `mutgui/docs/specifications/feature-virtual-list-multi-viewport.md` — 多 viewport + sync_scroll 模式
- `mutgui/demo/examples/virtual_list_chat.py` — 聊天流式手动验证 demo，覆盖可变高度、最后一条增长和 stick-to-bottom

### 上层消费者

- `mutagent/docs/specifications/feature-builtin-webui.md` QUEST Q8 — mutagent.ui MessageList 的能力依赖清单
- `mutbot/frontend/src/components/MessageList.tsx`（407 行）— 现有 React 实现，作为视觉与交互行为对齐基线

### 外部参考

- **react-virtuoso** — 参考其 `followOutput` API（`'auto' | 'smooth' | false`）和 stick-to-bottom 的「用户滚动则解除」实现
- **Vaadin Virtual List** — `setRenderer` + 自动高度测量
- **Phoenix LiveView Streams** — `at: -1` 追加到尾部的语义
- **CSS `overflow-anchor`** — 浏览器原生 anchor scroll 仅对 native layout 生效，virtual list 用 `transform` 定位时失效

## 设计方案

### 高度模型

**采用「单一估算值 + 真实测量校正」混合策略**（Vaadin / Blazor 主流方案，工程上简单）：

- 前端维护 `heightMap: Map<itemId, number>`，键为 stable item ID（不是 index，因为 ID 跨 viewport 稳定）
- 未测量的 item 用 `estimatedItemHeight`（默认 32，可由后端通过 prop 覆盖）
- 已渲染的 item 通过 ResizeObserver 测得真实高度，写入 heightMap
- 总高度 = `Σ(已测量高度) + (未测量数 × estimatedItemHeight)`
- offsetTop = `Σ前置 item 的 (已测量高度 ?? estimatedItemHeight)`

heightMap 用 itemId 而非 index 作 key，使得 item 滚出 viewport 后高度信息**保留**（除非 adapter 通过 `id_changed` 通知该 item 真的换了）。这避免了用户来回滚动时反复测量同一 item。

**heightMap 是 per-client 前端状态**，不跨客户端同步：multi-VP 场景下不同客户端 viewport 宽度可能不同，同一 itemId 的 wrap 高度天然不同，per-client 维护是正确的。

**heightMap 不主动清理**：每项约 50 bytes，10000 条消息 = 500KB，浏览器完全可承受。若 itemId 真从 adapter 消失，heightMap 残留也无害（下次该 ID 不出现就不参与计算）。等真有用户报告内存问题再考虑 LRU。

**不引入「后端预估高度」机制**：聊天场景下后端无法准确预估（消息内容动态生成），多一轮预估 RTT 反而增加复杂度；文件列表等已知高度的场景仍可用 estimatedItemHeight 把估算值打准。

#### 估算值自适应（首版基础）

聊天场景下消息高度从 24px（短回复）到 8000px（长 markdown）跨三个数量级，单一估算值会严重失真。首版采用**已测量 item 的滑动平均**作为未测量 item 的估算值：

```
actualEstimate = heightMap.size > 0
    ? sum(heightMap.values) / heightMap.size
    : estimatedItemHeight  // prop 值仅作为 bootstrap
```

prop 传入的 `estimated_item_height` 只在「还没任何测量数据时」起作用。一旦有测量数据，估算值由真实数据驱动收敛。

#### 演进方向（不在首版）

- **按 item type 分桶估算**：聊天场景的 user / assistant_text / tool_group / error 几类消息高度分布差异大，按 type 分别记估算值比单一均值更准。需要 Adapter 多暴露一个 `item_type(index) -> str`。

### 单 item 高度变化

**机制**：每个 item 容器挂 ResizeObserver，高度变化时更新 heightMap 并触发重布局。

**关键约束**：
- 高度更新**不上报后端**——纯前端状态。后端不需要知道 item 像素高度，只需要知道 viewport item 范围（已有 onViewport）。
- 高度更新触发本地 re-layout（重算 offsetTop），但不发起额外 onViewport 回报，除非 viewport 范围真的变了。
- ResizeObserver 节流：连续高度变化合并到下一帧（`requestAnimationFrame`），同一 item 的多次变化只取最后一次。避免流式 token delta 每个字符触发一次 layout。不引入额外 `setTimeout` 防抖（避免 stick-to-bottom 锚底产生延迟感——用户希望流式输出「贴着底部生长」是即时反馈）。

### 单 item 高度 > viewport 高度

聊天场景高频：一条 5000 字 markdown / 长 traceback / 展开的 tool_group 高度可能远超 viewport。所有计算必须正确处理这种情况。

**stick-to-bottom 锚底公式**：`scrollTop = scrollHeight - clientHeight`。这条公式天然处理任意 item 高度——「内容底部贴 viewport 底部」与 last item 高度无关。**不要错写成「滚到 last item 的 top」**——这会让流式时 last item 的顶部被钉死、底部新内容被遮，是新手常见错误。

**viewport 范围判定改为相交判定**（不再是 `index = scrollTop / itemHeight`）：

```
item i visible ⟺ offsetTop[i] < scrollTop + clientHeight
              AND offsetTop[i] + height[i] > scrollTop
```

当 `height[i] > clientHeight` 时，viewport 内可能**只有这一个 item**。要保证 visible_ids 至少包含这一个 item，否则会出现「viewport 是空白」的 bug。

### 滚动位置的内部表达

**关键思维框架**：可变高度引入后，pixel `scrollTop` 不再是「滚动位置的真理」，而是渲染出口/浏览器接口。真正的内部状态是 **(visibleStartIndex, offsetWithinItem)**——「滚到第几个 item 的什么位置」。

pixel 仅在三个边界出现：
1. 浏览器 scroll 容器读 / 写 `el.scrollTop`
2. heightMap 累加得到 `offsetTop[i]` 喂给 `transform: translateY()`
3. 总占位高度 `totalHeight` 撑滚动条

所有内部计算（viewport 判定、stick-to-bottom 状态判定、未来的 anchor 补偿）都基于 `(index, offset)` 模型，pixel 是这个模型在浏览器边界的换算结果。

**为什么需要这个思维框架**：
- 等高时 `scrollTop = index × 32`，pixel 与 (index, offset) 是双射，谁当真理都行；可变高度后，pixel 与 (index, offset) 之间需走 heightMap 累加换算，且对未测量 item 不可逆
- 如果继续把 pixel 当真理，会写出几类错代码：用 `prevScrollTop / DEFAULT_ITEM_HEIGHT` 反算 index、跨 invalidate 用 pixel 阈值（scrollHeight 突变会导致瞬时失真）等
- 该思维框架也是未来 anchor scroll 补偿的前提

**首版不引入对外 API**：`scrollToItem(item_id, offset, align)` 之类命令式 API、`onScrollPosition(item_id, offset)` callback 都不在首版范围。等 mutagent.ui 真要做「跳转到某条消息 / 搜索结果定位 / 阅读位置恢复」时再独立立项。

**invalidate 视为有前后边界的过程**：未来 anchor scroll 补偿会在 invalidate 前后挂前置/后置 hook（见独立 spec）。首版不实现 hook，但 invalidate 实现要保持「这是一段连续过程、有明确开始与结束」的结构，不要把 invalidate 散落在多处副作用里。

### sync_scroll 在可变高度下的局限

现有 `sync_scroll = True` 模式后端透传 `scroll_top: float`（pixel）。在可变高度场景下，**不同客户端 viewport 宽度不同 → 同 itemId 的 wrap 高度不同 → 同一 pixel scrollTop 在不同客户端落到不同 item**。本 spec **不修复**这条限制——`sync_scroll` 与 `stick_to_bottom` 互斥（见下文），聊天场景不触发；其他 sync_scroll 用例（多客户端协作浏览同一文档）通常宽度也接近，触发概率低。

未来如需修复，方案是把后端协议升级为 `(item_id, offset_within_item)` 表达，pixel 字段保留兼容——非破坏性变更。

### stick-to-bottom 跟随策略

**状态归属：前端独立**（不通过后端同步）。理由：
- 聊天是 per-client 的阅读体验，不需要多客户端同步
- 后端零负担，复用现有 sync_scroll 体系反而冗余
- 与「sync_scroll = True」的多客户端协同模式天然兼容（sync_scroll 由后端控制，stick-to-bottom 由用户行为控制，两者正交）
- prop `stick_to_bottom: bool` 是「能力开关」（聊天场景下开启），不是「当前是否跟随」的运行时状态。前端拿到 prop = True 后自己内部维护 FOLLOWING/DETACHED 状态机——天然 per-client，无需 per-client 切换 prop

**判定与状态机**：

```
状态：FOLLOWING | DETACHED

初始：FOLLOWING

用户主动滚动事件:
    if 滚动方向是向上 OR 距底部 > THRESHOLD:
        → DETACHED
    elif 滚到底部（距底部 < THRESHOLD）:
        → FOLLOWING

itemCount 增加 / heightMap 变化（流式追加 / 单 item 增长）:
    if 状态 == FOLLOWING:
        scrollTop = scrollHeight - clientHeight  # 锚到底（任意 item 高度都正确）
    else:
        保持当前 scrollTop
        # 前置 item 高度变化导致的视觉跳动属于已知限制（首版接受）
```

**THRESHOLD**：默认 32px（约一行高度），可由 prop 覆盖。

**「用户主动滚动 vs programmatic 滚动」识别**：复用现有 `isProgrammaticScrollRef` 模式——stick 触发的 `el.scrollTop = ...` 设置 flag，下一个 onScroll 事件忽略状态切换判定。

### stick-to-bottom 不内置 UI、不上报后端

stick-to-bottom 状态机**完全收敛在前端**，遵循三条原则：

- VirtualList **不内置任何 UI**（无「返回底部」按钮、无角标、无 toast）
- **不上报后端**（per-client 纯前端状态，避免无意义的 RPC 与多客户端语义冲突）
- 「用户滚到下方自动恢复跟随」是基础语义，已在状态机中（DETACHED + scrollTop 到底 → FOLLOWING），不需要任何提示 UI 也能工作

业界共识：底层虚拟列表组件（react-virtuoso、SwiftUI ScrollView 等）都不绑定 UI 提示，按钮/角标/未读计数等是产品层决策，由上层消费者（如 mutagent.ui MessageList）自行实现。

#### 未来扩展位（首版不实现）

以下为非破坏性扩展接口，未来需要时按此扩展：

- **状态信号 callback**：`onFollowStateChange(following: bool)` —— 上层用来决定何时显示「返回底部」按钮
- **命令式 API**：前端 ref 暴露 `scrollToBottom()` —— 上层按钮点击时调用

首版连这两个扩展位也不预先暴露，避免引入未验证的 API 形状。等真实场景出现再加。

### 互斥校验

`sync_scroll = True` 与 `stick_to_bottom = True` 同时启用语义直接冲突：sync_scroll 让所有客户端共享 scrollTop，stick_to_bottom 让每个客户端独立维护跟随状态。VirtualList 构造函数检测到同时为 True 时抛清晰错误。聊天场景用 `stick_to_bottom`，协作编辑场景用 `sync_scroll`，没有同时需要的合理用例。

### API 增强

#### 后端 Declaration 增加 props

```python
class VirtualList(View):
    def __init__(
        self,
        id: str,
        adapter: VirtualListItemAdapter,
        *,
        sync_scroll: bool = False,
        stick_to_bottom: bool = False,        # 新增
        estimated_item_height: int = 32,       # 新增
    ) -> None: ...
```

- `stick_to_bottom: bool` 默认 False（不破坏现有 demo 行为）。聊天场景显式传 True。
- `estimated_item_height: int` 默认 32（保持向后兼容）。聊天场景可设为 120 之类的更接近平均值的数值，减少首屏跳动。

#### 前端组件 props 增加

```ts
interface VirtualListProps {
  itemCount: number;
  children?: React.ReactNode;
  onViewport?: (info: { start: number; end: number }) => void;
  onScroll?: (info: { scrollTop: number }) => void;
  scrollTop?: number;
  overscan?: number;
  style?: React.CSSProperties;
  // 新增
  stickToBottom?: boolean;
  estimatedItemHeight?: number;
  // 新增：item 容器渲染时把 itemId 作为 data-attribute 透出，
  // 供 heightMap 用 ID 而非 index 索引
  itemIds?: string[];          // 长度 = visible children 数
}
```

`itemIds` 由后端在 render 时附带，作为新 prop 传给前端组件（最局部、不改框架、不侵入 item 渲染）。VirtualList.render 已在 `_refresh_visible` 中拿到 `visible_ids`，挂到 props 即可，长度等于 `$children` 长度，与 children 同顺序对应。前端拿到 itemIds[i] 就给第 i 个 visible child 容器加 `data-item-id` 属性，ResizeObserver 回调里读这个属性反查 heightMap。

### 可变高度的渲染布局

将原来「固定 32px × index 算 offsetTop」改为：

```tsx
// 总高度估算（撑滚动条）
const totalHeight = Array.from({ length: itemCount }, (_, i) => {
  const id = i >= viewportStart && i < viewportStart + visibleCount
    ? itemIds[i - viewportStart]
    : null;
  return (id && heightMap.get(id)) ?? estimatedItemHeight;
}).reduce((a, b) => a + b, 0);

// 视口内 offsetTop = 前置 item 高度累加
const offsetTop = sum(0..viewportStart of (heightMap.get(idAtIndex) ?? estimatedItemHeight));
```

注意：viewport 外的 item id 后端没下发，只能用 estimatedItemHeight 占位。这正好是「单一估算 + 增量校正」模型可接受的：用户滚到那个区域时，item 渲染出来后 heightMap 校正，scrollHeight 自然修正。

**已知副作用**：滚动条总高度会随用户滚动逐步变化（每次新 item 被测量都修正一次 totalHeight）。这是该方案的固有 tradeoff，react-virtuoso、Vaadin 等都接受这点；用户感知微弱，因为 visible item 的滚动位置始终正确。

### 复制兜底（替代跨 item 文本选择）

mutagent.ui 的 AssistantMessage 自己加「复制」按钮，点击直接 `navigator.clipboard.writeText(fullText)`，绕过 DOM 选择限制。**这条不在本 VirtualList spec 范围内**，记在这里作为对 mutagent.ui 的约定，避免误以为 VirtualList 要解决跨 item 选择。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|---|---|---|---|
| mutagent.ui MessageList | 流式聊天消息列表 | 真可变高度 + 单 item 重测 + stick-to-bottom | 流式输出过程中视觉稳定（不跳动）；用户在底部时新内容自动跟随；用户上滚后停止跟随；回到底部恢复跟随；测量后的总高度准确反映真实滚动条 |
| mutgui 现有 demo（properties 等） | 等高列表 | 默认行为不变 | `stick_to_bottom` / `estimated_item_height` 默认值保持现有视觉效果，无回归 |
| 多 viewport demo | sync_scroll 模式 | 与 stick_to_bottom 互斥校验 | 同时设两者抛清晰错误 |

## 已知限制（首版接受）

- **DETACHED 状态下前置变化会导致视觉位置跳动**，包括以下子情况：
  - 锚点之前的 item 被删除
  - 锚点之前的 item 高度变化（如 tool_group 折叠/展开、markdown 图片异步加载完成）
  - 锚点 item 本身被删除
  - 留待独立 anchor-scroll spec 解决，首版不实施
  - 流式聊天场景下这些情况几乎不发生（流式只追加最后一条，FOLLOWING 状态自动处理）
- **sync_scroll 在「可变高度 + 多客户端不同 viewport 宽度」下不保证视觉同步**：因 pixel scrollTop 在不同客户端含义不同。当前所有合理用例都不触发（sync_scroll 与 stick_to_bottom 互斥，等高列表 pixel 一致，多客户端协作通常宽度接近）
- **跨 item 文本选择无原生支持**（被 virtual scroll 卷出视口的 item 不在 DOM 中），通过 AssistantMessage 「复制」按钮兜底
- **滚动条总高度随用户滚动会有微小波动**（未测量 item 用估算值，测量后修正）。可变高度差异巨大时（如 24px 短消息混 8000px 长 markdown）波动幅度可能较大；估算值滑动平均可缓解但无法消除
- **拖拽滚动条到未测量区域时存在落点漂移**：连续滚动会自然修正

## 验收边界

**首版必须满足**：
- 不同高度的 item 正确堆叠，scrollTop 与视觉位置一致
- 单 item 高度持续变化时（模拟流式追加），后续 item 位置正确跟随，不重叠不留空
- 单条 item 高度 > viewport 高度时，viewport 范围按相交判定，至少包含该 item；FOLLOWING 状态下流式追加时该 item 底部正确锚底（不出现「item 顶部被钉死」）
- stick_to_bottom = True 时，初始状态在底部；新 item 追加自动滚到底；用户向上滚动后停止跟随；用户滚回底部恢复跟随
- stick_to_bottom 默认 False，现有 properties 等 demo 行为零变化
- sync_scroll + stick_to_bottom 同时为 True 时抛清晰错误
- 现有 multi-viewport 测试全部通过

**首版不要求**：
- DETACHED 状态下的 anchor scroll 补偿（独立 spec）
- 「返回底部」按钮、未读计数等 UI 提示（产品层决策，由上层 mutagent.ui 实现）
- `scrollToItem` 等命令式跳转 API（独立 spec）
- sync_scroll 在可变高度下的跨客户端视觉一致性
- 按 item type 分桶估算高度（演进项）
- 跨 item 文本选择
- heightMap 清理策略

## 实施步骤清单

- [x] 扩展 VirtualList 后端 API，透传 `stick_to_bottom`、`estimated_item_height` 和 `itemIds`，并加入 `sync_scroll` / `stick_to_bottom` 互斥校验
- [x] 重写前端 VirtualList 的布局与 viewport 计算，改为基于测量高度的可变高度虚拟滚动
- [x] 实现单 item 高度重测与 stick-to-bottom 状态机，覆盖流式增长和超高 item 场景
- [x] 补充后端与前端测试，验证兼容性与回归边界
- [x] 同步更新相关设计文档描述，并在完成后回填规范勾选状态

## 测试验证

- `pytest`
- `npm --prefix frontend run build`
- `npm --prefix frontend run build:standalone`

## 实施反馈

首版（impl-2，commit 38fc11e）实施后手动验证发现两类「滚动不平滑」：流式贴底抖动、用户主动滚动时 visible 段抖动。修复见独立文档 `bugfix-virtual-list-scroll-jitter.md`。

该 bugfix 中的 A2 修复（用户主动滚动期间挂起 layout flush）**取消了本 spec 原决策「不引入额外 setTimeout 防抖」**——原决策只考虑了流式贴底场景下 setTimeout 引入的延迟感，未意识到用户主动滚动期间 flush 会引入抖动；两者作用域正交，可同时满足。详细推演见 bugfix 文档的 A2 章节。
