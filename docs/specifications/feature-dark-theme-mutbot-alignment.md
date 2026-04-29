# Dark Theme 对齐 mutbot + CSS 契约测试

**状态**：✅ 已完成
**日期**：2026-04-22
**类型**：功能设计

## 需求

1. mutgui 内置暗色主题（`theme-dark` plugin）与 mutbot 视觉对齐
   - 主要背景色对齐 mutbot 体系（`#1F1F1F` / `#262526` / `#3C3C3C` 三档）
   - Accent 色对齐 VS Code 蓝（`#007acc`）
2. DockPanel 视觉细节调整
   - tabbar 与 panel content 之间无 1px 分割线
   - active tab 无蓝色下划线 indicator（只靠背景色区分）
   - tabset 无外边框
   - dock demo 面板不再强塞彩色背景（统一走 panel content 底色）
   - 顶部 demo header 说明文字去掉
3. 滚动条样式化
   - 全站滚动条统一 thin + 主题色
   - VirtualList、DockPanel content、Menu 默认带一致样式
   - 允许宿主在外部覆盖
4. CSS 契约测试 —— 通过单元测试固化"不可违反的铁律"
   - 铁律 A：所有规则必须包在 `@layer` 里
   - 铁律 B：禁用 `!important`
   - 铁律 C：`--mutgui-*` token 定义只在 `mutgui.theme` 层

## 关键参考

- `frontend/src/core/base.css` — 核心 token + `.mutgui-scrollbar` utility
- `frontend/src/plugins/theme-dark/dark.css` — 暗色主题 token 覆盖
- `frontend/src/plugins/theme-dark/index.ts` — antd ConfigProvider 主题配置
- `frontend/src/components/dock-panel.css` — DockPanel 结构和色彩 fallback
- `frontend/src/components/dock-panel.tsx` — active tab indicator 逻辑（`showIndicator` prop）
- `frontend/tests/css-contracts.test.ts` — CSS 契约测试
- `frontend/vitest.config.ts` — vitest 配置
- `demo/examples/dock.py` — Dock demo（已精简）
- `mutbot/frontend/src/index.css` — mutbot 配色和滚动条风格参考来源

## 设计方案

### 主题 Token 对齐（3 档体系）

mutbot 本身是 3 档色：`#1F1F1F`（主背景）/ `#262526`（浮层 / tabbar / menu bg）/ `#3C3C3C`（描边 / 分割线）。
mutgui 之前的 2 档偏中灰，观感偏亮。统一到 3 档后与 mutbot 一致。

| token | 值（OKLCH 精确换算） | 用途 |
|-------|-------------------|------|
| `--mutgui-bg` | `oklch(0.2393 0 0)` ≈ `#1F1F1F` | 主背景 / panel content / active tab |
| `--mutgui-surface` | `oklch(0.2659 0 0)` ≈ `#262526` | tabbar / splitter / 浮层（menu） |
| `--mutgui-border` | `oklch(0.3562 0 0)` ≈ `#3C3C3C` | 描边 / 菜单 divider |
| `--mutgui-text` | `oklch(0.85 0 0)` ≈ `#CCCCCC` | 主文字 |
| `--mutgui-text-dim` | `oklch(0.60 0 0)` ≈ `#858585` | 次文字 |
| `--mutgui-accent` | `oklch(0.55 0.17 240)` ≈ `#007ACC` | VS Code 蓝 |

**颜色写法选择**：核心色用 OKLCH 三位小数精确换算（保持 mutgui 风格一致，便于 `color-mix` 派生）。`rgba(...)` 仅用于透明色场景（滚动条 thumb）。

**antd colorPrimary** 同步从 `#4a8ef0` 改到 `#007acc`。

### DockPanel 色彩归属

核心一致性关系（跨亮/暗主题通用）：

- tabbar / merged-bar / splitter **都走 surface 色**（同色、视觉上融为一体）
- active tab 下沉到 `--mutgui-bg`，只有 tab 本身从 tabbar 底色中"切出"
- **所有边框去掉**：tabset 外框、merged-bar 底边、tabbar 与 content 的方向性分隔线

`.mutgui-dock-tabbar` / `.mutgui-dock-merged-bar` / `.mutgui-dock-splitter` 的 bg fallback 从 `var(--mutgui-border)` 改回 `var(--mutgui-surface)`（mutbot 本来就是这么用的）。

### Active Tab Indicator

之前 `TabButton` 无论 active 还是拖拽，都通过 2px `border*` 模拟 indicator。现在拆成两用：

- active 态：**不画 indicator**，只靠 `--mutgui-bg` 底色区分
- 拖拽命中（`dragOverIdx === i`）：画蓝色 indicator 指示 drop 位置

新增 `showIndicator` prop（默认 false），只在拖拽命中时传 true。

### 滚动条方案（纯标准 API）

mutbot 用"标准 API + webkit fallback"两套并存。Chrome 121+ 有个关键规则：**同一元素设了 `scrollbar-color` 后，同元素的 `::-webkit-scrollbar` 规则被禁用**；且 `scrollbar-color` 可继承，会传染到后代元素禁用它们的 webkit 规则。

两套并存在 mutbot 里不出问题，是因为 mutbot 只在具体容器（`.message-list-scroller`）上挂规则，不在 `:root` 全局挂。mutgui 想做全局，只能**全面放弃 webkit**。

最终方案：

- 全站只用 `scrollbar-width: thin` + `scrollbar-color: var(--mutgui-scrollbar-thumb) transparent`
- 删除所有 `::-webkit-scrollbar-*` 规则
- `--mutgui-scrollbar-thumb`：亮主题 `rgba(100, 100, 100, 0.4)`、暗主题 `rgba(121, 121, 121, 0.4)`（中性灰 + alpha，不走 `color-mix` 因为 mix 在亮底/暗底方向不同）
- 不支持 thumb hover 高亮（标准 API 限制），对应 `-hover` token 移除

**代价**：`thin` 宽度由浏览器决定（Chrome Windows ≈ 10-12px），不能精确像素控制。权衡后接受（全浏览器一致比精确宽度更重要）。

#### `.mutgui-scrollbar` utility class

新增 utility class，放在 `@layer mutgui.components`：

```css
.mutgui-scrollbar {
  scrollbar-width: thin;
  scrollbar-color: var(--mutgui-scrollbar-thumb) transparent;
}
```

- mutgui 内置组件硬编码挂 class：`.mutgui-virtual-list`、`.mutgui-menu`、`.mutgui-dock-content`
- `<html>` 走 `:where(:root)` 的全局规则，视口滚动条自动主题化
- 不开 `className` prop —— 宿主要覆盖直接写 CSS（宿主未入 layer 的规则优先级天然高于 layer，不用 `!important`）

### Plugin 边界守护

`dark.css` 和当时的 `theming.py`（该 demo 后续已移除）的 body 规则块原本有 `min-height: 100vh` 和 `margin: 0`。这两项属于**业务视觉决定**（想让背景撑满视口 / 清零浏览器默认 margin），不应进 plugin。

依赖 CSS"body 背景传播"规则（body 的 background 自动传到视口），`min-height: 100vh` 对"紫色/黑色铺满视口"本来就没有必要。删掉这两行后紫色和暗底依然铺满视口，且不再触发多余的 html 滚动条。

保守清理：只删 `min-height` 和 `margin`，保留 `background` 和 `color`（plugin 还提供"一键变暗底"的便利）。

### CSS 契约测试（核心护栏）

**动机**：本次 dark theme 迭代中，AI 多次将规则跳出 `@layer` 以"提优先级"（2026-04-22 事故：VirtualList 滚动条宽度问题，误判为 antd 覆盖，实际是 Chrome 继承 scrollbar-color 禁用 webkit 规则）。文档约定不够硬，需要**机器可验证的护栏**。

**技术栈**：vitest + postcss（postcss 是 vite 的传递依赖，vitest 新增）。

**测试文件**：`frontend/tests/css-contracts.test.ts`

**测试目录**：扫描 6 个 mutgui 自有 CSS 文件（不含 `index.css`，它只有 `@layer` 声明和 `@import`）：
- `core/base.css`
- `components/menu.css` / `dock-panel.css` / `virtual-list.css`
- `plugins/theme-dark/dark.css`

**三条铁律的注释结构**（每个 describe 顶部）：
1. 契约本身（What）
2. 理由（Why）— 违反的具体危害
3. 历史违规事件（如有）— 本次 A 的注释里写了 2026-04-22 事故
4. 修改前提（When to change）— 明确需用户授权

**集成到构建**：`build:standalone` 前先跑 `vitest run`，失败直接中断，违反铁律的代码出不了包：

```json
"build:standalone": "vitest run && vite build --config vite.standalone.ts && vite build --config vite.antd.ts && vite build --config vite.theme-dark.ts"
```

**首次运行的收益**：测试抓到 `dark.css` 历史上所有规则都裸在文件顶层（从未按铁律归到 @layer），已顺手修复，把整个 body 规则块包进 `@layer mutgui.theme`。

### Demo 精简

`dock.py`：
- 去掉顶部 `.header` 说明文字（完全交给 DockPanel 占满视口）
- 去掉 11 个面板的彩色背景 dict，统一走 panel content 的 `--mutgui-bg`
- `<body>` 不设 class（html 有全局 scrollbar 规则即可）

历史上的 `theming.py`：
- 删除 MyPurpleTheme plugin 里的 `min-height: 100vh` 和 `margin: 0`

## 实施步骤清单

- [x] theme-dark token 3 档体系（bg/surface/border 精确 OKLCH 换算 mutbot 颜色）
- [x] antd colorPrimary 改 `#007acc`
- [x] DockPanel 色彩归属：tabbar/merged-bar/splitter 走 surface；三处边框去掉
- [x] TabButton 新增 `showIndicator` prop，active 态不画 indicator
- [x] dock demo 精简（去 header / 去彩色 bg / body 不带 class）
- [x] 滚动条方案全面切到标准 API：删 webkit 规则，新增 `.mutgui-scrollbar` utility class
- [x] `--mutgui-scrollbar-thumb` token（亮/暗主题各自设值），删除 `-hover` token
- [x] 三个组件硬编码挂 `mutgui-scrollbar` class：VirtualList / Menu / DockPanel content
- [x] dark plugin 清理 body 规则中的业务决定（`min-height` / `margin`）
- [x] 当时的 theming demo plugin 同样清理（该 demo 已在后续版本移除）
- [x] 安装 vitest，写 `tests/css-contracts.test.ts`（铁律 A/B/C）
- [x] `vitest.config.ts` 配置
- [x] `package.json` 加 `test` 脚本；`build:standalone` 前置 `vitest run`
- [x] 修复测试抓出的 `dark.css` 历史违规（body 规则块包进 `@layer mutgui.theme`）

## 测试验证

- ✅ 15 个 CSS 契约测试全部通过
- ✅ `npm run build:standalone` 构建成功（含测试前置）
- ✅ 浏览器实测（Chrome 147）：
  - Dock / VirtualList / Menu / 各 demo 视觉与 mutbot 一致
  - 滚动条全站 thin + 主题色，宿主可通过普通 CSS 覆盖
  - 暗色主题下 color-scheme 传到 html，系统滚动条、表单控件跟着变暗

## 遗留问题

- `thin` 实际宽度由浏览器决定（Chrome Windows ≈ 10-12px），不能精确到 8px。接受此代价。
- 标准 API 不支持 thumb `:hover` 高亮。需要时可参考 mutbot 在特定容器上组合 `:hover` + `transition: scrollbar-color` 的做法（Firefox 有动画、Chrome 瞬时切换）。
- VirtualList 最初观察到的"滚动条特别宽"根因：`:where(:root)` 上 `scrollbar-color` 继承到后代禁用 webkit + `scrollbar-width: thin` 不继承。全面切到标准 API 后彻底消除。

## 复盘要点

- **护栏优于文档**：本次 AI 多次把规则跳出 `@layer` 以"提优先级"，事后验证根因完全不是优先级问题。纯文档/memory 约束无法阻止这类"反应式违规"，只有机器可验证的单元测试能做到。
- **OKLCH 换算需要精确**：`#1F1F1F` 写成 `oklch(0.20 0 0)` 看起来差不多，实测观感偏差明显。用脚本精确换算到 `oklch(0.2393 0 0)`。
- **3 档色 vs 2 档色**：mutbot 的 3 档结构（bg / surface / border）有明确分工，mutgui 之前的 2 档挤压容易产生歧义（tabbar 到底走哪个？splitter 到底走哪个？）。回归 3 档后所有组件的色彩归属都清晰。
- **Plugin 边界**：Plugin 该管 token 和 color-scheme，不该管 `min-height: 100vh` / `margin: 0` 这种业务视觉选择。`background` 传播规则让后者大多数时候是多余的补丁。
