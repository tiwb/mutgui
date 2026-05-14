# mutgui theming demo — 后端控制 none/dark 切换

**状态**：✅ 已完成
**日期**：2026-04-29
**类型**：功能设计

## 需求

1. 既然自定义紫色主题已移除，`no_theme` 更适合升级为真正的 `theming` demo。
2. demo 需要展示“主题由后端控制”的事实，而不是前端自行决定是否安装 theme-dark。
3. 当前协议只有 `runtime.install`，没有扩展卸载；因此切换主题时应通过 reload 触发新连接重新装配。

## 关键参考

- `demo/framework/_routes.py` — `MutguiRoute.runtime_messages()`，运行时装配消息入口
- `demo/examples/no_theme.py` — 本轮改造前的零主题 demo
- `frontend/src/plugins/theme-dark/index.ts` — 唯一保留的主题扩展
- `frontend/src/core.tsx` — 内置 `mutgui.reload()` 命令
- `tests/test_command_channel.py` — command wire message 测试风格参考

## 设计方案

### 范围

本轮只实现**单个 demo 内的后端控制切换**：

- 文件名改为 `demo/examples/theming.py`
- gallery 路径变为 `/theming/`
- 只支持两种模式：
  - `none`
  - `dark`

不实现“整个 demo 站全局共用一个主题状态”。那种方案需要把状态提升到 gallery server 或 cookie/query 参数层，本轮不展开。

### 后端控制方式

- View 保存当前 `theme_mode`
- 用户点击“切到无主题”/“切到黑色主题”按钮时：
  - 后端更新 `theme_mode`
  - 后端发送 `mutgui.reload()`
- 浏览器 reload 后重连 websocket
- route 在新的 `runtime_messages()` 中读取当前 `theme_mode`
  - `none` → 不下发主题扩展
  - `dark` → 下发 `@mutgui/theme-dark`

这样主题切换完全由后端决定，且符合当前“安装但不卸载”的 plugin 模型。

### 页面展示

页面展示两类状态：

- 当前主题模式（由后端状态决定）
- 当前 websocket `channel_id`（reload 后会变化，便于验证确实发生了重连）

`theme_mode` 与 `channel_id` 通过 `render_viewport()` 动态写入文案，不依赖重新 render 缓存树。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| mutgui demo 使用者 | 理解主题是否由后端控制 | none/dark 两按钮 + reload 重连反馈 | 点击按钮后页面 reload，且新连接按后端状态装配正确主题 |
| mutgui 下游应用 | 参考“当前协议下如何切换主题” | 后端状态 + `runtime.install` + `mutgui.reload()` | 可复用同一模式实现应用级主题切换 |

## 实施步骤清单

- [x] 将 `no_theme.py` 改为 `theming.py`，并把 demo 语义改为 none/dark 切换
- [x] 让 route 按后端状态动态决定是否安装 `@mutgui/theme-dark`
- [x] 补测试并完成构建验证

## 测试验证

- `npm --prefix frontend run build`
- `python -m pytest tests/test_command_channel.py tests/test_menu.py tests/test_dock_panel.py tests/test_theming_demo.py`
