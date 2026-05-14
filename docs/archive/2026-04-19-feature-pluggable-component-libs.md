# 可插拔组件库 设计规范

**状态**：✅ 已完成
**日期**：2026-04-19
**类型**：功能设计

> **后续说明（2026-04-29）**：本文定义的**命名空间注册与组件解析规则仍然有效**，但底层加载方式已从 IIFE + `window.MutguiApp.*` 升级为 **ESM + import map + `boot.js`**。运行时加载协议以 [`feature-component-lib-extension.md`](feature-component-lib-extension.md) 和 [`../design/frontend-build.md`](../design/frontend-build.md) 为准。
>
> 除组件解析语义外，正文里关于 `standalone.tsx`、`vite.antd.ts`、`window.MutguiApp`、HTML `<script>` 链的描述都应视为**第一版历史记录**，不再作为当前实现依据。

## 需求

当前 mutgui 的组件系统与 Ant Design 强绑定：`antd.ts` 手动注册 20+ 个组件，standalone 包（933KB）内含完整 antd。但 mutgui 的核心协议（`$component` 字符串 → React 渲染）本身与任何前端组件库无关。

目标：
1. mutgui 核心不包含任何组件库，组件库作为独立插件加载
2. 统一的组件解析机制，支持：已加载的组件库、原生 HTML 元素、Web Components
3. 后端通过 HTML 模板控制加载哪些组件库 JS
4. demo 改为 `mutgui.js`（核心）+ `antd.js`（组件库）分离构建

## 关键参考

- `frontend/src/registry.ts` — 当前注册表实现（`Map<string, ComponentType>`）
- `frontend/src/renderer.tsx` — `MutguiComponent` 中的 `resolve()` 调用和 `UnknownComponent` 降级
- `frontend/src/antd.ts` — 当前 antd 手动注册（`registerAntd()`）
- `frontend/src/standalone.tsx` — 当前入口，调用 `registerAntd()` + 创建 WebSocket 连接 + mount
- `frontend/vite.standalone.ts` — standalone 构建配置（IIFE，无 external）
- `demo/app.py` — 当前 demo，生成 HTML 模板并通过 Starlette 服务

## 设计方案

### 核心思想：加载即注册

去掉显式注册步骤。组件库 JS 文件加载后，其模块导出表直接作为组件解析源。`resolve()` 遍历已加载的源查找组件，找不到则返回字符串让 React 当原生 HTML 元素渲染。

### 组件解析机制

**解析链**：一个有序数组，每个元素是一个 `name → Component` 的映射对象。映射可选带 `__name__` 字段标明命名空间（组件库源都必须带），不带则作为“手动覆盖”顶层源。

```typescript
// 解析规则（registry.ts 实现）
const sources: Record<string, unknown>[] = [];

function registerComponents(source: Record<string, unknown>): void {
  sources.unshift(source);  // 后加入的优先级更高
}

function resolve(name: string): ComponentType | string {
  // 带点名字（antd.Button / mutgui.Menu.Item）：只在命名空间源内查找，
  // 命中后允许按点分段逐层属性访问
  if (name.includes('.')) {
    const [ns, ...rest] = name.split('.');
    for (const src of sources) {
      if (src.__name__ === ns) {
        const hit = walk(src, rest);
        if (hit) return hit;
      }
    }
    return name;  // 未命中 → 原生元素
  }
  // 单段名字：只匹配无命名空间的源（手动覆盖），避免组件库名字劫持
  for (const src of sources) {
    if (src.__name__) continue;
    if (src[name]) return src[name];
  }
  return name;  // 兜底：React.createElement 当原生元素渲染
}
```

**关键规则**：
- **裸名字不会命中组件库**。`$component: "Button"` 永远是 `<button>`（HTML），不会被 antd 的 `Button` 劫持。引用组件库组件必须写全名：`antd.Button`、`mutgui.VirtualList`、`antd.Typography.Title`。
- 不再有 `UnknownComponent`——任何未识别的名字都尝试作为 HTML 原生元素或 Web Component 渲染。
- `registerComponents()` 是唯一 API。组件库以命名空间形式注册（`{__name__: 'antd', ...antd}`），手动覆盖以无命名空间形式注册（`{Button: MyCustomButton}`）。

### 构建拆分

**当前**：一个 standalone 构建产出 `mutgui.js`（933KB，含 React + antd + 核心）

**改为三个构建目标**：

| 构建 | 入口 | 格式 | React | 产物 | 大小（预估） |
|------|------|------|-------|------|-------------|
| core | `src/standalone.tsx` | IIFE | 打包 | `static/mutgui.js` | ~100KB |
| antd | `src/libs/antd.ts` | IIFE | external | `static/libs/antd.js` | ~800KB |
| library | `src/index.ts` | ESM | external | `dist/index.js` | ~16KB |

**core（mutgui.js）**：
- 包含 React、ReactDOM、mutgui 核心渲染器
- 暴露 `window.MutguiApp = { mount, React, ReactDOM, registerComponents }`
- 不包含任何组件库

**antd（antd.js）**：
- 包含 antd 全部导出
- React/ReactDOM 标记为 external，通过 `globals` 引用 `MutguiApp.React`
- 加载后自动调用 `MutguiApp.registerComponents(antdExports)`

**library（dist/index.js）**：
- 保持不变，ESM 格式供 npm 消费者使用

### 组件库 JS 的结构

每个组件库 JS 文件是一个 IIFE，加载后自动调用 `registerComponents()` 注册：

```typescript
// src/libs/antd.ts — antd 组件库入口
import * as antd from 'antd';

// 加载即注册
(window as any).MutguiApp.registerComponents({
  __name__: 'antd',
  ...antd,
});
```

构建配置：

```typescript
// vite.antd.ts
export default defineConfig({
  build: {
    lib: {
      entry: 'src/libs/antd.ts',
      formats: ['iife'],
      name: 'MutguiAntd',
      fileName: () => 'antd.js',
    },
    outDir: '../src/mutgui/static/libs',
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime'],
      output: {
        globals: {
          'react': 'MutguiApp.React',
          'react-dom': 'MutguiApp.ReactDOM',
          'react/jsx-runtime': 'MutguiApp.jsxRuntime',
        },
      },
    },
  },
});
```

### 后端加载控制

后端通过 HTML 模板控制加载哪些 JS：

```python
# demo/app.py — 生成 HTML
LIBS = ["antd"]  # 配置需要的组件库

def make_html(libs: list[str]) -> str:
    lib_scripts = "\n".join(
        f'<script src="/static/libs/{lib}.js"></script>' for lib in libs
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body>
  <div id="app"></div>
  <script src="/static/mutgui.js"></script>
  {lib_scripts}
  <script>MutguiApp.mount(document.getElementById('app'), ...)</script>
</body></html>"""
```

浏览器按 `<script>` 顺序执行：mutgui.js 先加载（暴露 React 和 `registerComponents()`），然后各组件库 JS 加载并调用 `registerComponents()` 注册。

### Library 模式使用方式

npm 消费者的用法基本不变，只是用 `registerComponents()` 替代 `registerAntd()`：

```typescript
import * as antd from 'antd';
import { registerComponents, MutguiView } from '@mutgui/core';

registerComponents({ __name__: 'antd', ...antd });
// 或者自定义组件
registerComponents({ MyChart, MyTable });
```

### 未来扩展路径

1. **动态 import** — 当前方案用 `<script>` 标签按顺序加载。未来可通过 WebSocket 握手消息通知前端动态加载组件库（`await import("/static/libs/antd.js")`），支持运行时按需加载。

2. **pip install 扩展包** — Python 包（如 `mutgui-antd`）包含预构建的组件库 JS，通过 `entry_points` 机制被 mutgui 自动发现，自动添加到 HTML 模板的 `<script>` 列表中。用户只需 `pip install` 即可使用新组件库。

3. **CSS 动态加载** — 与 JS 对称，组件库的 CSS 也通过 `<link>` 标签在 HTML 模板中加载。antd 5.x 使用 CSS-in-JS 不需要额外 CSS，但其他组件库可能需要。

## 已确认决策

- **子模块组件解析**（如 `Input.TextArea`）：`resolve()` 中 `.` 统一为属性路径解析——先找完整匹配，没找到再尝试 `sources[x].Input.TextArea`。兼容直接导出和属性挂载两种模式。
- **VirtualList 归属**：随 mutgui.js 核心包打包，核心初始化时 `registerComponents({ VirtualList })`，不属于任何组件库。
- **jsx-runtime**：antd 内部依赖 `react/jsx-runtime`，构建时标记为 external 并映射到 `MutguiApp.jsxRuntime`。这是标准的 rollup globals 配置，构建时验证即可。

## 实施步骤清单

- [x] 重写 `registry.ts`：用 sources 解析链替代 `Map`，实现 `registerComponents()` 和新的 `resolve()`（含属性路径解析和字符串兜底）
- [x] 更新 `renderer.tsx`：移除 `UnknownComponent`，适配 `resolve()` 返回字符串的情况
- [x] 创建 `src/libs/antd.ts`：antd 组件库入口，加载时自动调用 `MutguiApp.registerComponents()`
- [x] 更新 `standalone.tsx`：移除 `registerAntd()` 调用，暴露 `React`/`ReactDOM`/`jsxRuntime`/`registerComponents` 到 `window.MutguiApp`，内置注册 `VirtualList`
- [x] 创建 `vite.antd.ts`：antd 独立构建配置（IIFE，React external）
- [x] 更新 `vite.standalone.ts`：从 standalone 构建中移除 antd（不再 import antd）
- [x] 更新 `package.json`：添加 `build:antd` 和 `build`（新的不含 antd 版本）构建脚本
- [x] 更新 `index.ts`：导出 `registerComponents` 替代 `register`/`registerAll`/`registerAntd`
- [x] 更新 `demo/app.py`：HTML 模板添加 `antd.js` 的 script 标签，静态文件挂载 libs 目录
- [x] 构建验证：执行 `build` + `build:antd`，确认产物正确
- [x] 运行 demo 端到端验证：启动 demo，确认所有组件正常渲染和交互

