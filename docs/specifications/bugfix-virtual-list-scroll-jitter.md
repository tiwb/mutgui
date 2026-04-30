# VirtualList 滚动不平滑修复

**状态**：✅ 已完成
**日期**：2026-04-27
**类型**：Bug 修复

## 现象

`feature-virtual-list-streaming.md` 实施完成（impl-2，commit 38fc11e）后，手动验证 `demo/examples/virtual_list_chat.py` 发现两类滚动不平滑：

1. **流式 token 累加贴底抖动**：FOLLOWING 状态下助手消息流式增长时，最后一条 item 在视口底部肉眼可见地"颤"——每个 chunk 触发一次跳动，而非平滑生长
2. **用户主动滚动时 visible 段抖动**：用户向下滚动到未测量区域时，新 item 进入视野被首次测量后 visible 段位置瞬时偏移

第三类是 `feature-virtual-list-streaming.md` 已经接受的限制，不在本次修复范围内：

- DETACHED 状态下读历史时 viewport **上方** item 高度/数量变化导致跳动 → 留待独立 anchor-scroll spec 解决

## 关键参考

- `mutgui/frontend/src/components/virtual-list.tsx` — 当前实现（GPT impl-2，508 行）
- `mutgui/docs/specifications/feature-virtual-list-streaming.md` — 上游 spec，本次修复属于其实施反馈
- `mutgui/demo/examples/virtual_list_chat.py` — 手动验证 demo
- 历史对比：`virtual-list-streaming-impl-1`（Claude 实现，已弃，列表不连续）

## 根因分析

### B1：用户主动滚动时 visible 段抖动

链路：

```
onScroll → calculateViewport → setViewportStart → 后端下发新 itemIds
  → 新 item 渲染 → ResizeObserver 触发 → pendingMeasureIds 累积
  → flushMeasuredHeights → heightMap 写入 + setLayoutVersion(+1)
  → useMemo 重算 totalHeight + offsetTop（用了新的 indexToId 测量值）
  → React commit → visible 段 transform 跳到新 offsetTop
```

问题：用户的滚动手势仍在进行（onScroll 还在触发），上述链路在用户的滚动帧之间穿插执行，每次 flush 都让 visible items 的 `transform: translateY(...)` 跳一下。表现为"滚动不跟手"。

### B2：流式 token 累加贴底抖动

链路：

```
后端 invalidate（最后一条 item 文本增长） → 前端重渲染该 item
  → ResizeObserver 触发 → pendingMeasureIds 累积
  → requestAnimationFrame → flushMeasuredHeights → setLayoutVersion(+1)
  → useMemo 重算 layout.totalHeight
  → useEffect[layout.totalHeight] → anchorToBottom → scrollTop 写入
```

问题：anchor-to-bottom 走 useEffect，**异步、滞后于 paint**：
- 帧 N：item 高度增长 → ResizeObserver 触发
- 帧 N+1：flushMeasuredHeights 同步写 heightMap + setLayoutVersion → React 重渲染（此时 totalHeight 已经增大但 scrollTop 没动 → visible 区下移、底部出现空白 / 最后一条被裁）
- 帧 N+2：useEffect 跑，写 scrollTop → visible 段补回到底

每个 token chunk 都走一遍 N→N+1→N+2，肉眼上是"先漏一点底，再补回来"。

### B3：layout 计算每次都全量遍历

`getAdaptiveEstimatedHeight` 每次都 new Set + 遍历 indexToId + 遍历 heightMap；`calculateVirtualLayout` 又 O(itemCount) 累加。每次 layoutVersion 增长都重跑一次。1000+ items 时累加成可感知的延迟。

### B4：死代码增加阅读成本

`calculateVirtualLayout` 内部计算了 `visibleStart/End` 字段，并读取了过期的 `containerRef.current?.scrollTop`，但消费方（render 只用 `totalHeight`/`offsetTop`，calculateViewport 自己用实时 scrollTop 重算一遍）都不用这两个字段。误导。

## 修复方案

### A1：stick-to-bottom anchor 同步化

把 anchor-to-bottom 从 `useEffect` 移到 `flushMeasuredHeights` 末尾**同步执行**。flushMeasuredHeights 自身已经在 `requestAnimationFrame` 回调里、且写完 heightMap 后立即调用 `setLayoutVersion`——在 setLayoutVersion 之前/之后同步读 `el.scrollHeight` / `el.clientHeight`，立即写 `el.scrollTop = scrollHeight - clientHeight`，与 heightMap 写入处于同一帧 commit。

效果：消除 N→N+1→N+2 的三帧链路，流式生长改为单帧贴底。

需要保留原来的 useEffect[itemCount, itemIds] 锚底路径作为兜底（itemCount 变化但没触发 ResizeObserver 时，比如 item 被删除），但把依赖里的 `layout.totalHeight` 移除——它已经被 flushMeasuredHeights 内的同步路径覆盖。

### A2：用户主动滚动期间挂起 layout flush

> ⚠️ **本条偏离 streaming spec 原决策**：streaming spec 明确写过「不引入额外 `setTimeout` 防抖（避免 stick-to-bottom 锚底产生延迟感——用户希望流式输出「贴着底部生长」是即时反馈）」。
>
> 本条在用户**主动滚动期间**挂起 flush，对**流式贴底**没有影响（FOLLOWING 状态下用户没在滚动，A1 路径仍然同帧锚底）。两者作用域正交：
> - 用户主动滚动 → 短暂的 idle 检测期内不重排，避免 visible 段抖动
> - 流式贴底 → 由 A1 走 flush 同步路径，零延迟
>
> 取消原决策的理由：原决策只考虑了"流式贴底场景下 setTimeout 引入延迟感"，没有意识到"用户主动滚动期间 flush 引入抖动"。两者本来就不会同时发生。

机制：
- onScroll 时设 `userScrollingRef = true`，并 schedule 一个 100ms 后清除的 timer（每次 onScroll 重置 timer——典型 scrollend polyfill）
- `flushMeasuredHeights` 检查 `userScrollingRef`：若为 true，**不**调用 `setLayoutVersion`（heightMap 仍写入，但不触发重渲染）
- timer 触发清除后，主动调用一次 `setLayoutVersion(+1)` 让累积的高度变化一次性应用

边界：
- FOLLOWING 状态下不挂起（流式贴底优先于平滑——A1 同步路径仍生效）
- sync_scroll 模式下也挂起（被动 client 收到后端 scrollTop 时是 programmatic scroll，不会标记 userScrolling）

未来考虑：浏览器 `scrollend` 事件已被 Chromium / Firefox 支持，可优先使用，timer 作为 Safari fallback。本次先用纯 timer 实现以减少复杂度。

### A3：estimate 滑动平均增量维护

把"已测量高度的 sum / count"提升为 ref：
- `flushMeasuredHeights` 写入新高度时，按 prevHeight → nextHeight 增量更新 sum
- 新 itemId 第一次测量时 count++
- estimate getter 退化成 O(1) 除法

`getAdaptiveEstimatedHeight` 被替换，`calculateVirtualLayout` 仍 O(itemCount) 累加（这一层暂不优化，分段累加是另一个故事）。

### A4：删 `calculateVirtualLayout` 死代码

- 移除 `visibleStart` / `visibleEnd` 字段（render 不用、calculateViewport 自己重算）
- 移除 `calculateScrollAnchor` 在 `calculateVirtualLayout` 内部的调用（同上）
- 移除 `scrollTop` / `clientHeight` 入参（render 链路不用，calculateViewport 自己读 el）
- 保留 `calculateScrollAnchor` 函数本身（calculateViewport 仍用它定位 first 相交 item）

## 实施步骤清单

- [x] **A4 先行清理死代码**：精简 `calculateVirtualLayout` / `VirtualLayout` 接口，只保留 `totalHeight` + `offsetTop` + viewport 边界字段，移除过期 scrollTop 读取
- [x] **A3 增量维护 estimate**：引入 `measuredHeightSumRef` / `measuredCountRef`，`flushMeasuredHeights` 内增量更新，`getAdaptiveEstimatedHeight` 改 O(1)
- [x] **A1 stick-to-bottom 同步化**：在 `flushMeasuredHeights` 末尾按 FOLLOWING 状态同步写 `scrollTop`；调整原 `useEffect` 依赖，避免双重锚底
- [x] **A2 滚动期间挂起 flush**：引入 `userScrollingRef` + 100ms idle timer，`flushMeasuredHeights` 在 userScrolling 期间跳过 `setLayoutVersion`，idle 后补一次
- [x] **回归 streaming spec 验收清单**：跑 `pytest` + `npm --prefix frontend run build` + `npm --prefix frontend run build`
- [x] **手动验证 chat demo 三场景**（见验收）
- [x] **streaming spec 末尾加实施反馈交叉引用**，避免后人对"不引入 setTimeout 防抖"决策的理解冲突

## 验收

`python demo/examples/virtual_list_chat.py` 手动跑下列场景，每条都不应有"跳一下 / 漏一线 / 抖动"的视觉感受：

1. **流式贴底**：滚到底部 → 点"发送并流式回复" → 流式输出过程中最后一条贴着 viewport 底部平滑生长，不出现"先漏底再补回"
2. **用户主动滚动**：列表已有 30+ 条消息，从顶部用滚轮/拖滚动条向下滚 → visible 段位置随 scrollTop 平滑变化，不因新 item 测量而瞬时偏移
3. **DETACHED 状态稳定**：滚到中段 → 点"发送并流式回复" → 当前阅读位置不变，不被流式锚底干扰（FOLLOWING 已切到 DETACHED）；流式结束后 itemCount 数字更新

不在本次验收范围（留待独立 anchor-scroll spec 解决）：

- DETACHED 状态下点"插入超长消息"导致的视觉跳动
- DETACHED 状态下上方图片加载完成导致的视觉跳动

## 测试验证

- `pytest`
- `npm --prefix frontend run build`
- `npm --prefix frontend run build`
- 手动验证：`python demo/examples/virtual_list_chat.py`

## 实施反馈

- 已完成代码实现、前端测试、库包构建、standalone 构建。
- 最终手动验收发现，一个更底层的问题混入了此前的抖动分析：demo 页中的 antd 组件曾整体失效，`antd.Button` / `antd.Alert` / `antd.Input.TextArea` 被错误回退成原始自定义标签，导致页面 DOM 结构、样式和高度测量都不处于真实运行状态。
- 根因不是组件名写错，而是前端组件解析器只接受 `function`，把 React object 形态组件（如 antd 的 `forwardRef` / `memo` 组件）误判为“非组件”；修复解析器后，standalone 页面恢复为真实 button / alert / textarea。
- 在 antd 恢复正常渲染后，用户按原路径再次手动验证，原先观察到的明显滚动乱跳现象消失。由此可判定，之前至少有一部分“抖动”样本属于坏页面状态下的伪问题，而不是正常聊天 UI 上稳定可复现的 VirtualList 缺陷。

