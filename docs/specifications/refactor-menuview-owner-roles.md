# MenuView.owner 字段双角色清理

**状态**：✅ 已完成
**日期**：2026-05-15
**类型**：重构

## 需求

1. `MenuView.owner` 字段当前同时承担两个独立角色，语义混乱：
   - **Lifecycle owner**：menu 挂在哪个 view 的 `overlay_children`、关闭时谁 invalidate（`_menu_impl` 使用）
   - **业务 owner**：传递给 `ActionContext.owner`，供 `Action.execute(ctx)` 识别"在哪个业务 view 上发起"
2. `_menu_impl.menu_trigger_handle` 末尾 `menu_view.owner = view` **强制覆盖**调用侧传入的 owner，导致：
   - `ActionMenu(owner=self.owner, ...)` 的传参实际会丢失
   - 多级菜单中 `ctx.owner` 变成父级 ActionMenu，而非最初的业务 view
3. `ActionContext.owner` 字段当前**没有任何消费者**——demo 中 actions 全部走 `ctx.data['dock_panel']` 等显式 key，所以双角色冲突没造成可见 bug，但属于潜在地雷

## 关键参考

- `src/mutgui/menu.py:44` — `MenuView.owner: View | None = None` 字段定义
- `src/mutgui/_menu_impl.py:38-43` — `menu_close` 用 `self.owner` 做 lifecycle（移除 overlay + invalidate）
- `src/mutgui/_menu_impl.py:70` — `menu_view.owner = view` 强制覆盖调用侧传入的 owner
- `src/mutgui/action.py:569` — `ActionMenu._base_context()`：`ActionContext(owner=self.owner, ...)` 把 lifecycle owner 当业务 owner 传出
- `src/mutgui/action.py:545` — 渲染期 `ActionMenu(owner=self.owner, ...)` 实际无效（被 trigger 覆盖）
- 关联 spec：`feature-action-event-handler.md`（已记录"调用侧不再传 `owner=`"作为 workaround）

## 当前 workaround

`feature-action-event-handler.md` 重构时调用侧不再传 `owner=`，避开"传了被覆盖"的困惑：

```python
# 之前
MenuTrigger(lambda: ActionMenu(owner=self.owner, source_action=..., context=...))

# 之后（workaround）
MenuTrigger(ActionMenu, source_action=..., context=context, ...)
# owner 由 _menu_impl 自动赋值为 trigger view（lifecycle 角色）
```

业务 owner 通过 `ActionContext.owner` 单独传递（虽然目前没人读）。

## 候选方向（待设计阶段确定）

- **方向 1**：分离字段。`MenuView` 内部 lifecycle 用私有字段（如 `_host_view`），公开 `owner` 留给业务（或干脆删除，业务全部走 `ActionContext.owner`）
- **方向 2**：lifecycle owner 不覆盖。`menu_trigger_handle` 改成 `if menu_view.owner is None: menu_view.owner = view`，调用侧传的优先；但业务 owner ≠ 挂载点时 `menu_close` 的 invalidate 目标会错位
- **方向 3**：明确 `MenuView.owner` 仅为 lifecycle 字段，删掉 `ActionContext.owner` 字段（既然没消费者），业务侧需要 view 引用时强制走 `ctx.data`

## 影响面

- `MenuView` 公开接口变更（任何外部 menu 用例都受影响）
- `ActionMenu` 接口
- `ActionContext` 字段定义
- 现有 demo / 测试需要回归

## 设计方案

### 决策一：用 `mutobj.Extension` 承载 lifecycle host（不用私有字段）

mutgui 既有架构已经用 Extension 管理运行时私有状态（`ViewObservers`、`ViewRenderState`、`ViewPortRuntime`），lifecycle host 完美匹配同一模式。相比私有字段 `_host`：

- `MenuView` Declaration 表面完全干净（只剩 `id` + `close()`）
- 状态归属到 `_menu_impl.py`（实现侧），与“声明-实现分离”原则一致
- 不参与 wire 序列化（不是 Field，零序列化风险）
- 与 mutgui 现有 Extension 模式同构

### 决策二：彻底删除双角色，不保留 deprecated 别名

下游盘点：

- `mutgui` 自身：`MenuView.owner` 仅 `_menu_impl` 写入、`menu_close` 读取（lifecycle 双方）；`ActionContext.owner` 仅 `ActionMenu._base_context` / `ActionToolbar._base_context` 写入，**全仓零读取者**
- `mutagent` webui：4 处 `ActionContext(owner=self, ...)`，业务读 `ctx.data["chat_input"]` / `ctx.data["conversation"]`，**owner 零读取**
- `mutbot`：完全不使用 mutgui 菜单/Action 系统

双角色字段全是“只写不读”的死分支，直接砍，不保留别名（mutgui 还在快速迭代，无历史包袱）。

### 决策三：`MenuView.owner` 字段直接删除（不重命名）

下游零使用，没有重命名为 `_host` 的必要——lifecycle host 已经移到 `MenuRuntime` Extension 里，`MenuView` 类上不再需要这个字段。

### 落地方案

```python
# _menu_impl.py 新增
class MenuRuntime(mutobj.Extension[MenuView]):
    """MenuView 框架运行时状态 — 仅 _menu_impl 维护。"""
    host: View | None = None  # 菜单挂载点（overlay_children 容器 + invalidate 目标）
```

- `menu_close`：从 `MenuRuntime.get(self).host` 取挂载点，读 + 清理
- `menu_trigger_handle`：`MenuRuntime.get_or_create(menu_view).host = view`，不再赋值 `menu_view.owner`
- `MenuView.owner` 字段从声明删除
- `ActionContext.owner` 字段 + `with_updates(owner=...)` 形参从 dataclass 删除
- `ActionMenu` / `ActionToolbar` 中所有 `owner=self.owner` / `owner=self` / `ActionContext(owner=...)` 删除
- `dock_panel.py`、demo、mutagent webui 的所有 `ActionContext(owner=self, ...)` 删除 owner 形参

## 关键参考（实施补充）

- `src/mutgui/_view_impl.py:35-49` — 现有 Extension 用法范本（`ViewObservers`、`ViewRenderState`）
- `src/mutgui/_viewport_impl.py:25` — `ViewPortRuntime` Extension
- `mutobj/src/mutobj/core.py:1088-1170` — `Extension` 基类、`get_or_create` / `get` 语义
- 下游影响（mutagent）：
  - `mutagent/src/mutagent/webui/_chat_input_impl.py:33, 82` — `ActionContext(owner=self, ...)` × 2
  - `mutagent/src/mutagent/webui/_conversation_impl.py:120, 155` — 同上 × 2

## 实施步骤清单

- [x] `src/mutgui/menu.py` — 删除 `MenuView.owner` 字段定义
- [x] `src/mutgui/_menu_impl.py` — 新增 `MenuRuntime(Extension[MenuView])`，重写 `menu_close` / `menu_trigger_handle` 使用 Extension 而非 `self.owner` / `menu_view.owner`
- [x] `src/mutgui/action.py` — 删除 `ActionContext.owner` 字段、`with_updates(owner=...)` 形参；删除 `ActionMenu` / `ActionToolbar` 中所有 owner 引用，`_base_context` 不再 fallback 到 `self.owner`
- [x] `src/mutgui/dock_panel.py` — 删除 `ActionContext(owner=self, ...)` 实参
- [x] `mutgui/demo/examples/action.py` — 删除 `ActionContext(owner=self, ...)` 实参
- [x] `mutagent/src/mutagent/webui/_chat_input_impl.py` — 删除 2 处 `owner=self,`
- [x] `mutagent/src/mutagent/webui/_conversation_impl.py` — 删除 2 处 `owner=self,`
- [x] 跑 `pytest` 回归 mutgui 测试（重点 `tests/test_menu.py` / `tests/test_action.py`）— 243 passed
- [x] 跑 `pytest` 回归 mutagent 测试 — 1004 passed, 4 skipped
