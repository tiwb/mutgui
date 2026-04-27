# VirtualList 流式贴底失效修复

**状态**：✅ 已完成
**日期**：2026-04-27
**类型**：Bug 修复

## 现象

`bugfix-virtual-list-scroll-jitter.md` 实施完成（commit 89d6a96）后，抖动现象在 antd 渲染恢复正常后已消失。但在重新组织 demo（commit 55f4a47，移除调试探针、按钮下移）后，再次手动验证 `demo/examples/virtual_list_chat.py` 发现新症状：

**流式回复过程中，第一段 token 出现时列表能贴底，但后续 chunk 全部不再贴底**。最后一条助手消息从视口底部"长出去"，距离底部越来越远，直到流式结束。整个过程视觉上没有抖动（不是 jitter spec 描述的那种 "颤一下"），就是单方向的"内容超出底部"。

复现路径：
1. `python demo/examples/virtual_list_chat.py`
2. 等初始 6 条消息渲染完，手动滚到底部（也可以直接发送，发送时 itemCount 变化会触发首次贴底）
3. 点击"发送并流式回复"
4. 观察：第一段 chunk 文本出来时列表瞬间贴底；之后每 80ms 追加一段，最后一条消息底部逐渐离开视口下沿，期间 scrollTop 完全不动

不在本次范围（已是 streaming spec 的既定行为，或留待 anchor-scroll spec 解决）：
- DETACHED 状态下用户读历史时不被打断
- DETACHED 状态下上方 item 高度变化不锚定

## 关键参考

- `frontend/src/components/virtual-list.tsx` — 当前实现（commit 55f4a47）
- `docs/specifications/bugfix-virtual-list-scroll-jitter.md` — 上一轮抖动修复（已完成），引入了 `userScrollingRef` + `isProgrammaticScrollRef` 单 flag 模型与 `flushMeasuredHeights` 内的早期推 scrollTop 路径，本次问题与这两处机制密切相关
- `docs/specifications/feature-virtual-list-streaming.md` — 流式 streaming 上游 spec
- `demo/examples/virtual_list_chat.py` — 手动复现 demo
- `src/mutgui/virtual_list.py` — 后端 VirtualList，`item_view.invalidate()` 路径只重发该 ItemView 的 wire，**不**触发父 VirtualList 的 itemCount/itemIds 变化
- `https://github.com/petyosi/react-virtuoso/blob/master/packages/react-virtuoso/src/stateFlagsSystem.ts` — react-virtuoso 将“离开底部”的原因区分为 `SCROLLING_UPWARDS` / `SIZE_INCREASED` / `VIEWPORT_HEIGHT_DECREASING`
- `https://github.com/petyosi/react-virtuoso/blob/master/packages/react-virtuoso/src/followOutputSystem.ts` — react-virtuoso 对 `SIZE_INCREASED` / `VIEWPORT_HEIGHT_DECREASING` 走自动回到底部，而不是把它们当成用户脱离跟随

## 调查

### 链路梳理

后端 `append_to_message` → `_invalidate_existing_item` → 只 `item_view.invalidate()`，**没有**调 `adapter.invalidate()`。所以前端 VirtualList 父组件的 `itemCount` / `itemIds` props **不变**，VirtualList 这一层不会因后端 push 而自然 re-render。

所有"贴底"反应只能依赖一条链：

```
ItemView 内 DOM 长高
  → ResizeObserver 触发（盯的是 wrapper div）
  → flushMeasuredHeights via RAF
    → 更新 heightMap
    → setLayoutVersion(v+1)
  → React commit：spacer 高度 = layout.totalHeight 增大 → scrollHeight 增大
  → useEffect [..., layoutVersion] 跑（已加依赖）
    → 把 scrollTop 推到 scrollHeight - clientHeight
```

useEffect 的实际代码：

```ts
useEffect(() => {
  if (!stickToBottom || followStateRef.current !== 'FOLLOWING') return;
  const el = containerRef.current;
  if (!el) return;
  const targetScrollTop = Math.max(0, el.scrollHeight - el.clientHeight);
  if (Math.abs(el.scrollTop - targetScrollTop) < 1) return;
  isProgrammaticScrollRef.current = true;
  el.scrollTop = targetScrollTop;
  lastScrollTopRef.current = targetScrollTop;
  calculateViewport();
}, [calculateViewport, itemCount, itemIds, stickToBottom, layoutVersion]);
```

### chrome-cdp 实测数据

用 chrome-cdp 在浏览器里装 ResizeObserver + MutationObserver + scroll listener 探针，记录每个事件触发瞬间的 `scrollTop` / `scrollHeight` / spacer height / transform 等。重置 demo → 滚到底（自动贴底）→ 点击"发送并流式回复"，捕捉到的关键时间段：

**阶段 A：itemCount 变化（user prompt + 空 assistant 入场）成功贴底一次**

```
t=43997ms scroll       sT=863  sH=1423 dist=0    ← 用户/初始已贴底
t=45542ms SPACER-style sT=863  sH=1786 dist=363  ← spacer 突然涨 +363（新 item 入场）
t=45546ms (4ms 内)     sT=1226 sH=1786 dist=0    ← useEffect 把 sT 推到 1226 ✓
t=45559ms scroll       sT=1226                   ← 浏览器派发 scroll #1
t=45560ms SPACER-style sT=1026 sH=1586 dist=0    ← viewport 重算，spacer 缩到 1586，
                                                   浏览器自动 clamp sT 到 1026（max scrollable）
t=45575ms scroll       sT=1026                   ← 浏览器派发 scroll #2
```

**阶段 B：之后所有流式 chunk 都不再贴底**

```
t=45708 item-resize msg-55 newH=135.2  sT=1026 sH=1638 dist=52
t=45726 SPACER-style sH=1638                    sT=1026 dist=52   ← spacer 长高，sT 不动
t=45741 SPACER-resize sH=1638.5                 sT=1026 dist=52
t=45798 item-resize msg-55 newH=161.6  sT=1026 sH=1665 dist=79
t=45808 SPACER-style sH=1665                    sT=1026 dist=79
...
t=46575 SPACER-resize sH=1796.8                 sT=1026 dist=211  ← 越来越远
```

`SPACER-style` 持续在变 → 说明 `setLayoutVersion` + React commit 都在跑 → useEffect 必然被触发（依赖了 `layoutVersion`）。但 `scrollTop` 始终停在 1026 不动 → useEffect 必然第一行就 `return` → **`followStateRef.current !== 'FOLLOWING'`**。

### 根因

`followStateRef` 在阶段 A 末尾被错误切到 `'DETACHED'`，之后再也回不来（DETACHED 下 useEffect 不推 scrollTop，dist 单调上升，更不会自动切回 FOLLOWING）。

切换发生在 t=45575ms 那次 scroll：

- handleScroll 此时读到的 `previousScrollTop = lastScrollTopRef = 1226`（来自阶段 A 第一次 useEffect 设的）
- `currentScrollTop = el.scrollTop = 1026`（spacer 缩小后浏览器对 sT 的自动 clamp）
- `isProgrammaticScrollRef` 已被上一次 scroll #1 消费成 `false`
- 进入 `resolveFollowStateOnUserScroll`：`isScrollingUp = 1026 < 1226 - 1 = TRUE` → 返回 `'DETACHED'`

阶段 A 之所以会触发"两次"scroll 事件而 flag 只准备了一次，源于两个时机错位：

1. **第一次 useEffect 设 sT=1226**（spacer=1786 时的底部）→ 浏览器派发 scroll #1，flag 被消费
2. **viewport 重算导致 spacer 缩到 1586** → 浏览器自动把超出范围的 sT 从 1226 clamp 到 1026 → 派发 scroll #2，flag 已经是 false → 被当成"用户向上滚"

`isProgrammaticScrollRef` 是 boolean 单 flag。只要"程序性写 scrollTop 的次数"和"浏览器派发 scroll 事件的次数"不严格 1:1（包括浏览器自身的 clamp、合并、去抖等行为），flag 就会错位。错位一次，followState 就被永久污染。

### 与上一轮 jitter 修复的关系

`bugfix-virtual-list-scroll-jitter.md` 的 A1（stick-to-bottom 同步化）在 `flushMeasuredHeights` 内部加了一段"早期推 scrollTop"。这段代码用的是**未 commit 的旧 scrollHeight**（spacer 还没长高），且只在 `Math.abs >= 1` 时才设 flag——本身效果有限，但额外贡献了一次 sT 写动作和 lastScrollTopRef 更新机会，使阶段 A 的 flag/event 时序更难对齐。完整的 flag 错位场景在去掉这段代码后是否依然存在，需要在修复方案设计时验证。

`bugfix-virtual-list-scroll-jitter.md` 实施反馈中"用户验证后抖动消失"的结论应该理解为：jitter 修复 + antd 渲染恢复 共同消除了肉眼可见的抖动；但留下了一个**新的、更隐蔽的状态污染问题**——followState 一旦被错误切到 DETACHED，后续 useEffect 全部短路。

## 设计方案

### 设计原则

保持 `feature-virtual-list-streaming.md` 的原语义不变：

- **只有明确的用户操作**才能让状态从 `FOLLOWING` 切到 `DETACHED`
- **没有用户操作**时，即使浏览器因为 layout / clamp 派发了 scroll，也不能污染 followState
- 用户一旦明确开始向上读历史，哪怕只滚了一小段、尚未超过 threshold，也应立即解除跟随

换句话说，当前 bug 不是"贴底判定公式错了"，而是**把"scroll 结果"误当成了"用户意图"**。

### A1：把"用户意图"和"scroll 结果"拆开

`handleScroll` 不能再直接用"是否收到了 scroll 事件"来推断这是用户滚动。需要额外维护一个短时 `scrollCauseRef` / `userIntentRef`：

- `wheel`
- `touchmove`
- `keydown`（`PageUp` / `PageDown` / `Home` / `End` / `ArrowUp` / `ArrowDown` / `Space`）
- 滚动条拖拽（`pointerdown` 后进入 dragging，直到 `pointerup`）

这些明确的输入事件出现时，才把接下来的一次或一小段 scroll 标记为 **USER**；否则默认是 **LAYOUT_OR_PROGRAMMATIC**。

`handleScroll` 中 followState 切换规则改为：

```ts
if (cause === 'USER') {
  // 保持 streaming spec 的语义：
  // 用户向上滚一格就 DETACHED；用户滚回底部再 FOLLOWING
  followStateRef.current = resolveFollowStateOnUserScroll(...)
} else {
  // 这里只更新 lastScrollTop / viewport，不允许 FOLLOWING -> DETACHED
  // 若当前已经回到底部，可把状态收敛回 FOLLOWING
  if (distanceFromBottom <= threshold) {
    followStateRef.current = 'FOLLOWING';
  }
}
```

这样浏览器在 spacer 缩小时触发的 clamp scroll 没有对应的用户输入前导事件，只会被归类为 **LAYOUT_OR_PROGRAMMATIC**，不会再把状态错误切到 `DETACHED`。

### A2：`isProgrammaticScrollRef` 只负责"回声抑制"，不再承担用户意图识别

当前单 boolean flag 最大的问题不是"程序性滚动一定识别不出来"，而是**它被拿去决定 followState 是否可信**。修复后它降级为窄职责：

- 阻止 `el.scrollTop = ...` 触发的首个 `onScroll` 反向调用 `onScrollHandler`
- 避免本组件自己写入的 scrollTop 立即形成反馈回路

它**不再**作为"这次 scroll 是不是用户操作"的唯一依据。浏览器 clamp、多次 scroll 合并/拆分、scroll 事件补发都不应该再有机会污染 followState。

### A3：像 react-virtuoso 一样，按"离底原因"而不是"离底事实"决策

react-virtuoso 的做法不是简单地看 `isAtBottom` 布尔值，而是区分：

- `SCROLLING_UPWARDS`
- `SIZE_INCREASED`
- `VIEWPORT_HEIGHT_DECREASING`

本问题也应采用同样思路。对 VirtualList 来说，最少需要区分两大类：

1. **USER_SCROLL_AWAY**：用户明确向上/离底滚动 → `DETACHED`
2. **LAYOUT_SHIFT**：内容高度变化、spacer 重算、浏览器 clamp、viewport 变化 → 保持原状态；若原来是 `FOLLOWING`，继续贴底

这保证了"用户操作很明确"这个产品语义：**不是所有离开底部都代表用户想读历史**。

### A4：`userScrollingRef` 的挂起逻辑也绑定到明确用户输入

当前代码里，只要 `!isProgrammaticScrollRef.current` 就会把 `userScrollingRef.current = true`。这会把浏览器 clamp 也误记成"用户正在滚动"。

修复后应改为：

- 只有 `cause === 'USER'` 时才进入 `userScrollingRef` idle timer
- `LAYOUT_OR_PROGRAMMATIC` scroll 不启动 idle timer，也不挂起后续 flush

否则 followState 虽然修好了，layout flush 仍会被非用户 scroll 误伤。

### A5：观测与验证范围

现有探针已经足够确定设计方向，不需要再继续扩大根因搜索。实施前补最小观测即可：

- 在 `handleScroll` 入口打印：`prev` / `current` / `distanceFromBottom` / `cause` / `followState(before->after)`
- 单测补三类场景：
  - **layout clamp**：先 programmatic scroll 到底，再模拟 scrollHeight 收缩后的 clamp scroll，状态保持 `FOLLOWING`
  - **explicit user up-scroll**：用户向上滚一小段但未超过 threshold，仍立即切 `DETACHED`
  - **user back to bottom**：用户重新滚到底，恢复 `FOLLOWING`

### 为什么不选其他方向

- **不选"只看距底 threshold"**：会丢掉"用户刚开始读历史就立刻停跟随"这一条明确语义
- **不选"继续强化 programmatic target 匹配"**：仍然是在猜 scroll 事件来源，本质上还是把用户意图绑定到浏览器时序细节上
- **不把希望押在合并 commit / 消灭二次 scroll**：这类时序在浏览器和 React 调度层面都不稳定，修掉一次还会在别的路径复发

## 实施步骤清单

- [x] 为 VirtualList 增加显式的用户滚动来源识别（wheel/touch/keyboard/scrollbar drag）
- [x] 重构 `handleScroll`：followState 只在明确用户滚动时允许 `FOLLOWING -> DETACHED`
- [x] 收窄 `isProgrammaticScrollRef` 职责，只保留程序性写 scrollTop 的回声抑制
- [x] 修正 `userScrollingRef` / idle timer 的触发条件，避免 layout clamp 被记为用户滚动
- [x] 为 followState 增加 layout clamp / 显式用户滚动 / 回到底部三类前端单测
- [x] 手动回归 `demo/examples/virtual_list_chat.py`：流式期间持续贴底；用户一旦开始上滑立即停止跟随；无用户操作时不会无故脱底

## 测试验证

- `pytest`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `npm --prefix frontend run build:standalone`
- 手动验证：`python demo/examples/virtual_list_chat.py`

## 关键观测代码（chrome-cdp）

复现使用的探针代码（保留供后续验证修复时复用）：

```js
const el = document.querySelector('.mutgui-virtual-list');
const spacer = el.children[0];
const transformed = el.children[1];
if (window.__probe) window.__probe.cleanup();
el.scrollTop = el.scrollHeight - el.clientHeight;  // 强制贴底

const events = [];
const t0 = performance.now();
const log = (tag, extra) => events.push({
  tag, t: Math.round(performance.now() - t0),
  sT: Math.round(el.scrollTop), sH: el.scrollHeight, cH: el.clientHeight,
  spacerH: Math.round(spacer.getBoundingClientRect().height * 10) / 10,
  tf: transformed.style.transform, n: transformed.children.length,
  dist: el.scrollHeight - el.clientHeight - el.scrollTop,
  ...(extra || {})
});

const onScroll = () => log('scroll');
el.addEventListener('scroll', onScroll, { capture: true });

const ro = new ResizeObserver(entries => {
  for (const e of entries) {
    if (e.target === spacer) log('SPACER-resize', { newH: Math.round(e.contentRect.height * 10) / 10 });
    else log('item-resize', {
      itemId: e.target.dataset?.itemId || '?',
      newH: Math.round(e.contentRect.height * 10) / 10
    });
  }
});
ro.observe(spacer);
for (const w of transformed.children) ro.observe(w);

const mo = new MutationObserver(muts => {
  for (const m of muts) {
    if (m.target === spacer && m.attributeName === 'style')
      log('SPACER-style', { h: spacer.style.height });
    if (m.target === transformed && m.type === 'childList') {
      log('item-list-change', { added: m.addedNodes.length, removed: m.removedNodes.length });
      for (const n of m.addedNodes) if (n.nodeType === 1) ro.observe(n);
    }
    if (m.target === transformed && m.attributeName === 'style')
      log('TF-change', { tf: transformed.style.transform });
  }
});
mo.observe(spacer, { attributes: true, attributeFilter: ['style'] });
mo.observe(transformed, { attributes: true, attributeFilter: ['style'], childList: true });

window.__probe = {
  events,
  cleanup: () => { el.removeEventListener('scroll', onScroll, { capture: true }); ro.disconnect(); mo.disconnect(); }
};
```

通过 `chrome-cdp pysandbox "playwright.browser_evaluate(function='() => window.__probe.events.map(e => ...)')"` 拉日志。
