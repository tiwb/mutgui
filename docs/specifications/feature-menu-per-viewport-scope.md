# 菜单 per-viewport 作用域

**状态**：✅ 已完成
**日期**：2026-05-15
**类型**：功能设计（菜单系统语义扩展）

## 需求

1. 多 viewport（多个浏览器窗口/标签页连接同一 mutgui 实例）场景下，在 viewport A 触发菜单，viewport B 也显示菜单且位置错误（掉到屏幕中央）。
2. 跨 viewport 的菜单坐标本身没有正确语义：
   - `placement='cursor'`：A 的鼠标位置在 B 上无意义（B 的用户没动鼠标）。
   - `placement='bottom-start'` 等基于元素：A 的 `getBoundingClientRect()` 是 A 视口里的 DOM 位置，B 的同元素可能在不同位置（窗口尺寸/滚动/布局差异）。
3. 期望行为：**菜单只在触发它的 viewport 显示**；两个 viewport 各自打开同一菜单时互不干扰。

## 关键参考

- `mutgui/src/mutgui/menu.py` — MenuView + MenuTrigger 声明
- `mutgui/src/mutgui/_menu_impl.py` — MenuTrigger.handle 实现，创建菜单并注入 overlay_children
- `mutgui/src/mutgui/_view_impl.py` — View 渲染序列化、`_render_and_cache` 注入 overlay children 到 wire_tree
- `mutgui/src/mutgui/_viewport_impl.py` — `_vp_push_render` per-viewport 推送 wire_tree
- `mutgui/src/mutgui/events.py` — `Event.viewport_id`（即 channel_id，标识事件来源 viewport）
- `mutgui/frontend/src/components/menu.tsx` — Menu 组件、`createMenuTriggerHandler`、`pendingTrigger` 模块级全局
- `mutgui/frontend/src/components/menu-layout.ts` — 菜单布局计算
- `mutgui/frontend/src/core/renderer.tsx` — MutguiView + renderTree、菜单 viewId 检测与 Menu 容器包装

## 备选方案讨论

记录决策过程，避免日后绕回。

### 方案 A（已否决）：把 trigger 位置嵌入 wire tree

让所有 viewport 都看到菜单，把 `{x, y, placement, triggerRect}` 序列化进 wire 让每个 viewport 各自定位。

否决原因：**坐标跨 viewport 没有正确答案**。
- A 的鼠标坐标在 B 上没意义。
- A 的 `triggerRect` 是 A 视口下的 DOM 几何，与 B 视口的同元素几何不一致；即使按比例缩放也无法对齐。
- UX 上也违反直觉：右键菜单是光标驱动的瞬态浮层，跨窗口共享本身就是错的。

### 方案 B（采纳）：菜单只在触发 viewport 渲染

利用现有 `Event.viewport_id` 标记菜单来源，推送 wire_tree 时按 origin 过滤，非 origin viewport 看不到该菜单。

### 方案 B 的三种细化（B3 采纳）

设场景：host View 上挂菜单，A 已打开 menu_A 正交互，B 也右键触发同一菜单。

| 细化 | 关闭旧菜单逻辑 | 行为 | 评价 |
|------|--------------|------|------|
| B1 | 关闭 host 上**所有**旧菜单（保持当前实现） | B 触发会把 A 上的 menu_A 也关掉 | A 用户看到菜单凭空消失，诡异 ❌ |
| B2 | 把 `overlay_children` 拆到 ViewPort 上 | A、B 各自独立菜单链 | 干净 ✅，但破坏 mutobj "View 跨 viewport 共享" 的存储模型 |
| B3 | 关闭 host 上**同 origin 的**旧菜单 | A、B 各自独立菜单链 | 视觉等价 B2 ✅，存储模型保持不变 |

**采纳 B3**：视觉行为符合直觉、改动量最小、不破坏 View 共享存储模型。

## 设计方案

### 核心思想

菜单的 **state（MenuView 实例）** 仍挂在 host View 的 `overlay_children`（保持跨 viewport 共享存储），但 **visibility（推送给哪个 viewport 渲染）** 按 origin 隔离。每个菜单记住自己来自哪个 viewport（`origin_channel_id`），推送 wire_tree 时按 origin 过滤；关闭逻辑也按 origin 隔离。

### 数据模型

`MenuView` 新增字段：

```python
class MenuView(View):
    id: str | int = mutobj.field(default_factory=...)
    owner: View | None = None
    origin_channel_id: int | None = None   # 触发 viewport 的 channel_id
```

`origin_channel_id` 在 `MenuTrigger.handle` 中创建 menu 时赋值为 `event.viewport_id`。子菜单的 origin 与父菜单一致（子菜单的 trigger event 也来自同一个 viewport）。

### 后端流程改动

**`_menu_impl.menu_trigger_handle`**：

1. 创建 menu_view 时设置 `menu_view.origin_channel_id = event.viewport_id`。
2. 关闭旧菜单的循环改为"只关闭同 origin 的菜单"：

   ```python
   for child in list(ext.overlay_children.values()):
       if isinstance(child, MenuView) and child.origin_channel_id == event.viewport_id:
           await child.close()
   ```

3. 其余逻辑不变。

**`_viewport_impl._vp_push_render`**：

在 `wire_tree = view.render_viewport(wire_tree, channel_id)` 之后，对 wire_tree 中的 `$view` 节点按 origin 过滤：

- 若引用的是 MenuView 且 `origin_channel_id is not None and origin_channel_id != channel_id`，从 wire_tree 中剔除该节点。
- 同步从 child_viewport reconciliation 中跳过（不为该菜单创建子 ViewPort）。

为避免在 viewport 实现里 `import MenuView`（破坏分层），用 duck typing：检查 `getattr(child_view, "origin_channel_id", None)`。这是个通用属性，未来 tooltip / popover 等"光标驱动浮层"也可复用。

**`ViewPort.detach`**：

ViewPort 断开时，关闭所有 `origin_channel_id == self.channel.channel_id` 的菜单，避免菜单挂在已断开的 viewport 上变成"孤儿"。在 `_viewport_impl.viewport_detach` 中遍历 `ext.view`（host）的 overlay_children 处理。

### 前端流程

**无前端逻辑改动**。

- `pendingTrigger` 模块级全局单例保持不变——它本来就只在触发 viewport 的浏览器进程内有效，多 viewport 各自独立浏览器进程，互不影响。
- viewport B 因为不再收到该菜单的 wire_tree，前端 MutguiView 根本不会 mount Menu 组件，自然没有定位问题。
- viewport A 走原有路径：`createMenuTriggerHandler` 写 `pendingTrigger` → 后端推 wire → MutguiView 读 `takePendingMenuTrigger()` → 正确定位。

### 行为表

| 场景 | 行为 |
|------|------|
| 单 viewport，依次触发两次菜单 | 关闭旧、打开新（同 origin，与现状一致） |
| viewport A 打开菜单，A 内 ESC / 点空白 | A 关闭，B 不受影响（B 本来就没渲染） |
| viewport A 打开菜单，B 此时也右键同一菜单 | A 的菜单保持打开（不同 origin），B 打开自己的菜单 |
| viewport A 打开菜单，A 用户切换到子菜单 | 子菜单 origin = A，仍只在 A 渲染 |
| viewport A 打开菜单后断连 | A 的菜单在 detach 时被关闭并从 overlay_children 移除 |
| viewport A 打开菜单，B 的 host View 重新 invalidate | B 的推送过滤掉 menu_A，B 仍看不到 menu_A |

### mutobj 视角的合理性

- `MenuView.origin_channel_id` 是 Declaration 上的普通字段，符合 mutobj 数据/实现分离风格。
- 过滤逻辑放在 `_vp_push_render` 而非 MenuView 自身的 `render_viewport`：因为 wire_tree 中 `$view` 引用是由 host View 注入的，过滤天然属于 host→viewport 推送阶段。
- 用 duck typing（`getattr(child, "origin_channel_id", None)`）避免 `_viewport_impl` 反向依赖 `menu` 模块，保持依赖方向。

### detach 时的菜单清理

采用 fire-and-forget：detach 是 sync 方法且常发生在连接异常关闭，async 上下文不一定可用；`MenuView.close` 本质是 `overlay_children.pop` + `host.invalidate()`，没有需要 await 的 IO，可安全 `asyncio.create_task` 或直接同步调用底层清理。如未来 close 需要等待 IO 再升级 detach 为 async。

## 实施步骤清单

- [x] `menu.py`：MenuView 新增 `origin_channel_id: int | None` 字段
- [x] `_menu_impl.py`：`menu_trigger_handle` 创建菜单时赋值 origin；关闭旧菜单循环只关闭同 origin 的 MenuView
- [x] `_viewport_impl.py`：`_vp_push_render` 推送前按 origin 过滤 overlay `$view` 节点（duck typing：`getattr(child, "origin_channel_id", None)`）
- [x] `_viewport_impl.py`：`viewport_detach` 关闭挂在 host 上、origin == 本 channel_id 的菜单（fire-and-forget，复用 `menu.close` 的同步底层）
- [x] 补充多 viewport 场景的测试用例（B 不渲染 A 的菜单、A/B 各自菜单互不干扰、detach 清理孤儿菜单）
- [x] 跑全量 `pytest` 验证回归
