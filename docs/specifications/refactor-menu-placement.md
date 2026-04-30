# 菜单 Placement 重构 — 锚点对齐 + 自动 flip

**状态**：✅ 已完成
**日期**：2026-04-28
**类型**：重构

## 需求

1. **可控的默认弹出方向**。除现有的 `cursor`/`bottom`/`right` 外，需要支持向上/向左等方向（背景：`mutagent` 的 send-mode 切换按钮位于 chat 输入框右下角，菜单需要向左上方弹出）。
2. **菜单尺寸变化时弹出点不变**。菜单内容由后端 push 驱动，可能在显示后因刷新、过滤、异步加载等改变大小；尺寸变化时菜单应该围绕"弹出点（锚点）"伸缩，而不是整体平移。
3. **超出视口时自动处理**。弹出位置 + 弹出方向可能让菜单超出视口边界，行为应与主流菜单系统（Floating UI / Ant Design / Windows 右键菜单）一致：先翻转方向（flip），再沿交叉轴贴边平移（shift），实在放不下用 max-height 内部滚动兜底。

### 现状问题

`feature-menu-system.md` 已实现 `cursor`/`bottom`/`right` 三种 placement，本地修改新增 `top-end` 但实现不完善：

- `placement` 命名风格不统一（`bottom`/`right` 是简写，`top-end` 是 Floating UI 风格）。
- 边缘检测逻辑硬编码在 `Menu` 组件 `useLayoutEffect` 内，每个方向一个 if 分支，新增方向需复制粘贴，无单元测试。
- flip 不对称（`top-end` 只翻 top 不翻 left），且与"全局兜底"的 `vw - rect.width` 平移叠加，破坏锚点对齐。
- `useLayoutEffect` deps 为 `[trigger]`，菜单尺寸变化（如搜索过滤 list）不会触发重算，"弹出点不变"无法保证。
- `requestAnimationFrame` 双重计算只是兜底首次 mount 的尺寸滞后，并非真正监听尺寸变化。

### 前置依赖

- `feature-menu-system.md` — 菜单系统基础（`MenuView`/`MenuTrigger` Declaration、`$menu` wire 协议、portal 渲染、close 机制）

## 关键参考

### 现有实现

- `mutgui/frontend/src/components/menu.tsx` — `Placement` 类型、`createMenuTriggerHandler`、`Menu` 组件 + `useLayoutEffect` 定位
- `mutgui/src/mutgui/menu.py` — `MenuTrigger.__init__` 接受 `placement` 参数、`to_wire()` 写入 `$placement`
- `mutgui/tests/test_menu.py` — `to_wire` 序列化测试覆盖 `placement="bottom"`、`"top-end"`
- `mutgui/frontend/tests/virtual-list-layout.test.ts` — vitest 风格参考（纯函数布局算法的单测样例）

### 调用点（外部消费者）

| 文件 | 当前 placement |
|---|---|
| `mutagent/src/mutagent/ui/_chat_input_impl.py:132` | `top-end`（保留） |
| `mutgui/demo/examples/menu.py:66` | `right` → 改为 `right-start` |
| `mutgui/demo/examples/menu.py:225` | `bottom` → 改为 `bottom-start` |
| `mutgui/demo/examples/menu.py:246` | `bottom` → 改为 `bottom-start` |

### 业内参考

- Floating UI：`{side}-{align}` 命名 + 中间件管线（flip / shift / size）
- Ant Design Dropdown：`placement` 同样用 `{side}-{align}`，子菜单只 flip 一次

## 设计方案

### Placement 命名规范

采用 `{side}-{align}` 格式，对齐 Floating UI / Ant Design 业内惯例。**不保留旧 `bottom`/`right` 别名**，调用点直接改名（用户已确认）。

合法值集合（11 个）：

```
'cursor'
'top-start'    | 'top-center'    | 'top-end'
'bottom-start' | 'bottom-center' | 'bottom-end'
'left-start'   | 'left-end'
'right-start'  | 'right-end'
```

仅 `top` / `bottom` 提供 `center`（业内 dropdown 居中常用），`left` / `right` 不提供 center（用例罕见，按需再加）。

`MenuTrigger.__init__` 在收到非法 placement 时抛 `ValueError`，避免拼错只在前端默默回退。

### 锚点 + 菜单对齐角模型

把"placement 字符串"翻译成统一的几何模型：

```ts
interface Anchor {
  // 锚点：菜单要钉到视口的哪个点
  point: { x: number; y: number };
  // 菜单的哪个角对齐到锚点（start=左/上, end=右/下, center=中线）
  menuAlign: { x: 'start' | 'center' | 'end'; y: 'start' | 'center' | 'end' };
  // 主轴 + 翻转后的备选 point（cursor 模式无）
  flipAxis?: 'x' | 'y';
  flipPoint?: { x?: number; y?: number };
}
```

布局公式（菜单尺寸变化时不变 → 满足需求 2）：

```
left = point.x - (menuAlign.x === 'end' ? width : menuAlign.x === 'center' ? width/2 : 0)
top  = point.y - (menuAlign.y === 'end' ? height : menuAlign.y === 'center' ? height/2 : 0)
```

各 placement 对应的 anchor（以 triggerRect 为基准）：

| placement | point | menuAlign | flipAxis | flipPoint |
|---|---|---|---|---|
| `bottom-start` | (left, bottom) | {start, start} | y | {y: top} |
| `bottom-center` | (centerX, bottom) | {center, start} | y | {y: top} |
| `bottom-end` | (right, bottom) | {end, start} | y | {y: top} |
| `top-start` | (left, top) | {start, end} | y | {y: bottom} |
| `top-center` | (centerX, top) | {center, end} | y | {y: bottom} |
| `top-end` | (right, top) | {end, end} | y | {y: bottom} |
| `right-start` | (right, top) | {start, start} | x | {x: left} |
| `right-end` | (right, bottom) | {start, end} | x | {x: left} |
| `left-start` | (left, top) | {end, start} | x | {x: right} |
| `left-end` | (left, bottom) | {end, end} | x | {x: right} |
| `cursor` | (mouse.x, mouse.y) | {start, start} | — | — |

`cursor` 模式无主轴概念，flip 由两轴独立按"哪边空间大"决定（Windows 右键菜单逻辑）。

### 自动适配视口（flip + shift + size）

参考 Floating UI 的中间件管线，分三层：

1. **主轴 flip**（仅 side-align placement 适用）：如果首选方向溢出，且翻转后空间更大，就把 `menuAlign[flipAxis]` 翻转 + `point[flipAxis]` 替换为 `flipPoint`。
2. **交叉轴 shift**：剩余溢出沿交叉轴平移让菜单贴边（保留 4px margin）。这一轴上锚点会偏移，但菜单完整可见，符合 Windows / Chrome 右键菜单行为。
3. **尺寸约束 size**：flip + shift 后仍超出视口，给出 `maxHeight` / `maxWidth`（视口尺寸 - 2 * margin），由组件套到样式上让菜单内部滚动（已有 `mutgui-scrollbar` class 配合 `overflow: auto`）。

`cursor` 模式特殊处理：两轴独立判断，溢出哪边就把对应 align 翻成 end（point 不变，因为锚点是单点）。

### Flip 决策时机（关键 — 满足需求 2）

**flip 与 shift 决策只在 mount 时做一次，结果锁定到 ref；后续菜单尺寸变化只用锁定的 anchor + 公式重算 left/top，不再 flip 也不再 shift**（决策原因：避免内容动态变化导致菜单一会儿向上一会儿向下"横跳"；与 Floating UI 默认行为一致；符合需求 2"弹出点不变"语义）。

例外：mount 后的尺寸重算包含一个**最小 shift 兜底** — 如果按锁定 anchor 算出的位置让菜单飞出视口（贴边过远），仍允许沿越界方向平移到刚好贴边。这只是防御性兜底，不改变 menuAlign 也不重新 flip。

### 实现拆分

**纯函数模块** `frontend/src/components/menu-layout.ts`：

```ts
export type Side = 'top' | 'bottom' | 'left' | 'right';
export type Align = 'start' | 'center' | 'end';
export type Placement = 'cursor'
  | 'top-start' | 'top-center' | 'top-end'
  | 'bottom-start' | 'bottom-center' | 'bottom-end'
  | 'left-start' | 'left-end'
  | 'right-start' | 'right-end';

export function resolveAnchor(
  placement: Placement,
  triggerRect: DOMRect | undefined,
  cursorPoint: { x: number; y: number } | undefined,
): Anchor;

export interface LayoutResult {
  left: number;
  top: number;
  // mount 时锁定使用的有效 anchor（已 flip + shift 后）
  effectiveAnchor: Anchor;
  maxHeight?: number;
  maxWidth?: number;
}

export function computeMenuLayout(input: {
  anchor: Anchor;
  menuSize: { width: number; height: number };
  viewport: { width: number; height: number };
  margin?: number;  // 默认 4
}): LayoutResult;

// 仅按锚点 + 尺寸算位置 + shift 兜底（不 flip）
export function recomputePosition(
  anchor: Anchor,
  menuSize: { width: number; height: number },
  viewport: { width: number; height: number },
  margin?: number,
): { left: number; top: number };
```

**Menu 组件** `frontend/src/components/menu.tsx`：

- mount 时调 `resolveAnchor` + `computeMenuLayout`，把 `effectiveAnchor` 和 `maxHeight/maxWidth` 锁到 ref。
- 用 `ResizeObserver` 监听菜单尺寸，回调里调 `recomputePosition`（基于锁定的 anchor）。
- `maxHeight/maxWidth` 通过 inline style 应用到菜单容器，配合 `overflow: auto` 让菜单内部滚动。
- 首次打开菜单时通过 `document.body[data-menu-just-opened]` 短暂抑制 `:hover`，直到用户第一次 `pointermove` 再恢复，避免点击打开的同一帧命中首个菜单项 hover。

### 测试策略

- **后端单测** `tests/test_menu.py`：`to_wire` 覆盖几个新 placement、placement 校验抛 `ValueError`。
- **前端纯函数单测** `frontend/tests/menu-layout.test.ts`：
  - 11 种 placement 在视口宽松时返回的 left/top 公式正确
  - 主轴溢出触发 flip（含 cursor 模式两轴独立 flip）
  - 交叉轴 shift 对齐
  - 视口太小时返回 maxHeight/maxWidth
  - "锚点恒定"语义：固定 anchor 不同 menuSize 算出的位置满足"end 角 / start 角不动"
  - `recomputePosition` 不 flip，仅 shift 兜底
- **demo 视觉验证**：见下方"消费者场景"。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| `mutagent` send-mode 菜单 | 输入框右下角按钮，菜单向左上方弹出 | `placement="top-end"` | 按钮不动时菜单右下角对齐按钮右上角；菜单变高时向上增长，右下角不动 |
| `mutgui/demo/examples/menu.py` 已有用例 | 现有右键、下拉、命令面板演示 | `bottom-start` / `right-start` 重命名 | 视觉行为与重构前一致 |
| `mutgui/demo/examples/menu.py` 新增 placement 演示 | 8 方向 placement 矩阵按钮 | 全部 placement | 每个方向都按表中"point + menuAlign"对齐触发按钮 |
| `mutgui/demo/examples/menu.py` 新增 flip 演示 | 触发按钮放在视口四个角附近 | flip + shift + size | 视口边缘的按钮弹出菜单时自动 flip 到反方向；窗口缩小到极致时菜单内部出现滚动 |
| `mutgui/demo/examples/menu.py` 新增 size-stable 演示 | 菜单内容动态增减（搜索过滤 / 展开折叠） | 锚点恒定语义 | 菜单尺寸变化时弹出角（按 placement 决定）固定不动；非弹出角随尺寸增长/收缩 |

## 实施步骤清单

- [x] **新增 `frontend/src/components/menu-layout.ts`** — 类型定义（`Placement` / `Anchor` / `LayoutResult`）+ `resolveAnchor` + `computeMenuLayout` + `recomputePosition` 三个纯函数
- [x] **新增 `frontend/tests/menu-layout.test.ts`** — 覆盖测试策略列出的全部场景
- [x] **重写 `frontend/src/components/menu.tsx` 的定位逻辑** — 移除内联 if/else，改用 `menu-layout.ts` 的纯函数；新增 ResizeObserver 监听；锁定 anchor 到 ref；应用 maxHeight/maxWidth；删除原 `requestAnimationFrame` 兜底
- [x] **更新 `frontend/src/components/menu.tsx` 的 `createMenuTriggerHandler`** — 移除 placement 分支，统一通过 `triggerRect`（或 cursor 模式的 mouse 坐标）传递，由 `resolveAnchor` 在 mount 时翻译
- [x] **后端 `src/mutgui/menu.py`** — 更新 docstring 列出全部 11 个 placement；`__init__` 加 `_VALID_PLACEMENTS` 集合校验
- [x] **更新 `tests/test_menu.py`** — `to_wire` 用例改 `bottom-start`、补 `right-start` / `top-end`，新增 placement 非法值抛 `ValueError` 测试
- [x] **更新调用点**：
  - [x] `mutgui/demo/examples/menu.py:66` `right` → `right-start`
  - [x] `mutgui/demo/examples/menu.py:225` `bottom` → `bottom-start`
  - [x] `mutgui/demo/examples/menu.py:246` `bottom` → `bottom-start`
  - [x] `mutagent/src/mutagent/ui/_chat_input_impl.py:132` 保持 `top-end` 不变（验证仍正确工作）
- [x] **demo 增加 placement 矩阵演示** — `mutgui/demo/examples/menu.py` 新建一节（"Placement matrix"）：placement 按钮矩阵，覆盖全部 side-align placement
- [x] **demo 增加视口边缘 flip 演示** — `mutgui/demo/examples/menu.py` 新建一节（"Edge flip"）：四个按钮贴近视口边缘，分别触发 x / y 方向 flip
- [x] **demo 增加 size-stable 演示** — `mutgui/demo/examples/menu.py` 新建一节（"Resize stability"）：菜单内含 +/- 按钮动态增减菜单项数量，验证弹出角不动
- [x] **更新文档** — `feature-menu-system.md` 的"定位策略"章节已同步新 placement 表与自动适配语义；本文档已标记 ✅ 已完成

## 测试验证

- `python -m pytest tests/test_menu.py`
- `npm --prefix frontend test`
- `npm --prefix frontend run build`
- `npm --prefix frontend run build`
- `python -m pytest` 在当前环境因缺少 `playwright` 依赖而无法完成集成测试收集（`tests/integration/*` 导入失败）

## 实施记录

### 首帧定位与 hover 细节

- 菜单首次 mount 时先放到屏幕外并隐藏，`useLayoutEffect` 里完成自然尺寸测量、`maxHeight/maxWidth` 约束、最终 `left/top` 写回后再显示，消除 `top-*` / `left-*` placement 的首帧位置闪动。
- 点击或右键打开菜单时，浏览器会在菜单可见的同一帧立即重算 hit-test；如果指针正好落在第一项上，会直接触发 `:hover`。最终实现没有给 `TriggerInfo` 增加额外 suppress 字段，而是用全局短生命周期标记 `body[data-menu-just-opened]` + 一次性 `pointermove` 清理，让首帧 hover 抑制对所有触发方式统一生效。

## 待定问题

无（用户已确认接受所有方案，且不保留旧名别名）。

