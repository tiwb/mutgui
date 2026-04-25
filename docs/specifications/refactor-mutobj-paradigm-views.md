# mutgui 范式改造 — View / Adapter 改用 mutobj 属性声明

**状态**：✅ 已完成
**日期**：2026-04-25
**类型**：重构

## 需求

mutgui 的 `demo/` 和 `src/` 中大量 `View` / Adapter 子类使用 Python 原生写法：

```python
class CounterView(View):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0
```

这种写法在 mutobj 范式下是反模式，但因为 demo 是 agent 学习 mutgui 用法的主要样本，agent 看到后会照搬，导致新写的 View 也是这种反模式。

需要：
1. 把所有"`__init__` + super + 纯简单赋值"的写法改为 mutobj 属性声明
2. 保留有副作用或复杂构造的 `__init__`
3. 给 agent 留下正确的 mutobj 范式样本
4. 不破坏现有功能（demo 能跑、tests 通过）

## 关键参考

### mutobj 核心机制

- `mutobj/src/mutobj/core.py` — `Declaration` / `DeclarationMeta` / `field()`
- `Declaration.__new__` (L801-818) — 自动应用属性默认值
- `Declaration.__init__` (L820-841) — kwargs setattr，位置参数按 `_get_ordered_fields` 顺序映射
- `_MUTABLE_TYPES` (L55) — `(list, dict, set, bytearray)`，直接赋值会报错，必须用 `field(default_factory=...)`
- `DeclarationMeta.__new__` (L518-555) — 子类用 `attr = value` 覆盖父类声明属性的逻辑

### 范式参照

- `mutio/src/mutio/net/server.py` — `Request` / `Response` 类的属性声明范例
  ```python
  class Request(mutobj.Declaration):
      method: str = "GET"
      headers: dict[str, str] = mutobj.field(default_factory=dict)
  ```

### 相关待讨论问题

- `mutobj/docs/specifications/feature-init-stub-ide-warning.md` — Declaration `__init__` 桩的 IDE 警告问题（**本次不动**）

## 设计方案

### 三类处理策略

#### 类别 A — 简单属性赋值，改属性声明

特征：`__init__` 体只有 `super().__init__()` + 若干 `self.x = arg` 或 `self.x = 常量`，无副作用、无计算。

改造方式：
```python
# Before
class CounterView(View):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

# After
class CounterView(View):
    count: int = 0
```

调用方变化：`CounterView()` 不变；带参的 `RecordItemView(uid, name, age, plan)` 改为 kwargs（`RecordItemView(uid=..., name=..., age=...)`）或保持位置参数（mutobj 支持按字段声明顺序映射）。

#### 类别 B — 持有可变值或子 View，用 `field(default_factory=...)`

特征：默认值是 list / dict / set / 子 View 实例（实例本身可变）。

```python
# Before
class NestingView(View):
    def __init__(self) -> None:
        super().__init__()
        self.profile = ProfileView()
        self.subscription = SubscriptionView()

# After
class NestingView(View):
    profile: ProfileView = mutobj.field(default_factory=ProfileView)
    subscription: SubscriptionView = mutobj.field(default_factory=SubscriptionView)
```

可变默认值不能直接赋值（mutobj 强制报错），子 View 实例不能用类级共享（多实例共享同一子 View 是 bug）。

#### 类别 C — 保留 `__init__`

特征（满足任一即保留）：
- 构造时有副作用（`game.on_change(self.invalidate)`、`adapter.virtual_lists.append(self)` 等）
- 构造逻辑复杂（多步嵌套构造、循环填充、外部状态修改）
- 构造时需要派生计算（如 `self.id = f"{prefix}-{uuid}"` —— 也可以改用 `default_factory=lambda: ...`，按场景选择）

### 处理范围与不处理范围

#### 处理范围

- `mutgui/demo/examples/*.py` — 所有 View / MenuView 子类
- `mutgui/demo/standalone/*.py` — 所有 View 子类
- `mutgui/src/mutgui/*.py` — 所有 Declaration 子类（View / MenuView / Adapter）

#### 不处理范围

- `mutgui/tests/` —— 测试代码故意保留各种边界写法
- 普通 Python class（非 Declaration 子类），含：
  - `view.py:ViewBlock`（普通容器类）
  - `events.py:Event` / `EventHandler` / `Callback` / `Bind`（基础设施类型，部分用 `__slots__`）
  - `menu.py:MenuTrigger`（普通 EventHandler 子类）
  - `dock_panel.py` 内的 `@dataclass` 节点定义
- Declaration 桩函数体是 `...` 的 `__init__`（例如 `viewport.py:ViewPort.__init__`、`channel.py:Channel.__init__`）—— 这是 Declaration 接口声明，实现在 `_*_impl.py`，属于 mutobj 待讨论问题，本次不动

### 已知改造清单

#### `src/mutgui/`

| 文件 | 类 | 类别 | 备注 |
|------|-----|-----|------|
| `menu.py` | `MenuView` | A | `id: str | int = mutobj.field(default_factory=lambda: f"$menu:{uuid.uuid4().hex[:8]}")` 覆盖父类 `View.id`（已验证） |
| `virtual_list.py` | `VirtualListItemAdapter` | A | 改为 `mutobj.Declaration` 子类；`virtual_lists: list = field(default_factory=list)` |
| `virtual_list.py` | `VirtualList` | C | 副作用 `adapter.virtual_lists.append(self)`；本次不瘦身 |
| `dock_panel.py` | `DockPanel` | C | 副作用 `self._assign_ids(layout)` 修改 layout；本次不瘦身 |

#### `demo/examples/`

| 文件 | 类 | 类别 | 备注 |
|------|-----|-----|------|
| `basic.py` | `CounterView` | A | `count: int = 0` |
| `no_theme.py` | `NoThemeView` | A | `click_count: int = 0` |
| `theming.py` | `ThemingDemoView` | A | `click_count: int = 0` |
| `antd.py` | `AntdFormView` | A | 多个简单字段 |
| `dock.py` | `SimplePanelView` | A | `panel_id` / `title` / `click_count` |
| `dock.py` | `DockView` | C | 复杂布局构建 |
| `nesting.py` | `ProfileView` | A | `name` / `age` / `_render_count` |
| `nesting.py` | `SubscriptionView` | A | `subscribe` / `email` / `plan` / `_render_count` |
| `nesting.py` | `NestingView` | B | 持有 `profile` / `subscription` 子 View |
| `menu.py` | `TabContextMenu` / `AddDropdownMenu` / `TemplateSubmenu` / `CommandPalettePanel` | A | 简单字段 |
| `menu.py` | `MenuDemoPage` | B | `log_lines` 用 `field(default_factory=list)` |
| `mahjong.py` | `TableView` | C | 副作用 `game.on_change(self.invalidate)` |
| `mahjong.py` | `PlayerView` | C | 同上 |
| `virtual_list.py` | `RecordItemView` | A | 6 个简单字段 |
| `virtual_list.py` | `RecordAdapter` | C | 普通 class，构造时加载 100 条数据 |
| `virtual_list.py` | `VirtualListView` | C | 子组件构造、引用 `self._on_edit` |

#### `demo/standalone/`

| 文件 | 类 | 类别 |
|------|-----|-----|
| `starlette.py` | `HelloView` | A |

### 关键注意事项

1. **可变默认值** — mutobj 黑名单 `_MUTABLE_TYPES` 强制要求 `field(default_factory=...)`，违反会在元类阶段直接抛错
2. **子 View 实例必须用 `default_factory`** — 否则所有 View 实例共享同一子 View，状态串号
3. **位置参数按字段顺序映射** — 见下方"位置参数处理"

### 已验证的范式细节

#### `_` 前缀字段处理方式（验证日期 2026-04-25）

带类型注解的 `_` 前缀字段完全正常工作：

```python
class A(mutobj.Declaration):
    _render_count: int = 0
    _items: list = mutobj.field(default_factory=list)
```

- 默认值正确应用
- `default_factory` 实例隔离正确（每个实例独立的 list）
- 子类带注解可正常覆盖父类的 `_` 前缀字段

**已知限制**：`_` 前缀字段如果**不带类型注解**，在子类中无法覆盖父类已声明属性（`core.py` L523 显式跳过）。本次改造全部用带注解形式，不受限制。

**结论**：`nesting.py` 的 `_render_count`、其他 `_*` 调试字段全部按 `_x: T = default` 或 `field(default_factory=...)` 改即可，不需要为它们保留 `__init__`。

#### 子类 `field(default_factory)` 覆盖父类声明属性（验证日期 2026-04-25）

```python
class View(mutobj.Declaration):
    id: str | int = ''

class MenuView(View):
    id: str | int = mutobj.field(default_factory=lambda: f'$menu:{uuid.uuid4().hex[:8]}')
```

- 每个 `MenuView()` 实例获得独立的 uuid id
- 父类 `View()` 不受影响（仍然 `id=''`）
- 显式传值仍然有效（`MenuView(id="custom")` 正常工作）

**结论**：`MenuView.id` 改 `default_factory` 完全可行，可以消除 `MenuView.__init__`，归入类别 A。

### 决策

#### `VirtualListItemAdapter`（原 Q1）

**决策**：改为 `mutobj.Declaration` 子类，统一范式。

理由：mutgui 整个生态都基于 mutobj，统一范式有利于业务方理解；保持普通 class 会让"业务方该怎么继承 Adapter"的样板留有反模式。

实施注意：业务子类（如 `RecordAdapter`）的 `__init__` 写法也得跟着调整 —— `records: list[tuple[...]] = mutobj.field(default_factory=list)` 等，但 `_add` 循环填充初始 100 条仍需保留 `__init__`（属于副作用，归入类别 C）。

#### `MenuView`（原 Q2）

**决策**：改 `id: str | int = mutobj.field(default_factory=lambda: f"$menu:{uuid.uuid4().hex[:8]}")`，消除 `__init__`，归入类别 A。

理由：已验证可行（见上方"子类 `field(default_factory)` 覆盖父类声明属性"）。

#### 位置参数处理（原 Q4）

**决策**：保持位置参数调用不变，属性声明顺序严格匹配现有 `__init__` 的参数顺序。

理由：mutobj 的 `Declaration.__init__` 支持位置参数按 `_get_ordered_fields` 顺序映射（见 `core.py` L820-841）。`RecordItemView(uid, name, age, plan, on_edit, on_delete)` 这类调用点在改造后仍能工作，前提是声明顺序匹配。

实施时务必：
- 改造前先记录原 `__init__` 的参数顺序
- 改造后属性声明按相同顺序排列
- 所有调用点过一遍，确认参数对位

实施补充：对继承 `View.id` / `MenuView.id` 但旧位置参数并不包含 `id` 的内部类（如菜单 demo、`RecordItemView`），字段顺序无法完全保持旧构造签名；本次统一把内部调用点改为 kwargs，避免父类字段前置导致错位。

#### `src/mutgui/` 内部组件不瘦身（原 Q5）

**决策**：本次范围只动 demo 的反模式 + `src/` 中的简单类（`MenuView`、`VirtualListItemAdapter`）。`VirtualList` / `DockPanel` 这类核心内部组件**不瘦身**。

理由：
- demo 改造高 ROI（agent 学习样本）
- 核心内部组件 `__init__` 里副作用和初始化交织，瘦身收益小、改动风险大
- 如果未来要做，单独提一个 spec


## 验收标准

1. demo 全部能跑：至少手测 `python -m demo.examples.basic`、`dock`、`nesting`、`virtual_list`、`menu`、`mahjong`
2. `pytest` 全绿
3. 改造后的 View 子类没有 `super().__init__()` 调用（除非保留 `__init__` 的 C 类）
4. 没有 `def __init__(self): super().__init__(); self.x = ...` 的纯赋值模式残留
5. 改造后的代码在 IDE 中无新警告（特别是 mutobj 的可变默认值检测应通过）

## 实施步骤清单

- [x] 改造 `src/mutgui/menu.py` 与 `src/mutgui/virtual_list.py` 中的简单 Declaration 类为 mutobj 属性声明
- [x] 改造 `demo/examples/basic.py`、`demo/examples/no_theme.py`、`demo/examples/theming.py`、`demo/examples/antd.py`、`demo/examples/dock.py` 中的 A 类 View
- [x] 改造 `demo/examples/nesting.py` 与 `demo/examples/menu.py` 中的 A/B 类 View，并用 `default_factory` 处理子 View / list 默认值
- [x] 改造 `demo/examples/virtual_list.py` 与 `demo/standalone/starlette.py` 中的 A 类 View，同时保留 C 类复杂构造
- [x] 运行现有测试，并用脚本验证关键默认值、位置参数和 `default_factory` 行为
