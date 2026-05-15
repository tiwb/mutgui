# Callback API 范例与文档改进

**状态**：✅ 已完成
**日期**：2026-05-15
**类型**：重构（文档 + 范例改进）

## 需求

`Callback` 的 API 表面上和 `functools.partial` 同构——positional args 按顺序映射到 handler 参数。但在实际使用中，开发者在 mutagent `_settings_page_impl.py` 写出了：

```python
"onClick": Callback(partial(_on_menu_click, self)),
```

而这个写法有两个独立缺陷：

1. **`partial` 包了一层 view 实例**——本应直接 `Callback(_on_menu_click, self, ...)`，view 走 Callback 的 positional 通道
2. **漏写 `Expr.wire("$0.key")`**——antd Menu 的 onClick 会送 `{key, keyPath, item, domEvent}`，但完全没声明 wire 抽取

结果是菜单点击无响应。

### 根因（修订）

经讨论核对 `events.py` 实际行为，事故归因如下：

| 缺陷 | 直接后果 | `Callback` 是否有缺陷 |
|------|---------|--------------------|
| ① 用 `partial(self)` 包 view | dispatch 行为与 `Callback(_on_menu_click, self)` 完全等价（`partial.args` 调用时被前置）。冗余但无害 | 否，按声明执行 |
| ② 漏 `Expr.wire("$0.key")` | `to_wire()` 无 `$args` → 前端不投递 payload → 后端 `_on_menu_click(self)` 调用时 `panel_id` 走默认值 `""` → `if not panel_id: return` 静默退出 | 否，按声明执行 |

致命的是 ②，不是 ①。`Callback` 在它的责任范围内（声明→to_wire→dispatch→调 handler）每一步都忠实执行了使用者给的指令——**框架没有缺陷**。

事故链条上还有一层使用者侧的"沉默兜底"：handler 自己写了 `panel_id: str = ""` 默认值 + `if not panel_id: return`，把"Callback 漏配置"吃成静默退出。这同样是使用者纪律问题，不是框架要管的事。

真正能被框架侧改进的只剩一条：**之前 docstring 没有覆盖到 antd 组件回调最高频的"view + wire" 混合 positional 写法**，让没经验的开发者凭直觉去摸 `partial`，然后在 partial 这条旁路里把 ② 漏掉了。

### 改进目标

- `Callback` docstring 忠实陈述参数语义（类比 `functools.partial`，特定参数用 `Expr`）
- 示例覆盖之前漏掉的常见组合（view+wire 混合、render 期变量绑值）
- 仓库内不留 `partial(...)` 包 Callback 的反面教材

## 关键参考

- `mutgui/src/mutgui/events.py` — `Callback` 完整实现（Expr env 分派、to_wire、handle）
- `mutgui/docs/specifications/refactor-callback-explicit-expr.md` — Expr 重构设计文档（API examples 章节）
- `mutagent/src/mutagent/webui/_settings_page_impl.py` — 事故现场（已修复为正确写法）

## 设计方案

### 方案定位

框架无缺陷，本次改进**只动文档与代码示例**：

- **文档**：重写 `Callback` docstring，补齐之前没覆盖到的常见用法
- **代码**：清理仓库内 13 处 `Callback(partial(...))` 残留，让所有现存样例直接读就能上手

`Callback` 类的运行时行为零变更。

### docstring 改写要点

- 类比 `functools.partial`：positional/keyword args 在 dispatch 时按顺序映射到 handler 形参
- 明确三种"值的来源"及对应写法：
  - 普通 Python 值（包括 view 实例、字面量、render 期变量）→ direct，dispatch 时原样 forward
  - `Expr.wire("$N.path")` → 由 wire 端事件 payload 提供
  - `Expr.host("event.path")` → 由本端 dispatch context 求值
- 示例覆盖（6 行）：
  1. 无参 `Callback(self._on_click)`
  2. view + 字面量 + render 期变量 混合（keyword 形式注即可）
  3. view + wire 混合 positional — 最高频
  4. wire keyword
  5. host keyword
  6. 多个 wire 位置参数
- 保留现有"字符串就是字符串"提示

### 代码侧反面教材清理

仓库内所有 `Callback(partial(...))` 写法全部改为 `Callback` 直接传 positional。改写规则：

- `Callback(partial(handler, *bound), **kw)` → `Callback(handler, *bound, **kw)`
- 行为完全等价（同 `Callback.args` / 同 `to_wire` / 同 dispatch 路径）
- 改完后若文件不再使用 `partial`，一并删掉 `from functools import partial`

实施时用 `grep -rn "Callback(partial" --include="*.py"` 在 mutgui/mutagent/mutbot 全仓搜索定位。

### 不做的事

- **不在 `Callback` 加构造期参数失配校验**：handler 形参表 vs Callback 提供数量的对齐校验，本质是替使用者的 handler 写法做兜底，越界
- **不在 dispatch 期加 signature.bind 校验**：同上理由——`bind()` 通过的就是合法 Python 调用，框架不挡；`bind()` 不通过的 Python 自己会抛 `TypeError`，无需框架代劳
- **不自动 unwrap `functools.partial`**：清理后仓库示例里没有 partial 出现，不需要框架兜底"心智模型对齐"
- **不在 docstring 写反例**：反例形态写不完，正例覆盖到就够；让 docstring 保持纯描述性
- **不引入 antd 事件 payload 速查表**：antd payload 形状是外部知识，由使用者自查；框架不维护这张表
- **不改 wire 协议**：前端零改动

## 消费者场景

| 消费者 | 场景 | 验收标准 |
|--------|------|---------|
| mutagent 开发者 | 给 antd.Menu / Tabs / Select 等带 payload 的组件写 onClick / onChange | 读 `Callback` docstring 的 view+wire 示例 + 查 antd 组件事件 payload 形状 → 直接写对 |
| mutbot 开发者 | render 期循环变量 + view 透传的回调（如 provider 列表按钮） | 读 docstring 的 "render 期变量" 示例 → 直接 `Callback(handler, key, view=self)`，不会去想 `partial` |
| 仓库新人 | 浏览 mutagent / mutbot 现存代码学习 Callback 用法 | 全仓 grep 不到 `Callback(partial(` 这种反面教材 |

## 实施步骤清单

分两阶段：先改 mutgui 自身（文档源头），再机械化扫所有使用方（包括 mutgui 自己仓库内部）。

### 阶段一：mutgui 自身改动

- [x] 重写 `mutgui/src/mutgui/events.py` 中 `Callback.__init__` 的 docstring（按"docstring 改写要点"覆盖 8 个示例）
- [x] mutgui 测试：`cd mutgui && pytest`（243 passed）

### 阶段二：机械化清理所有使用方

范围：`mutgui` / `mutagent` / `mutbot` 三个仓库全部 Python 代码（包括 mutgui 自己的 demo / tests 等）。同时检查所有 `Callback(lambda ...)` 用法（binding 包装而非 handler 本身），改为直接 positional args。

- [x] 全仓 grep 定位：`grep -rn "Callback(partial" mutgui mutagent mutbot --include="*.py"` → 13 处
- [x] 逐处按改写规则清理，同时删掉不再使用的 `from functools import partial`（3 个文件：_settings_llm.py / _settings_mcp.py / setup_view.py）
- [x] 同时清理 `Callback(lambda ...)` 绑定包装 10 处（menu.py 4 / gomoku.py 3 / mahjong.py 3）
- [x] 复核：`Callback(partial` 全仓零输出
- [x] 手工验证：受影响模块的按钮交互正常（实施时按改动范围决定测哪些页面）
