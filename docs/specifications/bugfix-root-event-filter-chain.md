# 根级事件绕过 EventFilter 链

**状态**：✅ 已完成
**日期**：2026-05-15
**类型**：Bug 修复

## 需求

`_route_event` 在 `len(source) == 0` 分支（路由到 root View 的事件）直接调 `view.on_event(event)`，跳过了 `ext.event_filters` 链。这与「filter 通过率 = 是否到达 on_event」的语义文档不符——根级事件理应同样可被 EventFilter 拦截或观察。

不修复的实际后果：

- 任何想以 EventFilter 形式做横切关注（埋点、节流、权限校验、日志）的中间件，在根级事件上失效。
- 即将落地的 `feature-system-events-and-hash-nav.md` 承诺「根 View 上的 EventFilter 能拦截 `$hashchange`」，依赖该分支补 filter 链才能成立。
- 行为不一致难以排查：同一段 EventFilter 代码在子组件事件上能拦，在根事件上不能拦，且没有明显报错。

本 bugfix 与 hash 导航功能解耦——独立 PR、独立 commit、独立测试，方便回滚。

## 关键参考

- `src/mutgui/_view_impl.py` `_route_event` — 当前实现，`len(source) == 1` 分支已跑 filter 链，`len(source) == 0` 直接 `await view.on_event(event)`
- `src/mutgui/events.py` — `Event` / `EventFilter` / `EventHandler` 定义
- `src/mutgui/_view_impl.py` `view_on_event` — 根 View 默认 `on_event` 实现（按 `(component_id, event_name)` 查 handler）
- `feature-system-events-and-hash-nav.md` — 主消费者，依赖本 bugfix 让根 View 的 `$hashchange` 可被 EventFilter 拦截

## 设计方案

### 修复点

`_route_event` 的 `len(source) == 0` 分支补上与 `len(source) == 1` 分支同形的 filter 循环：

```python
else:  # len(source) == 0
    event = Event("", event_name, data, viewport_id=viewport_id)
    for f in ext.event_filters:
        if await f.on_event_filter(view, event):
            return
    await view.on_event(event)
```

两个分支的 filter 调用语义完全对齐：

- 同一个 `ext.event_filters` 列表
- 同一个 `on_event_filter(view, event)` 签名
- 同一个「返回 True 即拦截、阻止后续 filter 与 on_event」的短路语义

### 合成事件路径同样适用

`feature-system-events-and-hash-nav.md` 中后端在 `viewport.initialize()` 内合成 `$hashchange (cause=initial)` 时，必须走相同的 `_route_event` 路径（而不是直接 `await view.on_event(event)`），否则首屏入口事件会绕过 filter，与运行期 hashchange 行为不一致。

本 bugfix 文档不直接修改合成路径，但要求合成路径调用 `_route_event`，由本修复保证 filter 一致性。

### 兼容性

- 新行为：根级事件**会**经过 EventFilter 链。
- 既有 EventFilter 实现没有针对"根级事件不会到达"的隐式假设——`on_event_filter` 收到 `event.component_id == ""` 是合法输入，filter 实现要么基于 `event.name` 判断，要么基于 `component_id` 判断，没有路径会因为新增「根级事件穿过 filter」而崩。
- 既有应用没有 EventFilter 实例时（`ext.event_filters == []`），for 循环空过，行为与现状完全等价。

不需要 feature flag，直接合入。

## 待定问题

无。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| `feature-system-events-and-hash-nav.md` | 根 View 上 EventFilter 拦截 `$hashchange` | 根分支 filter 链生效 | 在根 View 注册一个总是返回 True 的 EventFilter，`$hashchange` 不再触达 `on_event` |
| 通用 EventFilter 中间件 | 埋点 / 节流 / 权限 / 日志类 filter 在根级事件同样工作 | 根分支 filter 链生效 | 同一个 EventFilter 实例对子组件事件和根级事件行为一致 |

## 实施步骤清单

- [x] 修改 `src/mutgui/_view_impl.py` 的 `_route_event` 函数，在 `len(source) == 0` 分支补 EventFilter 链循环
- [x] 在 `tests/test_view_event_routing.py`（或对应测试文件）新增三个用例：
  - [x] 根级事件经过 EventFilter（filter 返回 False，`on_event` 被调用）
  - [x] 根级事件被 EventFilter 拦截（filter 返回 True，`on_event` 不被调用）
  - [x] 多个 EventFilter 串联，第一个返回 True 后第二个不被调用（短路语义）
- [x] 运行 `pytest tests/test_view_event_routing.py` 确认绿
- [x] 运行全量 `pytest` 确认无回归
