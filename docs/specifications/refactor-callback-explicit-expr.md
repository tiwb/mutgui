# Callback / Bind 显式 `Expr` 引用重构

**状态**：✅ 已完成（阶段 1 + 2 均已实施，mutbot 无需改动）
**日期**：2026-05-14
**类型**：重构（不兼容 API 升级）

## 需求

1. `Callback` 当前把"构造时已知的值"和"dispatch 时延迟取的值"全塞进字符串 DSL，导致歧义：`Callback(handler, "hello")` 看起来像传字符串常量，实际被解释成前端 resolvePath，运行时静默解析为 `None`
2. 非字符串 kwarg（`Callback(handler, view=self)`）不报错、到 `to_wire()` 才崩，错误暴露点距离构造点很远
3. 现有三套 DSL（`$0.xxx` 前端取值 / `@view` 注入实例 / `@event.xxx` 后端元数据）+ "extract 必须是 str" 隐式约定，心智负担大；其中 `@view` 等价于 `view=self` 透传，是历史变通
4. `Bind` 同样存在 path 参数被传非字符串时延迟报错的问题

## 关键参考

### 现有实现

- `mutgui/src/mutgui/events.py` — `Callback` / `Bind` / `EventHandler`
  - `Callback.__init__:79` — `*args: str, **extract: str`，运行时不强制
  - `Callback.handle:88` — `@`-DSL 解析（`event` / `view` 注入源）
  - `Callback.to_wire:103` — 过滤 `@` 前缀，剩下当 path 发给前端
  - `Bind.__init__:135` — `path: str`，运行时不强制
- `mutgui/src/mutgui/_view_impl.py:281` — `_process_value` 调 `EventHandler.to_wire()`
- `mutgui/frontend/src/renderer.tsx` — `processProps` / `createHandler`，按 `$handler` wire 格式提取
- `mutgui/frontend/src/resolve-path.ts` — 前端 `resolvePath`

### 现有 wire 协议（基本不变，仅前端 path 解析增强）

```jsonc
// Callback with kwargs
{"$handler": {"value": "$0.target.value"}}
// Callback with positional args
{"$handler": {"$args": ["$0.x", "$0.y"]}}
// Bind
{"$handler": {"$args": ["$0.target.value"]}}
```

### 全工作区现有用法（迁移影响面）

| 类别 | 数量 | 主要分布 |
|------|------|---------|
| `Callback(method)` 简单形式 | 大头（~70+） | 全部项目 |
| `Callback(lambda x=v: ...)` 闭包捕获 | ~15 处 | 各 demo |
| `Callback(handler, "$0.xxx")` 前端取值 | 8 处 | mutgui demo + tests + mutagent 1 处 |
| `Callback(handler, view="@view")` | 24 处 | mutagent webui (settings_llm/settings_mcp 为主) |
| `Callback(handler, ..., viewport_id="@event.viewport_id")` | 4 处 | mutgui dock_panel(3) + virtual_list(1) |
| `Bind(self, attr, "$0.xxx")` | ~15 处 | mutgui demo + mutagent webui |

mutbot 全部 7 处都是简单形式，无 DSL。

## 设计方案

### 核心洞察：所有参数都是同一个抽象的不同 binding

`Callback` 的每个参数都在回答同一个问题：**"dispatch 时把什么值送给 handler？"**。区别只在于"那个值的来源"。把"来源"提出来作为正交维度，三类参数归并为同一抽象的三种 binding：

| 求值环境 | 含义 | 求值时刻 |
|---------|------|---------|
| **direct** | 直接持有的 Python 值 / 引用 | dispatch 时直接 forward（mutable 引用的属性变化会被看到） |
| **wire** | wire 协议另一端的事件 payload | dispatch 时由对端按表达式 resolve |
| **host** | 运行 mutgui 业务代码这一端的 dispatch context（event / future: view / session ...） | dispatch 时本进程内按表达式 walk |

> **mutgui 视角下的术语锚定**：mutgui 是 wire 协议的**定义者**，不假设对端是 web。"wire 那一侧"对端可以是 web、native、test renderer，"host 这一侧"是运行 Python 应用代码的进程。

### 内部统一抽象：`Expr`

```python
@dataclass(frozen=True)
class Expr:
    env: Literal["direct", "wire", "host"]
    source: Any   # direct: 任意 Python 值；wire/host: 表达式字符串
```

frozen + 基于 `(env, source)` 的 `__eq__` / `__hash__`，可作 dict key / set 成员。

API 表面只暴露**统一入口**，env 是工厂方法属性而非类名：

| 用户写 | 内部表示 | 求值时机 |
|--------|---------|---------|
| `view=self` | `Expr(env="direct", source=self)`（自动包装） | dispatch 时直接 forward |
| `value=Expr.wire("$0.target.value")` | `Expr(env="wire", source="$0.target.value")` | dispatch 时对端 resolve |
| `viewport_id=Expr.host("event.viewport_id")` | `Expr(env="host", source="event.viewport_id")` | dispatch 时本端 walk |

### 设计原则

- **零隐式 DSL** — 字符串就是字符串，没有偷偷的 path 解释；所有"引用"必须显式包成 `Expr.wire(...)` / `Expr.host(...)`
- **零 fail-fast 类型校验** — API 让人无从用错，因此不再需要运行时类型检查
- **字符串载体而非 Python builder** — 引用对象用字符串描述表达式（`Expr.wire("$0.x")`），不用 magic 属性链（`Wire[0].x`）。理由见下节
- **统一抽象、独立求值器** — 内部 `Expr` 抽象统一三种环境；wire 和 host 各自有求值器实现，互不耦合
- **`@view` 退役** — `view=self` 透传等价且更直观（mutagent webui 24 处人工 review 迁移）

### 关键决策：为什么字符串载体而非属性链 builder

候选过两种载体：

```python
Expr.wire("$0.target.value")      # 字符串载体
Wire[0].target.value              # 属性链 builder（拒绝）
```

否决属性链 builder 的理由：

1. **形似神不似**：builder 看起来像 Python 属性访问，但实际不享有任何属性访问的好处（无 IDE 补全、无 mypy 检查、写错不会即时报错）。这种"假装"比直接的字符串 DSL 更让人困惑
2. **后端属性链同样是伪装**：magic builder 接受任何属性名，"看起来 Pythonic"对应不到任何静态保障
3. **字符串载体诚实**：`Expr.wire("$0.x")` 明牌承认"这是个 DSL 表达式"，不假装是别的东西
4. **扩展空间统一**：未来若引入 JMESPath / Python 子集等更强表达式语法，字符串载体无痛升级，调用代码 0 改动；属性链 builder 受限于 Python 操作符可重载范围
5. **跨语言友好**：字符串可直接发到任何端的解析器；属性链是 Python 专属
6. **实现简单**：split + walk 即可，无需元类、无需反向序列化

### 关键决策：跨端语法对称性是巧合，不是承诺

第一版 wire 和 host 都使用同一种语法（点分属性链 + `[int]` 下标），这是**最大公约数式的对称**，不是 API 承诺。设计上明确允许两端独立演进：

| 端 | 数据形态 | 自然演进方向 | 跨语言代价 |
|----|---------|------------|----------|
| wire | event payload（一棵 JSON 树） | Path 查询语言（JMESPath / JSONata） | 前端 JS 实现，轻 |
| host | dispatch context（Python 对象） | Python 表达式子集（simpleeval 路线） | 仅 Python 端，自然 |

强求两端永远对称，要么 host 浪费（path 表达不了 `event.x + offset.x`），要么 wire 重负担（前端要实现 Python 表达式语义）。设计文档承认两端方言可分叉，是字符串载体相对属性链 builder 的核心红利之一。

`Expr.wire` / `Expr.host` 各自的字符串方言由各端解析器定义，第一版恰好相同。

### Wire 协议

**结构不变**。前端看到的还是 `{"$handler": {"key": "...", "$args": [...]}}` 格式。

**唯一前端代码改动**：`resolve-path.ts` 增强支持 `[int]` 下标，使 wire 端语法与 host 端对称。

`Expr.host(...)` 在 host 端处理，**不出现在 wire 上**。

### API 形态

```python
from mutgui import Callback, Bind, Expr

# direct 环境 —— 直接传值（无需任何包装）
Callback(self._on_click)
Callback(handler, view=self)               # 替代旧 view="@view"
Callback(handler, "hello", count=42)       # 字符串/数字都是字面值

# wire 环境 —— Expr.wire(...) 显式标记
Callback(handler, value=Expr.wire("$0.target.value"))
Callback(handler, x=Expr.wire("$0.x"), y=Expr.wire("$0.y"))
Callback(handler, Expr.wire("$0.width"), Expr.wire("$0.height"))

# host 环境 —— Expr.host(...) 显式标记
Callback(handler, viewport_id=Expr.host("event.viewport_id"))

# 混用
Callback(handler, view=self, value=Expr.wire("$0.target.value"))

# Bind —— 第三参语义已锁定为 wire path，接受 Expr.wire 或字符串简写
Bind(self, "name", Expr.wire("$0.target.value"))
Bind(self, "name", "$0.target.value")     # 简写等价
Bind(self, "value", "$0")
```

### `Callback` 行为

构造时：
- 接受任意类型的 args / kwargs，不做类型校验
- 内部把每个参数包装成 `Expr`：`Expr` 实例直接采用，其余视为 `direct` 环境的 source

`to_wire()`：
- 只把 wire 环境的 expr 写入 wire payload（direct 和 host 都不出现在 wire 上）
- wire payload 格式与现有协议一致

`handle()`：
- 按每个参数的环境分别求值：
  - direct → 直接取 source
  - wire → 从 `event.data` 按 key 取（前端已 resolve 完成）
  - host → 在本端 dispatch context 上按 AST 子集 walk
- 求值后按原 args/kwargs 顺序送给 user callback

### `Bind` 的特殊性

`Bind` 的 path 参数语义本身就是"前端值赋给后端属性"，必然是 wire 环境的引用，不可能是 direct 或 host：

```python
Bind(self, "name", Expr.wire("$0.target.value"))    # 显式
Bind(self, "name", "$0.target.value")               # 字符串简写（自动 wrap 成 wire）
```

`Bind` 接受字符串简写，因为这里不存在与 direct 字符串的歧义 —— 第三参的语义在文档层面已锁定为 wire path。其他类型一律 `TypeError`。

### Wire expr 解析与校验

**语法**：`$N` 入口（N 是事件参数序号） + 点分属性链 + 整数下标。

```
$0
$0.target.value
$0.touches[0].x
$1.items[2].id
```

**构造期轻量校验**（host 端）：必须以 `$N` 开头且 N 是非负整数；其他详细解析交由对端。错误立即 `ValueError`。

**dispatch 期解析**：由 wire 协议接收方实现（mutgui 第一版前端在 `resolve-path.ts`）。

### Host expr 解析与求值

**语法**：AST 严格白名单子集 —— `Name` 入口 + `Attribute` (`.attr`) + `Subscript` (`[int]`)。

```
event.viewport_id
event.touches[0].x
event.data
```

**实现**：`ast.parse(source, mode='eval')` 后白名单 NodeVisitor，~30 行单文件。

```python
def parse_host_expr(source: str) -> list:
    """返回 [('name', 'event'), ('attr', 'touches'), ('index', 0), ('attr', 'x')]"""
    try:
        tree = ast.parse(source, mode='eval').body
    except SyntaxError as e:
        raise ValueError(f"Invalid host expression: {source!r}") from e

    segs = []
    while isinstance(tree, (ast.Attribute, ast.Subscript)):
        if isinstance(tree, ast.Attribute):
            segs.append(('attr', tree.attr))
        else:
            slc = tree.slice
            if not (isinstance(slc, ast.Constant) and isinstance(slc.value, int)
                    and not isinstance(slc.value, bool)):
                raise ValueError(
                    f"Only integer index supported in host expr: {source!r}"
                )
            segs.append(('index', slc.value))
        tree = tree.value
    if not isinstance(tree, ast.Name):
        raise ValueError(f"Host expr must start with a name: {source!r}")
    segs.append(('name', tree.id))
    segs.reverse()
    return segs
```

**自动拒绝**（一律构造期 `ValueError`）：

| 写法 | 拒绝原因 |
|------|---------|
| `event.data["key"]` | Subscript.slice 不是 int Constant（YAGNI，但不堵路） |
| `event.touches[-1]` | `-1` 是 `UnaryOp(USub, Constant(1))`，不是 Constant（YAGNI） |
| `event.x + 1` | BinOp（YAGNI） |
| `f(event.x)` | Call（YAGNI） |

**dispatch context**：第一版只有一个 key `event`（mutgui `Event` 对象，字段 `component_id` / `name` / `data` / `viewport_id`）。未来扩展通过往 context 加 key 实现，**不开新 env**。

### 错误时机

| 环节 | 时机 | 行为 |
|------|------|------|
| `Expr.host(bad_syntax)` | 构造期 | `ValueError`（AST 解析失败） |
| `Expr.wire(no_dollar_prefix)` | 构造期 | `ValueError`（缺 `$N` 前缀） |
| `Bind(self, attr, 123)` | 构造期 | `TypeError`（既非 `Expr.wire` 也非 str） |
| `Callback(...)` 任意参数类型 | 构造期 | 不报错（重构后皆为合法用法） |
| host expr 求值时段不存在的属性 | dispatch 期 | `AttributeError` 抛出（不静默吞） |

### 不做的事（第一版 YAGNI，但不堵路）

- **不做向后兼容**的 `@view` / `@event.xxx` 字符串 DSL（本地工程未发布，一次性切换）
- **不做属性链 builder 形式**（`Wire[0].x.y`），见上文决策
- **不做 host expr 高级语法**：字典 key、负数索引、算术、过滤、函数调用 — 字符串载体保留未来引入更强表达式引擎的可能（参考 simpleeval / asteval / RestrictedPython）
- **不做 cross-env 组合**（`event.x` from wire 和 `offset.x` from host 相加）— 在 Python handler 里两行解决，远比表达式引擎里支持简单
- **不做模板字符串**（`"Hello, {event.user.name}"`）— 这是包裹 Expr 的上层特性，非 Expr 替代品；用户在 handler 里 f-string 拼接即可
- **不在 Expr 上加 `lang=` 参数** — 字符串载体本来开放，未来需要多方言时通过新工厂方法（如 `Expr.wire_jmespath(...)`）引入，不破坏现有 API

## 实施步骤

分两阶段提交，**阶段 1 完成验证后再启动阶段 2**。

### 阶段 1：mutgui（机械替换 + 核心实现）

- [x] **`src/mutgui/events.py`**：
   - 新增 `Expr` frozen dataclass（env + source + `__eq__/__hash__`）
   - 新增 `Expr.wire(source)` / `Expr.host(source)` classmethod，构造期校验
   - 新增 `parse_host_expr(source)` AST 子集解析器（`functools.lru_cache` 缓存）
   - 新增 `eval_host_expr(source, context)` 求值器
   - 重写 `Callback.__init__` / `to_wire` / `handle`（按 env 分派求值）
   - 重写 `Bind.__init__`（接受 `Expr.wire` 或 str 简写）
   - 升级 `EventHandler` 基类：接受 Any kwarg，自动 wrap 为 Expr，`to_wire` 只输出 wire env
- [x] **`src/mutgui/__init__.py`**：导出 `Expr`
- [x] **`frontend/src/core/resolve-path.ts`**：增强支持 `name[int]` 下标语法
- [x] **`src/mutgui/menu.py` / `_menu_impl.py`**：`MenuTrigger` 复用基类 Expr 机制
   （设计文档遗漏，但与 Callback 共享 EventHandler 基类，必须同步迁移）
- [x] **`src/mutgui/dock_panel.py`**：4 处 `"@event.viewport_id"` → `Expr.host(...)`，wire 引用 `"$0.xxx"` → `Expr.wire(...)`
- [x] **`src/mutgui/virtual_list.py`**：同上
- [x] **`demo/examples/action.py`** / **`demo/examples/menu.py`**：所有 Callback / MenuTrigger wire 引用包装为 `Expr.wire(...)`；`Bind` 字符串简写保留
- [x] **`tests/test_events.py`**：用新 API 重写；新增 `parse_host_expr` 白名单 + 拒绝路径单测、`eval_host_expr` 单测、`Expr` 工厂校验单测
- [x] **`tests/test_nesting.py`** / **`tests/test_session.py`** / **`tests/test_menu.py`**：用新 API 更新
- [x] **`npm --prefix mutgui/frontend run build`** 通过（4 个 vite bundle 全部干净）
- [x] **`pytest`**（224 passed）+ **`mypy --strict`**（0 issues）通过 → 待人工 demo 自检后提交

### 阶段 2：mutagent webui

**策略**：每个 `view="@view"` 调用点回到原始问题——handler 是否需要 view 参数？

- 全部 26 处 `view="@view"` 确实需要（handler 是模块级函数，需要 View 引用做 invalidation），改为 `view=self`（因为 Callback 都在 View 的 render 方法内，self 即 View 实例）
- 全部 `Bind(self, attr, "$0.xxx")` 保持字符串简写（Bind 第三参语义已锁定为 wire，无需 Expr.wire 包装）
- `_toolbar_impl.py` 一处 `Callback(lambda, "$0", view="@view")` → `Expr.wire("$0")` + `view=self`

#### `_blocks_impl.py`

- [x] 1 处 `view="@view"` → `view=self`（`_toggle_thinking`）

#### `_chat_input_impl.py`

- [x] 1 处 `view="@view"` → `view=self`（`_submit`）
- [x] `Bind(self, "text", "$0")` — 字符串简写保留

#### `_messages_impl.py`

- [x] 1 处 `view="@view"` → `view=self`（`_toggle_tool_card`）

#### `_settings_llm.py`

- [x] 8 处 `view="@view"` → `view=self`（`_edit_provider`、`_start_add_provider`、`_cancel_settings`、`_save_all_settings`、`_back_to_list`、`_discover_models`、`_delete_provider`、`_save_provider_edits`）
- [x] 5 处 `Bind(...)` — 字符串简写保留

#### `_settings_mcp.py`

- [x] 14 处 `view="@view"` → `view=self`（`_edit_source`、`btn_handler`、`_start_add`、`_close_panel`、`_toggle_fn`、`_toggle_ns`、`_back_to_list`、`_btn_reload_tools`、`_delete_source`、`_btn_disconnect`、`_btn_reconnect`、`_btn_connect`、`_save_edits`）
- [x] 11 处 `Bind(...)` — 字符串简写保留

#### `_toolbar_impl.py`

- [x] 1 处 `Callback(handler, "$0", view="@view")` → `Callback(handler, Expr.wire("$0"), view=self)`
- [x] 导入 `Expr`

#### 验证

- [x] `pytest` — 980 passed, 4 skipped
- [x] 全局 grep 确认 mutagent 中零残留 `"@view"` / `"@event."`
- [x] 全局 grep 确认 mutagent 中零 `Callback` 裸 wire 字符串（除 Bind 字符串简写外）

### 阶段 3：mutbot（无）

mutbot 全部 7 处都是简单形式，无 DSL，无需改动。

## 收益对比

| 维度 | 当前 | 重构后 |
|------|------|-------|
| 字符串歧义坑（`"hello"` 静默 None） | ❌ 存在 | ✅ 根除 |
| 非 str kwarg 延迟报错 | ❌ 存在 | ✅ 不存在（合法用法） |
| DSL 套数 | 3 套（`$` / `@view` / `@event`） | 1 套抽象（`Expr` + 三种 env） |
| 概念心智 | "三种 DSL 各管一摊" | "所有参数都是延迟求值，环境决定来源" |
| 运行时类型校验 | 需要（fail-fast） | 不需要 |
| `Callback(handler, view=self)` | TypeError | ✅ work |
| `Callback(handler, count=42)` | TypeError | ✅ work |
| 跨语言扩展（wire/host 语法分叉演进） | 受 DSL 形态限制 | ✅ 字符串载体天然支持 |
| 未来表达式引擎升级 | 需破坏式改 API | ✅ 加新工厂方法即可 |

## 未来路线（不堵死方向，YAGNI 但保留扩展点）

设计文档明确承认这些方向是开放的，第一版不实现：

| 方向 | 触发场景 | 升级方式 | 影响面 |
|------|---------|---------|-------|
| host 表达式增强（Python 子集） | 用户需要 `event.x + offset.x` / `len(event.items)` 等 | 放宽 `parse_host_expr` 白名单，参考 simpleeval | 旧代码 0 改动 |
| wire 表达式增强（Path 语言） | 复杂 payload 取值（filter / wildcard） | wire 端实现 JMESPath；可选加 `Expr.wire_jmespath(...)` 工厂 | 旧代码 0 改动 |
| 模板字符串 | Bind 到字符串 prop 需要插值 | 新增 `Template(...)` 包裹层，与 Expr 正交 | 不影响 Expr |
| host context 扩展（session / view / request） | 业务场景需要 | 往 dispatch context dict 加 key | 不增加 env 类型 |
| 跨语言端 | 非 web 渲染端（native / test） | 各端自行实现 wire expr 解析器 | wire 协议结构稳定 |

## 文件清单

| 路径 | 改动 |
|------|------|
| `mutgui/src/mutgui/events.py` | 重写（Expr + parse_host_expr + 升级 EventHandler/Callback/Bind） |
| `mutgui/src/mutgui/__init__.py` | 导出 `Expr` |
| `mutgui/src/mutgui/menu.py` | `MenuTrigger` 升级为复用基类 Expr 机制 |
| `mutgui/src/mutgui/_menu_impl.py` | `MenuTrigger.handle` 改用 `_eval_kwargs` |
| `mutgui/frontend/src/core/resolve-path.ts` | 支持 `name[int]` 下标 |
| `mutgui/src/mutgui/dock_panel.py` | 3 处 `Expr.host(...)` + 13 处 `Expr.wire(...)` |
| `mutgui/src/mutgui/virtual_list.py` | 1 处 `Expr.host(...)` + 2 处 `Expr.wire(...)` |
| `mutgui/demo/examples/action.py` | 4 处 `Expr.wire(...)` |
| `mutgui/demo/examples/menu.py` | 1 处 `Expr.wire(...)`（MenuTrigger） |
| `mutgui/tests/test_events.py` | 重写（45 cases，含 parse_host_expr 白名单/拒绝/求值、Expr frozen/env 分派） |
| `mutgui/tests/test_nesting.py` | 3 处 `Expr.wire(...)` |
| `mutgui/tests/test_session.py` | 1 处 `Expr.wire(...)`（EventHandler kwarg） |
| `mutgui/tests/test_menu.py` | 重写：`Expr.wire(...)` + `view=self` 替代旧 `view="@view"` |
| `mutagent/src/mutagent/webui/_blocks_impl.py` | 1 处 `view="@view"` → `view=self` |
| `mutagent/src/mutagent/webui/_chat_input_impl.py` | 1 处 `view="@view"` → `view=self` |
| `mutagent/src/mutagent/webui/_messages_impl.py` | 1 处 `view="@view"` → `view=self` |
| `mutagent/src/mutagent/webui/_settings_llm.py` | 8 处 `view="@view"` → `view=self` |
| `mutagent/src/mutagent/webui/_settings_mcp.py` | 14 处 `view="@view"` → `view=self` |
| `mutagent/src/mutagent/webui/_toolbar_impl.py` | 1 处 `"$0"` → `Expr.wire("$0")` + `view="@view"` → `view=self` |
