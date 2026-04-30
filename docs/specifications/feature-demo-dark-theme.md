# Demo 深色主题适配 设计规范

**状态**：✅ 已完成
**日期**：2026-04-22
**类型**：功能设计

## 需求

`feature-builtin-css` 完成后，mutgui 内置组件（Menu / DockPanel / VirtualList）默认是深色主题。但 demo 本身还是旧的浅色风格：

- `demo/examples/*.py` 的 HTML page chrome（body 背景、标题、按钮）写死浅色（`#fafafa`、`#666`、`#1677ff` 等）
- Python 端 `ViewBlock` 里用 `"style": {...}` 硬编码的面板色板（如 `dock.py` 每个 panel 不同的浅色背景 `#e8f5e9` / `#e3f2fd` 等）
- 运行 demo 时，深色的 mutgui 组件嵌在浅色页面里，视觉混乱

### 目标

- **demo 默认适配深色**，不给 demo 增加"切主题"的代码能力 —— mutgui 就是深色的，demo 作为消费者直接跟着走
- demo 的 page chrome 通过 `--mutgui-*` token 引用，不写死色值
- demo 成为 mutgui token API 的第一个真实消费者 —— 反向验证当前暴露的 token 对普通宿主（即非 mutgui 组件的"周边区域"）是否够用

### 非目标

- 不做主题切换 / 浅色支持 / 用户偏好
- 不动 mutgui 组件的默认样式（那是 `feature-builtin-css` 的范围）
- 不做 demo 的交互 / 功能改动，只改视觉

## 范围

### 页面层（HTML `<style>`）

所有 demo 的 `MENU_HTML` / `DOCK_HTML` / ... 字符串里的 `<style>` 块：

- body / html 背景、前景色：改用 `--mutgui-bg` / `--mutgui-text`
- 标题 h2 / h4 / h3：改用 `--mutgui-text` 和 `--mutgui-text-dim`
- page-level 按钮、hover 态、边框：改用 `--mutgui-surface` / `--mutgui-border` / `--mutgui-accent`

涉及文件：
- `demo/examples/basic.py`
- `demo/examples/nesting.py`
- `demo/examples/virtual_list.py`
- `demo/examples/dock.py`（部分已改，复查）
- `demo/examples/menu.py`（部分已改，复查）
- `demo/examples/antd.py`
- `demo/examples/mahjong.py`（如果存在且未归档）

### Python 端 ViewBlock 内联 style

`"style": {...}` 里硬编码的颜色，分两类处理：

1. **功能性颜色**（log 面板背景、提示文字色等，只表达"这里是不同区域"）→ 改用 token（`--mutgui-surface` / `--mutgui-text-dim`）
2. **装饰性多彩**（DockPanel demo 里每个 panel 不同颜色，用于演示 "这是多个独立 panel"）→ 保留硬编码，但改成深色背景上协调的饱和色

第二类的具体色值留到设计阶段具体讨论，原则是与深色背景协调、彼此区分度足够。

## 关键参考

- `mutgui/frontend/src/styles/base.css` — 当前暴露的核心 token：`--mutgui-accent` / `--mutgui-bg` / `--mutgui-surface` / `--mutgui-text` / `--mutgui-text-dim` / `--mutgui-border`
- `mutgui/docs/specifications/archive/` 里的 `feature-builtin-css.md`（实施完成后归档）— token 设计背景
- `demo/examples/menu.py:274-297` 和 `demo/examples/dock.py:113-132` — 已部分改为 token 的样例，可参考延续

## 设计阶段要回答的问题

1. **demo HTML `<style>` 要不要引入一段共享 chrome**？现在每个 demo 各写各的 `body/h2/...`，都改成 token 后差异很小，可以抽到 `demo/framework/` 的公共 HTML 模板里
2. **现有核心 token 够用吗**？遇到 demo 需要但 mutgui 没暴露的语义色（如 success / warning / error 提示色），要区分：
   - 如果是 mutgui 组件未来也需要的 → 反推加到 mutgui 核心 token
   - 如果只是 demo 自己的装饰 → demo 硬编码，不污染 mutgui API
3. **DockPanel demo 的彩色 panel 是否保留**？彩色面板的设计初衷是"多 panel 可辨识"，但深色下需要重新配色。或者改为同色（不同 title 足以区分）？

## 消费者场景验证

demo 作为 mutgui token 的消费者，完成后应能说出：
- 哪些 token 覆盖了 demo 的需求（列清单）
- 哪些场景不得不硬编码（说明原因，判断是否需要扩展核心 token）
- 对 mutgui token API 的反馈（命名、粒度、缺口）

这部分是本 feature 对 mutgui 框架本身的**副产物价值**，不是额外工作 —— 设计阶段就把验收标准加入。

## 设计方案

### 问题本质

mutgui 内置组件是深色，但 HTML 默认 `color-scheme: light` + 白底黑字。当前 `base.css` 声明了 token 但**未给 body 设置默认背景**（因为组件库不应侵入宿主）。

**核心矛盾**：
- "零配置可看" vs "library 消费者不被强制设置整页背景"

### 解决方案：opt-in `.mutgui-theme` class

提供一个**显式激活**的页面级主题 class，消费者在 `<body>` 或 `<html>` 上加这个 class 即生效；不加 = 组件样式零侵入。

```css
@layer mutgui.theme {
  :is(html, body).mutgui-theme {
    background: var(--mutgui-bg);
    color: var(--mutgui-text);
    color-scheme: dark;
    min-height: 100vh;
  }
}
```

### 关键决策

**为什么是 class 而非改 body**（CSS 社区惯例：组件库不动宿主 body/html；消费者要的是"能选"，不是"被强制"）

**为什么不独立 `theme.css` 文件**（class 不激活时零影响，放进 `core/base.css` 不多一个文件/一份配置；激活机制在 HTML 上而非 CSS import 上）

**为什么 `.mutgui-theme` 而非 `.mutgui-root`**（`.mutgui-root` 已承担 token 作用域语义，两者分开更清晰：`.mutgui-root` = "这里挂 token"，`.mutgui-theme` = "整页套默认主题"）

**为什么 `:is(html, body)`**（消费者可以挂到任一层级。html 级影响滚动条深色，body 级只影响可视区。两种都允许）

### 实施位置

依赖 `refactor-frontend-layout` 先完成，文件位置按重构后布局：

- `mutgui/frontend/src/core/base.css` — 追加 `:is(html, body).mutgui-theme { ... }` 规则到 `@layer mutgui.theme`
- `mutgui/demo/framework/_routes.py::mutgui_page` — 默认 HTML 模板 `<body>` 加 `class="mutgui-theme"`
- 自定义 HTML 的 demo（通过 `MutguiRoute(..., html=...)` 传入）— 消费者自行决定是否加 class

### 完全定制的消费者路径

- **保留 mutgui 组件样式 + 自己的页面主题**：HTML 不加 `.mutgui-theme` class，`<body>` 写自己的 CSS；mutgui 组件仍按 token 渲染（深色），消费者可通过覆盖 `:root { --mutgui-bg: ...; }` 改 token 值
- **完全不要 mutgui 样式**：library 模式下不 `import '@mutgui/core/styles.css'` 即可（standalone IIFE 模式样式内联注入，不提供"只要 JS 不要 CSS"选项 —— 若需要此场景，后续另议）

### demo 页面层改造（原需求范围内）

沿用原需求章节的分类，在 opt-in `.mutgui-theme` 激活后：
- body 默认背景/前景已由 `.mutgui-theme` 提供，demo 的 `<style>` 块可**移除** body/html 的颜色声明
- 标题 / 按钮 / 边框等 page chrome：仍需各自引用 `--mutgui-*` token（不由 `.mutgui-theme` 统一管理，因为属于 demo 内部的装饰层）
- Python 端 `ViewBlock` 的 `"style": {...}` 处理方式不变（功能性颜色 → token；装饰性多彩 → 深色协调硬编码）

### 消费者验证

demo 本身就是第一个 opt-in 消费者：加 `class="mutgui-theme"` 后一行激活的体验，验证此方案对"纯 HTML + script 标签"场景的可用性。

### Q&A（已确认，归档至决策理由）

- 是否提供默认主题？ → **提供，但 opt-in**（不加 class 不生效，保持组件库不侵入宿主的惯例）
- 主题样式放哪？ → **并入 `core/base.css`**（和 token 声明在同一文件，语义紧凑；不需要独立 `theme.css`）
- class 命名 → **`.mutgui-theme`**（与 `.mutgui-root` 的 token 作用域语义分开）
- 支持挂在哪个标签？ → **html 或 body 都行**（`:is(html, body).mutgui-theme`）

## 实施步骤清单

**前置依赖**：`refactor-frontend-layout` 实施完毕（`core/base.css` 已就位）

- [x] **在 `core/base.css` 追加 opt-in 主题规则**（`:is(html, body).mutgui-theme { background / color / color-scheme / min-height }`，归入 `@layer mutgui.theme`）
- [x] **默认 demo 模板加 class**：修改 `demo/framework/_routes.py::mutgui_page`，`<body>` 加 `class="mutgui-theme"`
- [x] **自定义 HTML demo 处理**：
  - [x] `demo/examples/dock.py` 的 `DOCK_HTML` 模板 `<body>` 加 `class="mutgui-theme"`
  - [x] `demo/examples/menu.py` 的 `MENU_HTML` 模板 `<body>` 加 `class="mutgui-theme"`
- [x] **demo `<style>` 块清理**：各 demo 原本硬编码的 body 背景/前景色声明可移除（由 `.mutgui-theme` 统一提供）
- [x] **demo chrome token 化**（原需求范围）：
  - [x] `demo/examples/basic.py` 的 page chrome 颜色改用 `--mutgui-*` token（无自定义 `<style>` 块、无硬编码色，零改动）
  - [x] `demo/examples/nesting.py` 同上（零改动）
  - [x] `demo/examples/virtual_list.py` 同上（零改动）
  - [x] `demo/examples/antd.py` 同上（零改动）
  - [x] `demo/examples/mahjong.py` ViewBlock 内多处功能色改 token，装饰色（current 高亮、座位名、进入链接）调至深色协调饱和色
  - [x] `demo/examples/dock.py` 复查已改部分 —— header 已引用 token，`body` 颜色声明清理完
  - [x] `demo/examples/menu.py` 复查已改部分 —— body 的 `#fafafa`、h4 的 `#666`、ViewBlock 内 search 框/empty hint/context tab/两个按钮/日志 `<pre>` 全部改 token
- [x] **Python 端 ViewBlock style 颜色分类处理**：
  - [x] 功能性颜色（log 面板背景、hint 文字等）→ 改用 `--mutgui-surface` / `--mutgui-text-dim` token
  - [x] 装饰性多彩（DockPanel demo 的多 panel 区分色）→ 深色协调硬编码：用 `oklch(0.28 0.04 <hue>)` 保持亮度一致、色相区分，编辑区（`main-py` / `utils-py`）用中性深灰，terminal 用更暗灰
- [x] **构建 + 运行验证**：`npm run build` 已通过（216.82 kB），用户启动 `python demo/app.py`，逐个 demo 目测深色一致性 —— 留待用户验证
- [x] **消费者场景回顾**：实施结尾补充「token 覆盖清单 / 硬编码场景 / API 反馈」三条到文档（对应"消费者场景验证"章节）

## 消费者场景验证总结

demo 作为 mutgui token 的第一个真实消费者，实施后回收到以下反馈。

### token 覆盖清单

demo 中通过 `var(--mutgui-*)` 引用的 token：

| token | 使用场景 |
|------|---------|
| `--mutgui-bg` | 由 `.mutgui-theme` 隐式使用（body 背景）；menu search input 的输入背景 |
| `--mutgui-surface` | menu context tab 块背景、menu "⌘ Open Palette" 按钮背景、menu 日志 `<pre>` 背景、dock panel 默认背景 |
| `--mutgui-text` | 由 `.mutgui-theme` 隐式使用（body 前景）；menu 各按钮文字色、menu search input 文字色、mahjong 对家姓名（非高亮态）、dock panel 内文字 |
| `--mutgui-text-dim` | menu h4 标题、menu "No commands match" hint、menu 面板内次级 info；mahjong 状态提示 / 等待中 / 弃牌文字 / 牌墙张数 / hand-label |
| `--mutgui-border` | menu 所有按钮/input 的描边、menu 日志 pre 的描边；mahjong 中心虚线框、座位卡边、对家分隔线 |
| `--mutgui-accent` | menu "+ Add" 按钮背景 + 描边（主行动按钮） |

### 不得不硬编码的场景

1. **dock.py 多 panel 装饰色**（绿/蓝/粉/橙/黄/紫/红/青 + 中性深/终端暗）
   原因：demo 的目的是"演示多 panel 可辨识"，需要 8+ 种彼此区分的饱和色。mutgui 核心 token 只有一个 accent，语义上不应扩展成调色板。
   做法：`oklch(0.28 0.04 <hue>)` 固定亮度+弱饱和，仅靠 hue 区分，保证和深色背景协调。

2. **mahjong 的 `#ff7875`（current-turn 高亮红）/ `#69b1ff`（座位蓝 / 进入链接蓝）**
   原因：mahjong 的"当前回合"需要一个 warning/alert 语义色；座位名 / 链接需要一个独立于 accent 的"信息蓝"语义色。mutgui 核心 token 没有 warning / info 色，且 accent（蓝）会和座位蓝混淆。
   做法：保留硬编码，从 Ant Design 的深色模式推荐色值（`#ff7875` / `#69b1ff`）直接取用。

3. **mahjong 的 `oklch(0.30 0.05 70)` / `oklch(0.55 0.12 70)`（刚摸的牌高亮）**
   原因：需要一个"黄色标识 + 描边"表达"刚摸到"，性质同 #1（语义装饰色）。

### 对 mutgui token API 的反馈

- **命名 / 粒度 OK**：6 个核心 token 够覆盖"普通宿主的 page chrome"需求（背景 + 浮层 + 主/次文字 + 描边 + accent）。
- **明显缺口：语义状态色（success / warning / error / info）**
  - mahjong 的 current-turn 红、座位蓝都是 status/info 语义；menu 的 log `<pre>` 没用到但未来可能需要 error/warning hint。
  - 建议：未来 mutgui 组件自身如果要支持 danger button / error message / toast，可以考虑补充 `--mutgui-danger` / `--mutgui-warning` / `--mutgui-success` / `--mutgui-info` 四个语义 token（或复用 antd 的色值约定）。短期不加也行，demo 继续硬编码。
- **opt-in `.mutgui-theme` 方案验证通过**：纯 HTML + `<script>` 宿主加一行 class 即生效，零配置可看，且不阻止消费者自定义（消费者可在 body 写自己的 CSS 覆盖）。
- **dock panel 的彩色面板**：硬编码 oklch 调色板效果良好，但提示了另一个潜在需求 —— 如果未来 mutgui 要提供"多视图区分色"的 helper（例如 color-mix 派生的 hue palette），demo 这个场景会第一时间受益。

---

## 重新设计（2026-04-22）

### 触发原因

第一轮实施完成后真实打开 demo，发现问题：
- antd 组件（Card / Typography / Form / Input）仍是**亮色**（白底黑字），因为 `integrations/antd.ts` 没有配置 ConfigProvider，antd 默认就是 light。
- 结果：mutgui 组件（Menu/DockPanel）+ body 是深色，嵌在里面的 antd 组件是亮色，整体错乱。
- 第一轮我为了"看起来像深色"在大量 ViewBlock 里硬编码了 `var(--mutgui-*)`，但这与"demo 不应该写 CSS 定制颜色"的核心诉求背道而驰。

### 设计原则重新确立

用户澄清了底层理念：

1. **mutgui 框架不认识"主题"概念**。框架只提供"基础配色原语"（`--mutgui-*` CSS var），不替用户做主题选择。
2. **框架默认值应该对齐主流组件库 —— 亮色**。浏览器默认亮色、antd 默认亮色、MUI / Chakra / Mantine 都默认亮色。mutgui 作为底层 CSS 框架，默认值应该同步。"什么都不做 = 亮色"才是正确状态。
3. **暗色是一个"内置 plugin"**。因为暗色是常见需求，mutgui 提供一份**参考实现**，告诉用户"要切到其他主题，照这个路径做就行"。这个 plugin 和用户自己写的 plugin **完全对等**。
4. **demo 默认加载这个 plugin 呈现暗色**。但 demo 本身是 plugin 的**消费者**，不是框架的一部分。

### 核心机制：通用 Plugin 协议

mutgui 新增一个通用扩展点，不涉及 theme / antd / i18n 任何具体概念。

```ts
type MutguiPlugin = (ctx: PluginContext) => void;

interface PluginContext {
  addCss(css: string): void;                              // 注入 <style> 到 document.head
  addBodyClass(className: string): void;                  // 加到 document.body 的 class
  wrapRoot(wrap: (children: ReactNode) => ReactNode): void;  // 根渲染树外包一层 React
}

MutguiApp.mount(
  el: HTMLElement,
  wsUrl: string,
  plugins?: MutguiPlugin[],
  options?: { onStatus?: (status: string) => void },  // 原有 options 保留
): void;
```

**不支持**：单个 plugin 参数（必须传数组）、mount 后追加 plugin、移除 plugin。

**Plugin 之间关系**：
- 数组顺序决定 CSS 注入顺序（后注入的优先级更高）和 body class 加入顺序（无所谓）
- `wrapRoot`：数组中靠前的在外层，靠后的在内层

### 关键决策（已确认）

- **为什么 plugin 是单函数而不是结构对象**（对象形态暴露 `{ css, wrap, bodyClass }` 让调用者看字段）
  决策：单函数。plugin 只有一个入口，ctx 的方法是框架提供的能力面板。plugin 行为可编程（循环、条件、闭包），对象形态只能声明固定字段。
- **为什么不做 `addRootWrapper` 注册表**（"加载即注册"的魔法）
  决策：零副作用的 plugin 更干净。script 加载只挂 `window.MutguiXxx`，消费者主动 `mount(el, ws, [MutguiXxx])` 才生效。
- **为什么不做 mount 的 `theme` 参数**
  决策：框架不认识 theme。Plugin 协议里只有"css / bodyClass / wrapRoot"三个中性能力，没有任何一项叫 theme。theme-dark plugin 是这个协议的一个消费者而已。
- **为什么必须数组不能单个**
  决策：API 单一形态，消费者心智更简单，无歧义。传单个 plugin 就是 `[MutguiXxx]`，成本可忽略。

### 暗色主题 plugin: `mutgui-theme-dark.js`

**源码位置**：`mutgui/frontend/src/plugins/theme-dark/`
- `dark.css` —— 在 `.mutgui-dark` class 下覆盖所有 `--mutgui-*` token 成深色值，并设置 `body.mutgui-dark { background, color, color-scheme }`
- `index.ts` —— 通过 `?inline` 把 `dark.css` 打成 JS 字符串，实现 plugin 函数

**构建配置**：新增 `mutgui/frontend/vite.theme-dark.ts`（IIFE 模式，产物 `mutgui-theme-dark.js`）
**npm script**：新增 `build:theme-dark`

**plugin 内部伪代码**：

```ts
import darkCss from './dark.css?inline';
import { ConfigProvider, theme as antdTheme } from 'antd';
import React from 'react';

const darkAntdTheme = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    // 把 mutgui 的 --mutgui-accent 映射到 antd 的 colorPrimary
    // 因为 antd token 是 JS 值,CSS var 触达不到,只能在 JS 里写一份对应值
    colorPrimary: '#6a9ff5',  // 对应 oklch(0.65 0.16 250) 附近
  },
};

(window as any).MutguiThemeDark = (ctx) => {
  ctx.addCss(darkCss);
  ctx.addBodyClass('mutgui-dark');
  ctx.wrapRoot(c => React.createElement(ConfigProvider, { theme: darkAntdTheme }, c));
};
```

### `base.css` 回退改造

- 撤掉上一轮加的 `:is(html, body).mutgui-theme { ... }` 规则
- Token 默认值从深色改为亮色：

```css
:where(:root, .mutgui-root) {
  color-scheme: light;
  --mutgui-accent:    oklch(0.55 0.18 250);
  --mutgui-bg:        oklch(0.99 0 0);       /* 近白 */
  --mutgui-surface:   oklch(0.97 0 0);       /* 浅灰浮层 */
  --mutgui-text:      oklch(0.20 0 0);       /* 深色主文字 */
  --mutgui-text-dim:  oklch(0.50 0 0);
  --mutgui-border:    oklch(0.88 0 0);
}
```

- 暗色 token 搬到 plugin 的 `dark.css`：

```css
body.mutgui-dark,
body.mutgui-dark .mutgui-root {
  --mutgui-accent:    oklch(0.60 0.16 250);
  --mutgui-bg:        oklch(0.22 0 0);
  --mutgui-surface:   oklch(0.27 0 0);
  --mutgui-text:      oklch(0.88 0 0);
  --mutgui-text-dim:  oklch(0.62 0 0);
  --mutgui-border:    oklch(0.35 0 0);
  background: var(--mutgui-bg);
  color: var(--mutgui-text);
  color-scheme: dark;
}
```

### 为什么 mutgui 组件不再"默认深色"

之前 `feature-builtin-css` 的默认 token 是深色，意味着 mutgui Menu/DockPanel/VirtualList 开箱即深色。重新设计后它们变成"跟随 token"—— 默认亮色（和 antd 一致），在 `.mutgui-dark` 下变暗色。这是对 `feature-builtin-css` 默认取向的调整，但组件样式机制不变（仍然全靠 token）。

### demo 消费者改造

**`demo/framework/_routes.py::mutgui_page` 模板**：
```html
<body>
  <div id="app"></div>
  <script src="/static/mutgui.js"></script>
  <script src="/static/mutgui-antd.js"></script>
  <script src="/static/mutgui-theme-dark.js"></script>
  <script>
    MutguiApp.mount(document.getElementById('app'), wsUrl, [MutguiThemeDark]);
  </script>
</body>
```
- 去掉上轮加的 `class="mutgui-theme"`
- 增加 `mutgui-theme-dark.js` 的 script 标签
- mount 传入 `[MutguiThemeDark]`

**`dock.py` 的 `DOCK_HTML` 和 `menu.py` 的 `MENU_HTML`**：同步加 plugin 脚本 + mount plugin 数组。

**所有 demo 的 ViewBlock 硬编码色**：
- 上一轮为了"看起来像深色"硬塞的 `var(--mutgui-*)` 全部**回退**（因为 antd 现在真深色了，Card / Typography / Button 自动就对）
- `dock.py` 的 11 个装饰色板保留（合法的多 panel 区分色）
- `mahjong.py` 的语义红/蓝装饰色保留（业务语义色，plugin 不该管）

### 新增 demo：`demo/examples/theming.py`（历史记录，后续已移除）

演示 plugin 机制：
- 默认加载 `[MutguiThemeDark]` 是深色
- 提供按钮切换到"浅色"（传空数组 `[]`）
- 提供按钮切换到"自定义紫色主题"（一个 demo 级别自己写的 plugin，颜色换成紫色系）

因为 mount 只能一次（再 mount 要先 unmount 重来），这个 demo 可能通过**页面刷新 + URL 参数**实现不同模式，或者使用 `window.location.reload()` 触发重新加载。具体实现方案实施时再定。

## 实施步骤清单（重新设计版）

- [x] **撤销上一轮 base.css 的改动**：删除 `:is(html, body).mutgui-theme { ... }` 规则
- [x] **base.css token 默认值改亮色**：6 个 `--mutgui-*` token 换为亮色值；`color-scheme: light`
- [x] **扩展 MutguiApp.mount 签名**：
  - [x] `mount(el, wsUrl, plugins?: MutguiPlugin[], options?)` 四参数（plugins 在 options 之前，因为更常用）
  - [x] 实现 PluginContext：`addCss` / `addBodyClass` / `wrapRoot`
  - [x] 遍历 plugins 数组，每个 plugin `p(ctx)`
  - [x] 应用收集到的 CSS / bodyClass / wrappers
  - [x] 现有的 `injectStyles()`（注入 `index.css`）保持不变
- [x] **新建 theme-dark plugin**：
  - [x] `src/plugins/theme-dark/dark.css` —— body.mutgui-dark 下覆盖 token + 背景前景
  - [x] `src/plugins/theme-dark/index.ts` —— `?inline` 导入 CSS + 调 ctx 三方法 + antd ConfigProvider darkAlgorithm
  - [x] `vite.theme-dark.ts` —— IIFE 构建配置
  - [x] `package.json` 的 scripts 加 `build:theme-dark`,并把 `build` 串联构建三份产物
- [x] **mutgui-antd.js 暴露 antd 到全局**：`integrations/antd.ts` 在 `MutguiApp.antd` 下挂 antd 完整命名空间,供 plugin 引用
- [x] **默认 demo 模板改造**：`demo/framework/_routes.py::mutgui_page`
  - [x] 去掉 `class="mutgui-theme"`（上轮残留）
  - [x] 加载 `mutgui-theme-dark.js`
  - [x] mount 传 `[MutguiThemeDark]`
- [x] **自定义 HTML demo 改造**：`dock.py` / `menu.py` 的 `DOCK_HTML` / `MENU_HTML` 同上
- [x] **回退上一轮 ViewBlock 硬编码**：
  - [x] 复查结论:上轮所有 `var(--mutgui-*)` 引用实际都是针对**原生 DOM**(非 antd 组件),token 本身会跟随 body class 切换(亮/暗),保留即正确行为。**无需回退**。
  - [x] `menu.py` —— 保留 search input / empty hint / context tab / 两个按钮 / log `<pre>` 的 token 引用
  - [x] `mahjong.py` —— 保留功能色 token 引用
  - [x] `dock.py` —— `SimplePanelView` 默认背景走 `var(--mutgui-surface)`,有指定装饰色时用装饰色。11 个装饰色板保留
- [x] **新增 theming.py demo**（历史记录：演示 plugin 机制和定制化；该 demo 后续已移除）
- [x] **新增 no_theme.py demo**（演示框架零预设：不加载 theme plugin，mount 传空数组，观察亮色页面）
- [x] **全量构建**：
  - [x] `npm run build`(已串联 antd + theme-dark)
  - [x] 产物:`mutgui.js 217 kB` / `mutgui-antd.js 1524 kB` / `mutgui-theme-dark.js 0.63 kB`
- [x] **用户验证**：启动 demo 逐个目测暗色一致性（antd 组件也应为深色） —— 用户验证通过

## 消费者场景验证（更新版）

实施完成后补充：
- demo 作为 plugin 消费者，加载一个 plugin 就完成深色切换（包括 antd）的体验是否符合预期
- 是否真正做到"demo 几乎不写颜色 CSS"
- Plugin 协议的 ctx 三方法（addCss / addBodyClass / wrapRoot）对暗色主题够用吗？未来 i18n / error-boundary plugin 能否走同协议
- 历史上的 `theming.py` 演示定制路径是否清晰

