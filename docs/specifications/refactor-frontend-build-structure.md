# mutgui 前端构建结构收敛 设计规范

**状态**：✅ 已完成
**日期**：2026-04-29
**类型**：重构

## 需求

1. `mutgui/frontend/` 当前把 vendor、runtime lib、boot 分散到多份 `vite.*.ts` / `vendor-build/*.config.ts` / `vendor-build/entries/*` 文件中，目标少但文件跳转多，阅读成本偏高。
2. 构建结构需要继续支持 **下游复用**：`mutagent` 等依赖 mutgui 的项目应能复用同一套 build 规则，而不是复制整套 Vite 配置。
3. vendor 仍需保留 **增量构建**：像 `antd` 这种构建成本较高的第三方库，不应在每次 `npm run build` 时都无条件重打。
4. 产物协议不能变化：现有 `ModuleRegistry`、runtime manifest、`boot.js`、`@mutgui/core` / `@mutgui/antd` / `@mutgui/theme-dark` 的运行时行为必须保持兼容。

## 关键参考

- `mutgui/frontend/build.mjs` — 当前总构建入口
- `mutgui/frontend/build-preset.mjs` — 共享 build preset，供 mutgui 与下游复用
- `mutgui/frontend/mutgui.build.mjs` — mutgui 当前项目的 target 声明
- `mutgui/frontend/vendor/` — 当前 vendor 入口源码
- `mutgui/src/mutgui/modules.py` — runtime manifest 聚合与 `?v=<mtime_ns>` cache busting
- `mutagent/src/mutagent/webui/_server_impl.py` — 下游当前仍依赖旧 IIFE 静态资源加载
- `mutagent/docs/specifications/feature-frontend-component-package.md` — 下游组件包的既有讨论背景

## 设计方案

### 总体思路

把 mutgui 前端构建收敛成三层：

1. **项目声明文件**：描述当前项目有哪些 vendor / runtime / boot target
2. **共享 build-preset**：封装所有通用规则，供 mutgui 与下游项目复用
3. **单一执行入口**：`build.mjs` 读取项目声明并统一构建、写 manifest、清理旧产物

目标不是把所有源码都塞进一个文件，而是让“声明、规则、执行”三个层次各只保留一个入口。

### 目录结构

```text
mutgui/frontend/
  build.mjs
  build-preset.mjs
  mutgui.build.mjs
  vendor/
    react.ts
    react-dom-client.ts
    react-jsx-runtime.ts
    antd.ts
  src/
    boot.ts
    core.tsx
    integrations/antd.ts
    plugins/theme-dark/index.ts
```

调整点：

- 删除 `vendor-build/entries/` 这一层，vendor 入口直接平铺到 `vendor/`
- 删除 `vite.runtime.*.ts` / `vite.boot.ts` / `vendor-build/*.config.ts`
- 保留 `build-preset`，但收敛为单文件 `build-preset.mjs`
- 新增 `mutgui.build.mjs` 作为当前项目唯一的 target 声明文件

### 共享 build-preset

`build-preset.mjs` 负责三类能力：

1. **声明协议**
   - `defineFrontendProject(spec)`
   - `vendorTarget(spec)`
   - `runtimeTarget(spec)`
   - `bootTarget(spec)`

2. **构建执行**
   - 基于 Vite JS API 而不是 `vite --config xxx`
   - 由 `buildProject(projectDir, projectSpec)` 统一执行 vendor / runtime / boot

3. **manifest 生成**
   - 根据 vendor/runtime target 自动输出 `static/manifest.json`
   - 保持现有 `exports` / `css` / `entries` 格式不变

`build-preset.mjs` 需要通过 `@mutgui/core/build-preset` 暴露给下游项目，保证 `mutagent` 只写自己的项目声明文件，不复制规则实现。

### 项目声明文件

`mutgui.build.mjs` 只描述 **当前项目的 target 列表**，不包含具体 Vite 规则：

- vendor targets
  - `react`
  - `react-dom/client`
  - `react/jsx-runtime`
  - `antd`
- runtime targets
  - `@mutgui/core`
  - `@mutgui/antd`
  - `@mutgui/theme-dark`
- boot target
  - `boot.js`

其中：

- vendor target 声明需要包含 `packageName` / `entry` / `outFile(versionMap)` / `peers`
- runtime target 声明需要包含 `importName` / `entry` / `outFile` / `peers` / `cssFile?` / `kind?`

### vendor 增量策略

保留现有“**版本号文件名 + stale 检测**”的思路，不回退到每次全量重打 vendor：

1. vendor 产物仍输出到 `static/vendor/`
2. 文件名继续带版本号，如 `react-19.2.5.js`
3. `build.mjs` 仍根据：
   - `package-lock.json`
   - vendor 源码入口
   - 共享 `build-preset.mjs`
   的时间戳判断是否需要重建
4. runtime lib 与 boot 继续每次重建（目标少、速度快）

这样既保留“单一 build 入口”，也不丢掉 vendor 增量收益。

### 产物目录

运行时产物继续保持：

```text
src/mutgui/static/
  manifest.json
  boot.js
  vendor/
    react-<version>.js
    react-dom-client-<version>.js
    react-jsx-runtime-<version>.js
    antd-<version>.js
  libs/
    mutgui-core.js
    mutgui-core.css
    mutgui-antd.js
    mutgui-theme-dark.js
```

这里保留 `vendor/` 和 `libs/` 不是为了文件类型区分，而是为了表达 **生命周期差异**：

- `vendor/`：第三方、慢构建、版本化、可跳过
- `libs/`：项目源码、快构建、稳定文件名

### 下游复用约束

下游项目（本轮以 `mutagent` 验证）应只需要提供：

```text
mutagent/frontend/
  build.mjs
  mutagent.build.mjs
  src/...
```

其中：

- `mutagent.build.mjs` 通过 `@mutgui/core/build-preset` 声明自己的 runtime targets
- `build.mjs` 复用同一套 preset 执行构建
- 如果下游没有 vendor targets，则声明里可以为空数组

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 本轮验收 |
|---|---|---|---|
| mutgui 自身 | `python -m demo` 正常加载 runtime manifest / boot / vendor / libs | 单一 `build.mjs` + `mutgui.build.mjs` + `build-preset.mjs` | ✅ 必须 |
| mutagent | 复用 mutgui build-preset，生成自己的 runtime lib 并接入 WebUI | `@mutgui/core/build-preset` + `ModuleRegistry` 聚合 | ✅ 必须 |
| 未来扩展包 | 只写项目声明文件与源码入口，不复制 Vite 规则 | build-preset 子路径导出 | ✅ 需保留 |

## 实施步骤清单

- [x] 把 mutgui frontend 构建结构收敛为 `build.mjs` + `build-preset.mjs` + `mutgui.build.mjs`
- [x] 平铺 vendor 源码目录，删除 `vendor-build/entries` 与分散的 `*.config.ts` / `vite.runtime.*.ts`
- [x] 保持现有 vendor 增量构建与 runtime manifest 行为不变
- [x] 通过 package exports 暴露 `@mutgui/core/build-preset`
- [x] 用 mutagent 作为下游项目验证构建复用链路

## 测试验证

- `npm --prefix frontend run build`
- `npm --prefix frontend run test`
- `python -m demo` 后，`http://127.0.0.1:8080/basic/?fresh=post-refactor` 正常渲染 `Basic Demo`
- 下游 `mutagent/frontend` 已通过 `@mutgui/core/build-preset` 成功构建自己的 runtime manifest 与 `@mutagent/ui`

