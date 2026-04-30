# 内置组件 CSS 注入策略 设计规范

**状态**：✅ 已完成
**日期**：2026-04-21
**类型**：功能设计

## 需求

mutgui 内置组件（DockPanel、Menu、未来的更多组件）当前都引用了 className（如 `mutgui-dock-panel`、`mutgui-menu-item`），但**没有任何 CSS 随组件提供**：

- `frontend/src/` 下没有任何 `.css` 文件
- bundle 没注入样式
- demo 的 `<style>` 只含 page chrome，不含组件样式
- 用户开箱即用 mutgui，所有内置组件都是裸 DOM、没有视觉

这违反"开箱即用"原则。需要决定 mutgui 内置组件 CSS 的提供方式。

### 关键约束

1. **不强制依赖**：用户可能用自己的设计系统（Tailwind、antd token、CSS-in-JS），mutgui 不应强行注入大量样式
2. **零配置默认**：但默认情况下，开箱组件应该可见、可用、不丑
3. **可覆盖**：用户可以用更高优先级 CSS 覆盖默认样式
4. **bundle 大小**：CSS 不应让 mutgui.js 显著增大
5. **不依赖 antd**：mutgui 内置组件（DockPanel、Menu）的样式不应假设 antd 在场

### 当前现状

| 组件 | className 用法 | 默认样式 |
|------|---------------|----------|
| DockPanel | `mutgui-dock-panel`, `mutgui-dock-tabset`, `mutgui-dock-tab`, `mutgui-dock-splitter`, `mutgui-dock-overlay` 等十余个 | 无 |
| VirtualList | `mutgui-virtual-list` | 结构样式全部用内联 `style={{...}}`（flex/overflow/position/transform） |
| Menu | `mutgui-menu`, `mutgui-menu-item`, `mutgui-menu-divider`, `mutgui-menu-shortcut`, `mutgui-menu-submenu-arrow` | 仅 demo HTML 内联，不随 mutgui 提供 |

## 关键参考

- `frontend/src/dock-panel.tsx` — 引用 `mutgui-dock-*` className
- `frontend/src/menu.tsx` — 引用 `mutgui-menu-*` className
- `frontend/src/virtual-list.tsx` — 目前结构样式为内联 style，需迁出
- `frontend/vite.standalone.ts` — standalone bundle 构建配置
- `frontend/vite.config.ts` — library bundle 构建配置
- `demo/examples/dock.py` / `demo/examples/menu.py` — demo HTML 当前的 page chrome 样式

## 设计方案

### 本次范围

三个 mutgui 内置组件：**DockPanel + Menu + VirtualList**。

antd 组件、原生 HTML 元素、业务自定义组件不在本次范围内，其样式由应用自己决定。

mutbot 本次完全不变 —— mutbot 目前用 `flexlayout-react`（非 mutgui DockPanel），样式改造将来随 mutbot 重构一并进行。

### 样式分层

所有 mutgui 样式通过 CSS Cascade Layers 组织，用户普通 CSS 天然优先级高于所有 layer，无需 `!important`：

```css
@layer mutgui.base, mutgui.components, mutgui.theme;
```

- `mutgui.base` — 零值重置（如组件内必要的 `box-sizing`、`margin: 0`）
- `mutgui.components` — 组件结构样式（position、flex、overflow、z-index、动画等，不带就坏）
- `mutgui.theme` — CSS 变量默认值（颜色、边框、字号等）

浏览器要求：Chrome 111+ / Safari 16.4+ / Firefox 113+（2023 年 Q1-Q2）。`@layer` 可用于更老的浏览器（Chrome 99+），但 `color-mix()` 和 `oklch(from ...)` 相对色语法需要 Chrome 111+。mutgui 假定用户使用最新浏览器。

### 主题：深色 only

本次只提供一套深色主题，不做 `light-dark()` 方案。token 默认值直接写死深色。

理由：mutgui 的已知消费者（mutbot、编辑器类应用）均为深色界面，没有实际浅色需求。未来需要浅色时再重构为 `light-dark(dark, light)`，重构成本低。

`color-scheme: dark` 显式声明，让浏览器原生 UI（scrollbar、form control）也走深色。

### Token 设计

采用"核心层 + 覆盖层"两层 token 模型。token 挂双作用域，支持全局或局部覆盖：

```css
@layer mutgui.theme {
  :where(:root, .mutgui-root) {
    color-scheme: dark;

    /* 核心层（5-8 个，用户日常只改这些） */
    --mutgui-accent:       oklch(0.60 0.18 250);
    --mutgui-bg:           oklch(0.20 0 0);
    --mutgui-surface:      oklch(0.25 0 0);
    --mutgui-text:         oklch(0.85 0 0);
    --mutgui-text-dim:     oklch(0.60 0 0);
    --mutgui-border:       oklch(0.30 0 0);
  }
}
```

**颜色空间选择 OKLCH**：感知均匀的亮度维度，允许从基色派生状态色（hover/active/disabled），用户只需提供一个基色，组件自动派生完整状态序列。具体 token 默认值在实施阶段按 mutbot VS Code Dark 主题视觉参考校准。

**状态色派生**：组件内部用 `color-mix(in oklch, ...)` 或 `oklch(from var(--mutgui-accent) ...)` 从核心 token 派生 hover/selected/pressed 态，不暴露单独的 `--mutgui-accent-hover` 等 token。

**覆盖层**：每个组件另外暴露若干组件专属 token，默认 fallback 到核心：

```css
.mutgui-menu {
  background: var(--mutgui-menu-bg, var(--mutgui-surface));
  border: 1px solid var(--mutgui-menu-border, var(--mutgui-border));
}
```

大多数用户只调核心，精细用户可针对单个组件调整。

**双作用域作用**：
- `:root` —— 宿主全局覆盖（最常见用法）
- `.mutgui-root` —— 任意容器包 `class="mutgui-root"` 局部覆盖（多实例、嵌套场景）

### className 命名

延续现有 `mutgui-` 前缀全局 class（如 `mutgui-menu-item`）。前缀长度足够隔离，覆盖门槛最低。不采用 CSS Modules 或 data 属性方案。

### 文件组织

```
frontend/src/styles/
  index.css          ← 入口，@layer 声明 + @import 子文件
  base.css           ← layer base + token 默认值（layer theme）
  menu.css           ← layer components
  dock-panel.css     ← layer components
  virtual-list.css   ← layer components
```

每个组件一个 CSS 文件，与 tsx 一一对应，方便维护。

### 交付方式：library / standalone 分离

两种构建产物，同一份 CSS 源码：

| 构建 | CSS 处理 | 用户动作 |
|------|---------|---------|
| **library**（`npm run build`） | 产出独立 `dist/styles.css` | `import "mutgui/styles.css"` |
| **standalone**（`npm run build`） | `?inline` query 读取字符串，运行时注入 `<style>` | 零动作 |

**Vite 实现**：
- library：`build.cssCodeSplit: false`，CSS 自动产出独立文件
- standalone：入口 `standalone.tsx` 中 `import css from './styles/index.css?inline'` + 运行时 `document.head.appendChild(<style>)`

**铁律：tsx 文件不得 `import './xxx.css'`**。CSS 仅从构建入口引入，防止 library 构建把 CSS 意外 inline 进 JS bundle，破坏两种产物的一致性。

**package.json exports**：

```json
{
  "exports": {
    ".": "./dist/index.js",
    "./styles.css": "./dist/styles.css"
  }
}
```

**不拆分 theme.css**：主题 token 默认值与结构样式一起打包进单个 `styles.css`。未来若有"完全自定义主题"需求再拆分（YAGNI）。

**不按组件单独导出**：不提供 `mutgui/styles/menu.css` 这种粒度。当前组件数量少，精细引入收益低。

### VirtualList 迁移

当前 VirtualList 的结构样式全部用内联 `style={{...}}`（flex/overflow/position/transform）。本次将其迁到 `virtual-list.css`，进入 `@layer mutgui.components`。

收益：与其他组件风格统一；内联 style specificity 最高，当前用户想覆盖 VirtualList 结构行为（比如禁用 `overflow: auto`）只能 `!important`，迁到 layer 后普通 CSS 即可覆盖。

保留内联 style 的情况：随状态计算的动态值（如 `transform: translateY(${offsetTop}px)`、`height: ${estimatedTotalHeight}px`），必须保留在 tsx 内。

## 后续工作（不在本次范围）

- 浅色主题：通过 `light-dark(dark, light)` 补齐 token 值，声明 `color-scheme: light dark` 并提供 `[data-theme]` 手动切换
- 主题预设（VS Code Dark / Material / 自定义）
- Token 文档站：列出所有 public token 及其默认值，供用户查阅

## 实施步骤清单

### 建立样式基础设施

- [x] 创建 `frontend/src/styles/` 目录，新建 5 个 CSS 文件（`index.css` / `base.css` / `menu.css` / `dock-panel.css` / `virtual-list.css`）
- [x] `index.css` 声明 `@layer mutgui.base, mutgui.components, mutgui.theme` 并 `@import` 各子文件
- [x] `base.css` 定义 `:where(:root, .mutgui-root)` 的 token 默认值（核心层 6 个变量，深色，OKLCH），`color-scheme: dark`

### 迁移 Menu 样式

- [x] 把 `demo/examples/menu.py` HTML `<style>` 中的 `.mutgui-menu-*` 样式提炼到 `styles/menu.css`，改写为深色 OKLCH token 引用
- [x] hover 态用 `color-mix(in oklch, var(--mutgui-accent) N%, ...)` 派生，不新增 hover token
- [x] 暴露 Menu 组件级 token（`--mutgui-menu-bg`、`--mutgui-menu-border`、`--mutgui-menu-hover-bg`），默认 fallback 到核心
- [x] 清理 `demo/examples/menu.py` HTML 中的 `.mutgui-menu-*` 样式块，只保留 page chrome（body、h2、h4）

### 迁移 DockPanel 样式

- [x] 读 `dock-panel.tsx` 所有内联 `style={{...}}` 块，区分**静态结构样式**（position/flex/overflow/z-index 等）和**动态值**（随 state 计算的 width/height/transform）
- [x] 静态结构样式抽到 `styles/dock-panel.css`（mutgui-dock-panel / -overlay / -split / -splitter / -merged-bar / -tabbar / -tab / -tab-active / -action / -content / -tabset / -tabset-collapsed）
- [x] 默认视觉样式（border、background、color）用 OKLCH token 定义，暴露 `--mutgui-dock-*` 组件级 token fallback 到核心
- [x] 修改 `dock-panel.tsx`，移除已迁到 CSS 的静态 style 属性，仅保留动态值

### 迁移 VirtualList 样式

- [x] 把 `virtual-list.tsx:126-134` 的容器静态 style（flex/min-height/overflow/position）迁到 `styles/virtual-list.css` 的 `.mutgui-virtual-list`
- [x] `virtual-list.tsx` 内层容器（占位+translateY 层）没有 className，属于实现细节，保持内联 —— 不对外暴露覆盖能力
- [x] `virtual-list.tsx:148-150` 的 `minHeight: DEFAULT_ITEM_HEIGHT` 保留内联（随常量计算）
- [x] tsx 内 `style` prop 只保留动态值和调用者透传的 `...style`

### 构建配置

- [x] `vite.config.ts`（library）加入 `build.cssCodeSplit: false` 和显式的 CSS 入口，确保 CSS 输出为单一 `dist/styles.css`
- [x] `vite.standalone.ts` 入口改造：`standalone.tsx` 顶部 `import css from './styles/index.css?inline'` + mount 时注入 `<style>`，确保 IIFE 产物自带样式
- [x] `package.json` 添加 `exports` 字段，暴露 `./styles.css`

### 核对铁律

- [x] 全局 Grep `import .*\.css` 确认所有 tsx 文件都**没有** import CSS（只有 `standalone.tsx` 的 `?inline` import 允许）

### 构建与验证

- [x] `npm run build` 成功，产物 `dist/styles.css` 存在且包含所有组件样式（3.80 kB，含 `@layer` 声明 + Menu + DockPanel + VirtualList 全部规则）
- [x] `npm run build` 成功，`src/mutgui/static/mutgui.js` 内嵌样式（grep 确认 `mutgui-menu` / `mutgui-dock` / `mutgui-virtual-list` / `@layer` 都在 bundle 中）
- [x] menu demo：Menu 默认深色可见、hover 态正确（用户验证通过）
- [x] dock demo：DockPanel 默认深色可见、拖拽/tab 切换/splitter 正常（用户验证通过）
- [x] VirtualList（DockPanel 中）滚动/虚拟化正常（用户验证通过）
- [x] `@layer` 级联行为正常，用户普通 CSS 无需 `!important` 即可覆盖 mutgui 默认样式

## 遗留工作

本次只做了 mutgui 组件**自身**的深色样式。demo 的 page chrome（body / 标题 / 各类示例卡片）仍为浅色硬编码，与 mutgui 组件的深色主题不一致。

计划下一个 spec `feature-demo-dark-theme.md` 专门处理：把 demo 的 page chrome 改为引用 `--mutgui-*` token，作为第一个消费者验证 token API 的完整性。

