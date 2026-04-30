# 前端源码目录重构 设计规范

**状态**：✅ 已完成
**日期**：2026-04-22
**类型**：重构

## 需求

`mutgui/frontend/src/` 当前是扁平的文件布局，所有文件按"类型"堆在同一层：

```
src/
  antd.ts             # library 用的 antd 精选注册（registerAntd()）
  context.tsx         # React Context / Provider / hooks
  dock-panel.tsx      # 内置组件
  index.ts            # library 构建入口
  menu.tsx            # 内置组件
  registry.ts         # 组件注册表
  renderer.tsx        # 核心渲染器
  resolve-path.ts     # 路径工具
  standalone.tsx      # standalone 构建入口
  virtual-list.tsx    # 内置组件
  libs/
    antd.ts           # standalone 全量 antd IIFE 入口
  styles/
    index.css
    base.css
    menu.css
    dock-panel.css
    virtual-list.css
  vite-env.d.ts
```

### 问题

1. **框架核心与组件混在一起**：`renderer.tsx` / `registry.ts` / `context.tsx` / `resolve-path.ts` 是框架基础设施，`menu.tsx` / `dock-panel.tsx` / `virtual-list.tsx` 是内置组件，目前没有结构上的区分。组件数量增加后会更乱。
2. **组件资源按类型切开**：`.tsx` 和对应 `.css` 被分到 `src/` 和 `src/styles/` 两个目录。修改 menu 要在两个位置间跳转。组件数量多时更不方便。
3. **`antd.ts` / `libs/antd.ts` 命名混淆**：两者实际是不同用途（library 精选 vs standalone 全量），但同名容易误解为重复。应该和"内置组件"区分开，归入"外部库适配"类。

### 目标

- 框架核心 vs 内置组件 vs 外部库适配 三者目录分离
- 每个内置组件**就近**放自己的 `.tsx` + `.css`（以及未来可能的 hooks / 辅助文件）
- `antd` 两个入口文件清晰标识用途，并集中在"外部库适配"目录
- 重构不改变 public API（`src/index.ts` 的导出保持不变），消费者零感知

### 非目标

- 不引入新抽象、新 barrel file
- 不拆分现有单文件组件（menu.tsx 仍然是一个文件，内部不拆成多个）
- 不修改构建配置之外的代码逻辑（仅路径变化）

## 关键参考

- `frontend/src/index.ts` — library 构建入口，本次重构后要保持导出签名
- `frontend/src/standalone.tsx` — standalone 构建入口，含 CSS `?inline` 注入
- `frontend/vite.config.ts` / `vite.standalone.ts` / `vite.antd.ts` — 三份构建配置，可能需要更新 entry 路径
- `frontend/src/styles/index.css` — 当前 `@import` 各组件 CSS，重构后路径需更新
- `frontend/src/antd.ts` 与 `frontend/src/libs/antd.ts` 的差异说明（见本文"非目标"上方的说明）

## 倾向方向（供设计阶段参考，未拍板）

初步设想的目录形态：

```
src/
  core/                 # 框架基础设施（无具体业务）
    context.tsx
    registry.ts
    renderer.tsx
    resolve-path.ts
  components/           # 内置组件，每个组件一个目录
    menu/
      menu.tsx
      menu.css
    dock-panel/
      dock-panel.tsx
      dock-panel.css
    virtual-list/
      virtual-list.tsx
      virtual-list.css
  integrations/         # 外部库适配（替代 libs/）
    antd/
      register.ts       # 原 src/antd.ts，精选 antd → library 消费者
      standalone.ts     # 原 src/libs/antd.ts，全量 antd IIFE 入口
  styles/
    index.css           # @layer 声明 + @import 各组件 CSS（路径相对改变）
    base.css            # 核心 token + 最小重置
  index.ts              # library 构建入口，保持不变
  standalone.tsx        # standalone 构建入口，CSS 注入路径更新
  vite-env.d.ts
```

设计阶段需要讨论：
- `core/` 放哪些文件？`context.tsx` 导出的类型（`MutguiConnection` 等）算框架核心还是独立模块
- `components/menu/` 内是否要加 `index.ts` 做 barrel export？还是直接 `import { Menu } from './components/menu/menu'`
- `styles/` 是否整体并入 `components/*/`，还是保留独立目录（`index.css` 入口仍需要一个中心位置）
- `integrations/antd/` 两个文件叫什么名字最清楚(`register.ts` + `standalone.ts`?`library.ts` + `iife.ts`?）

## 风险

- 三份 vite config 的 entry 路径要同步更新，漏改会构建失败
- tsx 内相对 import 路径要全部更新（`./menu` → `./components/menu/menu`）
- `demo/examples/*.py` 如果在 HTML 中引用了构建产物路径，需要确认路径不变（产物文件名保持 `mutgui.js` / `antd.js` / `styles.css`）

## 设计方案

### 目录结构（定稿）

```
src/
  core/
    renderer.tsx       # 渲染引擎
    registry.ts        # 组件解析（registerComponents / resolve）
    context.tsx        # 通信 + scope Provider（本次不拆，后续另设 refactor）
    resolve-path.ts    # 路径工具
    base.css           # token 声明 + 页面级默认主题 + 最小重置（详见 feature-demo-dark-theme）
  components/          # 扁平，每组件 .tsx + .css 成对
    menu.tsx
    menu.css
    dock-panel.tsx
    dock-panel.css
    virtual-list.tsx
    virtual-list.css
  integrations/        # 外部组件库适配（第一个是 antd，未来 MUI 等）
    antd.ts            # standalone IIFE 入口（原 src/libs/antd.ts，全量 import * as antd）
  index.ts             # library 构建入口（import './index.css'）
  index.css            # 总装配：@layer 声明 + @import core/base + components/*.css
  standalone.tsx       # standalone IIFE 入口（import './index.css?inline'）
  vite-env.d.ts
```

**删除**：
- `src/antd.ts`（精选注册 helper `registerAntd()`）— 全仓库无调用点，死代码
- `src/styles/`（整个目录消失）— 组件 CSS 就近，`base.css` 归 core，总装配入口变为根级 `index.css`
- `src/libs/`（整个目录消失）— 唯一文件 `antd.ts` 移到 `integrations/antd.ts`

### 关键决策

**组件扁平化**（当前每组件只 2 文件：`.tsx + .css`，YAGNI。未来组件升级需要 hooks/子组件时再改目录结构）

**`context.tsx` 本次不拆**（通信层 + scope 混合的问题留到独立 refactor。本次只搬文件，避免范围蔓延）

**删除 `styles/` 目录**（目录名"放样式的地方"会引导后续贡献者把组件 CSS 塞回来。组件 CSS 就近，`base.css` 归 core，总装配入口降级为根级单文件）

**根级 `index.css` 而非 `styles.css`**（与 `index.ts` 配对，符合"目录入口"约定；不会让读者误以为"要加样式来这里"）

**`integrations/antd.ts` 单文件，非目录**（整个 mutgui 对 antd 的集成只有一个 IIFE 入口文件。未来若 antd 集成出现多文件（如拆分精选子集），再升级为 `integrations/antd/` 目录）

**内置组件命名空间统一**（VirtualList 此前未挂 `mutgui` 命名空间是历史遗留，本次一并改为 `mutgui.VirtualList`，与 DockPanel / Menu 一致）

**Standalone 产物命名约定**（`mutgui.js` + `mutgui-<libname>.js` 家族式命名。`antd.js` → `mutgui-antd.js`，未来 `mutgui-mui.js` 等。原 `src/mutgui/static/libs/` 目录取消，产物扁平化到 `static/` 根。理由：产物真正所属者是 mutgui 而不是第三方库；命名自解释归属；DevTools 排查清晰；与源码消除 `libs/` 的决定一致）

### standalone.tsx 内置组件注册（调整后）

```ts
registerComponents({
  __name__: 'mutgui',
  DockPanel,
  'DockPanel.Split': DockPanelSplit,
  'DockPanel.TabSet': DockPanelTabSet,
  Menu,
  'Menu.Item': MenuItem,
  'Menu.Divider': MenuDivider,
  VirtualList,
});
```

(原先 `registerComponents({ VirtualList })` 裸注册的调用删除)

### public API 兼容性

`src/index.ts` 导出签名**完全不变**（re-export 源的模块路径内部调整，不影响消费者）：

```ts
export { registerComponents, resolve } from './core/registry';
export { MutguiView, renderTree } from './core/renderer';
export type { ComponentSchema } from './core/renderer';
export {
  ScopeProvider, ConnectionProvider, useScope, useConnection, arrayEquals,
} from './core/context';
export type { ViewPath, MutguiConnection, RenderCallback } from './core/context';
export { resolvePath } from './core/resolve-path';
export { VirtualList } from './components/virtual-list';
export { DockPanel, DockPanelSplit, DockPanelTabSet } from './components/dock-panel';
```

Standalone 产物全局 API（`window.MutguiApp.*`）也**不变**（`mount` / `registerComponents` / `React` / `ReactDOM` / `jsxRuntime`）。

构建产物文件名保持：`dist/index.js` / `dist/index.d.ts` / `dist/styles.css`（vite `assetFileNames` 已经把任意 `.css` 重命名为 `styles.css`，源码 `index.css` → 产物 `styles.css`，消费者路径不变）。

Standalone 产物路径**变更**：
- `static/mutgui.js` — 保留
- `static/libs/antd.js` → `static/mutgui-antd.js`（重命名 + 扁平化，`static/libs/` 目录取消）

### 与 feature-demo-dark-theme 的兼容性

`feature-demo-dark-theme` 会在 `core/base.css` 中追加 `:is(html, body).mutgui-theme { ... }` 选择器（opt-in 页面级默认主题）。本次重构需要为这个能力预留位置：

- `base.css` 落在 `core/`，不在 `styles/`（消除后）
- `core/base.css` 的 `@layer mutgui.theme` 块已经存在，dark theme 规则追加到同一层即可
- 重构先完成，dark theme 在重构后的布局上实施

### Q&A（已确认，归档至决策理由）

以下问题在讨论阶段已确认结论，记录于此以便追溯：
- `src/antd.ts` 处理 → **删除**（死代码，无调用点；library 消费者可直接 `registerComponents({ Button, Input })`）
- `integrations/` 是否保留 → **保留**（antd 是第一个集成，未来 MUI 等扩展需要这个目录）
- `context.tsx` 拆不拆 → **不拆**（本次只搬文件，避免逻辑改动）
- 组件目录 vs 扁平 → **扁平**（当前每组件 2 文件固定，YAGNI）
- `styles/` 目录保留 → **删除**（引导效应负面，组件 CSS 就近更清晰）
- CSS 入口名 → **`index.css`**（与 `index.ts` 配对，避免"加样式来这里"的误读）
- VirtualList 命名空间 → **归入 `mutgui.VirtualList`**（历史遗留，本次一并修复）

## 实施步骤清单

- [x] **删除死代码**：移除 `frontend/src/antd.ts`（`registerAntd()` 无调用点）
- [x] **建立 core/ 目录**：移动 `registry.ts` / `renderer.tsx` / `context.tsx` / `resolve-path.ts` 到 `frontend/src/core/`
- [x] **建立 components/ 目录（扁平）**：
  - [x] 移动 `menu.tsx` 和 `styles/menu.css` → `frontend/src/components/menu.tsx` + `menu.css`
  - [x] 移动 `dock-panel.tsx` 和 `styles/dock-panel.css` → `frontend/src/components/dock-panel.tsx` + `dock-panel.css`
  - [x] 移动 `virtual-list.tsx` 和 `styles/virtual-list.css` → `frontend/src/components/virtual-list.tsx` + `virtual-list.css`
- [x] **建立 integrations/ 目录**：移动 `libs/antd.ts` → `frontend/src/integrations/antd.ts`（文件内容不变）
- [x] **CSS 入口重组**：
  - [x] 移动 `styles/base.css` → `core/base.css`
  - [x] 移动 `styles/index.css` → `frontend/src/index.css`，更新内部 `@import` 路径
  - [x] 删除空的 `styles/` 和 `libs/` 目录
- [x] **修正 tsx 内部相对 import 路径**（components 中互相引用走 `./xxx`；components → core 走 `../core/xxx`；core → components 走 `../components/xxx` — `renderer.tsx` 反向依赖 `menu.tsx` 的历史耦合保留，留待后续 refactor）
- [x] **`index.ts` 入口调整**：re-export 源路径改为 `./core/*` 和 `./components/*`，CSS import 改为 `./index.css`，导出签名保持不变
- [x] **`standalone.tsx` 入口调整**：
  - [x] import 路径更新到新布局
  - [x] CSS `?inline` 改为 `./index.css?inline`
  - [x] 内置组件注册合并到单个 `mutgui` 命名空间，VirtualList 从裸注册改为 `mutgui.VirtualList`
- [x] **VirtualList 命名空间 Python 端对齐**：`src/mutgui/virtual_list.py` 的 `$component` 改为 `mutgui.VirtualList`；`tests/test_virtual_list.py` 的断言同步更新
- [x] **更新三份 vite config 的 entry 路径**：
  - [x] `vite.config.ts` → `src/index.ts`（不变）
  - [x] `vite.standalone.ts` → `src/standalone.tsx`（不变，验证即可）
  - [x] `vite.antd.ts` → entry 改 `src/integrations/antd.ts`，`fileName` 改 `mutgui-antd.js`，`outDir` 改 `src/mutgui/static/`（去掉 `libs/` 子目录）
- [x] **同步更新 HTML 模板 script 路径**（`/static/libs/antd.js` → `/static/mutgui-antd.js`）：
  - [x] `demo/framework/_routes.py::mutgui_page`
  - [x] `demo/examples/dock.py::DOCK_HTML`
  - [x] `demo/examples/menu.py::MENU_HTML`
  - [x] `demo/standalone/starlette.py` 内嵌 HTML
  - [x] `tests/integration/conftest.py` 内嵌 HTML
  - [x] `frontend/src/standalone.tsx` 文件头 doc comment
- [x] **清理旧产物**：删除 `src/mutgui/static/libs/` 目录（构建前先清，避免旧产物遗留）
- [x] **构建验证**：
  - [x] `npm run build`（library 模式）成功，`dist/index.js` + `dist/styles.css` 产物齐全（`index.d.ts` 缺失是预先存在的 tsc 配置问题，非本次引入）
  - [x] `npm run build` 成功，`src/mutgui/static/mutgui.js` 产物齐全
  - [x] `npm run build:antd` 成功，`src/mutgui/static/mutgui-antd.js` 产物齐全（新文件名 + 新路径）
- [x] **同步更新 `docs/design/framework-capabilities.md`** — 描述现状的设计文档里的产物路径
- [x] **修复 `dist/index.d.ts` 缺失**：`package.json` 的 `build` 脚本由 `tsc && vite build` 改为 `vite build && tsc --emitDeclarationOnly`。根因是两者共用 `dist/`，vite 默认 `emptyOutDir` 会清掉 tsc 产出的 .d.ts。调整顺序 + emit-only 后，`dist/` 同时得到 `index.js` / `styles.css` / `index.d.ts`（及各模块 .d.ts）
- [x] **运行验证**：用户启动 `python demo/app.py`，在浏览器验证各 demo 正常渲染（已通过）

