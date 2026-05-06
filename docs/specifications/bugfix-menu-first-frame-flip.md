# 菜单首帧 flip 失效 bugfix

**状态**：✅ 已完成
**日期**：2026-05-06
**类型**：Bug 修复

## 需求

1. 修复菜单在首帧 children 未到时被错误布局，导致最终位置无法 flip 而盖住触发器的 bug。
2. 顺手修复 hover 子菜单连续触发时 `pendingTrigger` 全局变量可能被覆盖的潜在竞态。

### 现象

`mutagent webui` 中 Send 按钮旁的下拉菜单，按钮位于视口底部时弹出后盖住 Send 按钮，预期应 flip 到上方。

实测时序（chrome-cdp 注入 `getBoundingClientRect` 拦截 + body MutationObserver 抓到）：

| 时序 | 事件 | menu children | 测得高度 | style.top |
|---|---|---|---|---|
| t=0 | 第 1 次 getBoundingClientRect | 0 | 9.8 | -100000 (hidden) |
| t≈1.4ms | menu 插入 body, visibility:visible | 2 | 69.7 | 815.653 |
| t≈15ms | 第 3 次 getBoundingClientRect | 2 | 69.7 | 815.653 |
| t≈15ms | style 属性变化 | 2 | 69.7 | 761.227（最终 clamp 后位置） |

最终 `top=761.227 ≈ 835 − 69.77 − 4`，正是"不 flip + 视口底部 clamp"的结果——菜单整体盖住 Send。

## 关键参考

### 现有实现

- `frontend/src/core/renderer.tsx` — `MutguiView`，菜单分支在此判断（第 60–70 行 `isMenuViewId` 分支）
- `frontend/src/components/menu.tsx` — `Menu` 组件、`pendingTrigger` 全局变量、`useLayoutEffect` 布局、`ResizeObserver`
- `frontend/src/components/menu-layout.ts` — 纯函数 `computeMenuLayout` / `recomputePosition`（无 bug，无需修改）
- `frontend/tests/menu-layout.test.ts` — 现有 menu 几何单测（vitest）

### 前置规范

- `docs/specifications/feature-menu-system.md` — 菜单系统基础（✅ 已完成）
- `docs/specifications/refactor-menu-placement.md` — placement 重构（✅ 已完成，本 bug 在此基础上发现）

## 根因分析

**错误输入**：`Menu` 在 `children` 为空时跑了首次布局。

```
用户点击 ▾ → pendingTrigger 写入
↓
后端创建 MenuView，push 父 tree（含 $menu:xxx 引用）
↓
前端 MutguiView 收到父 tree → 立即创建子 MutguiView 并挂载 Menu
↓
但子 view 的 tree 还没 push → tree=[] → Menu children 为空
↓
Menu useLayoutEffect 在空 children 上跑 computeMenuLayout
→ 测得 9.8px → 错误判定"放得下"，不 flip
↓
子 tree 后到 → menu 真实高度 69.7px
↓
现有 ResizeObserver 只跑 recomputePosition（clamp 不 flip）
→ 错误位置无法纠正
↓
菜单盖住触发器
```

`computeMenuLayout` 几何计算本身没错，错的是被喂了"空菜单尺寸"。修法应该消除错误输入，而不是事后异步兜底。

## 设计方案

### 主修复：MutguiView received gating

在 `MutguiView` 的菜单分支，等子 view 收到首帧 tree 后再挂载 `Menu`。把 `tree` state 改为 nullable 区分"未收到"和"收到空帧"：

```tsx
const [tree, setTree] = useState<ComponentSchema[] | null>(null);
// null = 未收到首帧
// []   = 收到合法空 tree
// [...] = 正常内容

useEffect(() => {
  return conn.subscribe(fullPath, (newTree) => {
    setTree(newTree as ComponentSchema[]);
  });
}, [conn, fullPath]);

if (isMenuViewId(viewId)) {
  if (tree === null) return null;       // ← 关键：未收到首帧不挂 Menu
  return (
    <ScopeProvider value={fullPath}>
      <Menu menuId={String(viewId)} conn={conn} viewPath={fullPath} initialTrigger={initialTrigger}>
        {renderTree(tree)}
      </Menu>
    </ScopeProvider>
  );
}

return (
  <ScopeProvider value={fullPath}>
    {tree === null ? null : renderTree(tree)}
  </ScopeProvider>
);
```

**为什么用 nullable 而不是 `tree.length === 0 return null`**：后者无法区分"未收到首帧"和"已收到合法空 tree"，会吃掉业务方推送的空菜单语义。

**为什么用 nullable 而不是单独引入 `received` boolean**：状态空间更小，单一变量同时表达"是否收到"和"内容"，难写错。普通 view 分支 `tree === null ? null : renderTree(tree)` 与原 `renderTree([])` 行为等价（都渲染为空），无副作用。

### 同步修复：trigger 在 MutguiView 层 take

received gating 把 Menu mount 时机延后了 ~一次后端 round trip。这段窗口里如果用户连续触发（特别是 hover 子菜单时快速划过菜单项的 `onMouseEnter`），`pendingTrigger` 全局单变量会被覆盖。

把 `pendingTrigger` 的消费从 Menu mount 提前到 MutguiView 看到菜单 viewId 那一刻——通过 `useState` lazy initializer 同步消费一次：

```tsx
const [initialTrigger] = useState<TriggerInfo | null>(() =>
  isMenuViewId(viewId) ? takePendingMenuTrigger() : null
);
```

`menu.tsx` 暴露 `takePendingMenuTrigger()`（取走并清空 `pendingTrigger`），`Menu` props 增加 `initialTrigger?: TriggerInfo | null`，内部优先使用 `initialTrigger`，没有时 fallback 到旧 `pendingTrigger` 兜底（兼容意外路径）。

trigger 消费时机回到与原版一致（父 tree 一到就消费），不受 received gating 延后影响；同时 Menu 不挂载也不污染 `.mutgui-menu` 全局查询。

### 不做的事（明确排除）

- **不在 `Menu` 内引入 ResizeObserver 完整 relayout**：当前 mutgui 菜单是后端一次 push 的静态结构，挂载后不再变化。"挂载后动态变高 → 需重 flip" 是未观察到的 bug，YAGNI。
- **不用 `tree.length === 0`**：会吃掉合法空菜单。
- **不引入 Menu shell 提前挂载方案**：会让空 shell 进入 DOM 污染 `closeAllVisibleMenus` / `isInsideAnyMenu` / 父子链查找等多处全局 `.mutgui-menu` 查询，需要全部加 ready 过滤，改动面大幅扩散。
- **不清理 `effectiveAnchorRef` 死代码**：与本 bug 无关，留给后续小重构 PR。

### 防退化

补 vitest 回归测试覆盖：

1. 父 tree 引用 `$menu` view 后、子 view tree 未到前，`document.body` 中无 `.mutgui-menu` 节点。
2. 子 view 收到 `[]` 时，`.mutgui-menu` 仍挂载（防止未来有人简化成 `tree.length === 0`）。
3. （可选）端到端时序：trigger 位于视口底部 → 父 tree → 子 tree → 最终 `style.top < trigger.top`（即 flip 到上方），不 clamp 到底部。

## 消费者场景

| 消费者 | 场景 | 验收 |
|---|---|---|
| `mutagent` Send 按钮菜单 | 按钮在视口底部，点击后菜单弹出 | 菜单出现在按钮上方，不盖住按钮 |
| `mutgui demo/examples/menu.py` | 各 placement 示例 | 行为不变 |
| 业务方推送空菜单 view（理论） | 后端 push `[]` tree | Menu 挂载，显示空菜单（不被吃掉）|
| hover 子菜单（如 `MenuItem onMouseEnter`）| 用户快速划过多个父项 | 每个子菜单使用对应父项的 trigger 位置，不串位 |

## 关于落地范围

- 主体改动集中在 `frontend/src/core/renderer.tsx`（约 15 行）+ `frontend/src/components/menu.tsx`（暴露 `takePendingMenuTrigger` + `Menu` 接受 `initialTrigger` prop，约 10 行）。
- 不动 `menu-layout.ts`、不动 `Menu` 内部几何逻辑、不动 `ResizeObserver` 行为。
- main 上现存 commit `afccd3a`（"resize 时重跑完整布局"）是治标方案，本 bugfix 不直接 revert，但本 PR 让它变成多余的兜底；可在后续清理 PR 中评估是否回滚。

## 实施步骤清单

- [x] `menu.tsx`：暴露 `takePendingMenuTrigger()`，`Menu` 增加 `initialTrigger?: TriggerInfo | null` prop，内部优先使用 `initialTrigger` 取代直接读 `pendingTrigger`
- [x] `renderer.tsx`：`tree` state 改 nullable（`ComponentSchema[] | null`，初值 `null`），菜单分支用 `useState` lazy initializer 同步 take trigger，`tree === null` 时 `return null`，普通分支 `tree === null ? null : renderTree(tree)`
- [x] 检查 `MutguiView` 其他依赖 `tree` 的代码路径（含初始空数组的隐式假设）是否兼容 — 仅 MutguiView 内部读 tree，均已处理 null；renderTree 签名未变
- [x] 构建前端 `npm --prefix frontend run build`，确保 TS 类型检查 + 构建通过
- [x] 跑全部前端测试 `npm --prefix frontend test` 确认无回归 — 6 files / 40 tests 全过
- [x] 手工验证（待用户执行）：在 mutagent webui 里复现原场景点击 Send 旁边下拉菜单，确认 flip 到上方不盖住按钮

### 遗留项

- **组件级回归测试**（未完成）：验证未收到首帧不挂 Menu / 收到 `[]` 仍挂 Menu / 防退化为 `tree.length === 0`。
  原因：当前 frontend 测试基础设施只有纯函数 vitest（无 jsdom / @testing-library/react），引入会显著扩大本 PR 范围。
  后续动作：单独开 PR 引入 React 组件测试基础设施后补上本 bug 的回归测试。
- **清理 `effectiveAnchorRef` / `recomputePosition` 死代码**（未完成）：main 上 `afccd3a` 补的 RO relayout 现在变成多余兜底逻辑。建议后续独立 PR 清理（评估是否 revert afccd3a）。
