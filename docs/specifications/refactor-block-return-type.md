# ViewBlock 返回类型

**状态**：✅ 已完成
**日期**：2026-04-17
**类型**：重构

## 需求

`render()` 返回 `list[Any] | dict[str, Any]`，类型松散，无法承载缓存等未来能力。

### 前置依赖

- `feature-framework-core.md` — 基础框架设计

## 关键参考

### 现有实现

- `mutgui/src/mutgui/view.py` — `render() -> list[Any] | dict[str, Any]`
- `mutgui/src/mutgui/_view_impl.py` — `_render_and_cache` 处理 render 返回值

### 现有用法统计

- 21 个 render() 返回 `list[dict]` 或 `list[Any]`（bare list，多个平级节点）
- 3 个 render() 返回 `dict[str, Any]`（单根容器）
- 框架在 `_render_and_cache` 中将 dict 统一包成 list，wire format 的 `tree` 始终是 list

## 设计方案

### ViewBlock 类

`render()` 返回 `ViewBlock` 代替 `list[Any] | dict[str, Any]`。

```python
class ViewBlock:
    """View.render() 的返回类型 — 一个 View 的完整 UI 块。"""
    __slots__ = ("items",)

    def __init__(self, items: list[dict[str, Any] | View]):
        self.items = items
```

**设计决策**：

- **只接受 list**，不支持传入单个 dict（现有 3 个返回 dict 的 View 改为 `ViewBlock([{...}])` 包一层，成本低，换来接口统一）
- **可变**（`items` 可读写）— 当前不做 diff，不可变的理由不成立，可变更简单直接
- **无额外 API** — 不加 `append()`、`find()` 等方法，ViewBlock 只是 typed wrapper；需要动态构建用普通 list，最后封装为 ViewBlock

### 用法

```python
def render(self) -> ViewBlock:
    return ViewBlock([
        {"$component": "Input", "$id": "name", "value": self.name,
         "onChange": Bind(self, "name", "$0.target.value")},
        {"$component": "Button", "$id": "submit",
         "onClick": Handler(self.save)},
    ])
```

动态构建场景：

```python
def render(self) -> ViewBlock:
    items: list[dict[str, Any] | View] = [
        {"$component": "Input", "$id": "name", "value": self.name},
    ]
    if self.show_button:
        items.append({"$component": "Button", "$id": "submit"})
    return ViewBlock(items)
```

### 框架适配

```python
def _render_and_cache(view: View) -> None:
    ext = _render_ext(view)
    block = view.render()
    ext._handlers.clear()
    ext._children = {}
    ext._view_block = block                              # 缓存 ViewBlock 对象
    ext._wire_tree = _process_items(view, block.items)
```

去掉原有的 `isinstance(raw_tree, dict)` 分支——ViewBlock 只有 list，不需要类型判断。

### 命名理由

- **ViewBlock**（View 的 UI 块）— 同时回答"什么东西"（Block）和"属于谁"（View）
- **Block 而非 Fragment** — 内部结构是 fragment 式的（多个平级节点），但语义上它代表"这个 View 的完整 UI 产出"，是完整的积木块，不是碎片
- 缓存属性 `ext._view_block` 语义清晰："这个 View 当前的 UI 块"
- Notion/Gutenberg 建立的心智模型：独立的内容块，可组合

### 未来方向（不在本次实施范围）

以下方向记录设计讨论中的思考，为未来演进保留上下文。

#### 方向 A：增量更新 API

为 ViewBlock 添加查询和修改方法，使增量更新比直接操作嵌套 dict 更可靠：

```python
# 按 $id 查找节点
node = block.find("name")
node["value"] = new_value

# 批量更新属性
block.update_props("name", {"value": new_value, "disabled": True})
```

动机：直接操作 `block.items[0]["$children"][2]["value"]` 很脆弱，按 `$id` 索引更稳定。

#### 方向 B：ViewBlock 缓存到 View + 增量 render

ViewBlock 持久化在 View 上，`render()` 可选择全量重建或增量修改：

```python
class ProfileView(View):
    def render(self) -> ViewBlock:
        # 第一次：全量构建
        return ViewBlock([...])

    def on_name_change(self, value):
        self.name = value
        # 增量：只改一个属性，省去重建整棵树
        self._view_block.find("name")["value"] = self.name
        self.update()
```

依赖方向 A 的 API 才有实用性。省的是 Python 侧对象重建成本（wire 传输仍为全量推送）。

#### 方向 C：Vue 式属性绑定（Bind 双向化）

现有 `Bind(self, "name", "$0.target.value")` 是单向的（前端事件 → 后端状态）。未来可扩展为双向——后端状态变了自动推到前端：

```python
def render(self) -> ViewBlock:
    return ViewBlock([
        {"$component": "Input", "$id": "name",
         "value": Bind(self, "name")},  # 双向：状态变 → UI 自动更新
    ])
```

此模型下 ViewBlock 成为持久的"活模板"——框架扫描其中的 Bind 引用，状态变化时只推送变化的属性。这是架构级决策，需要独立设计文档。

#### 方向间的关系

```
A（增量 API）← B（缓存 + 增量 render）依赖 A
                C（Vue 式绑定）独立于 A/B，但可与 B 组合
```

方向 C 也可以走 React 路线（render() 全量重建 + 框架自动追踪依赖触发重渲染），此时不依赖 A/B。

## 实施步骤清单

- [x] 在 `view.py` 中定义 ViewBlock 类，更新 `View.render()` 返回类型为 `ViewBlock`
- [x] 在 `__init__.py` 中导出 ViewBlock
- [x] 更新 `_view_impl.py`：`_default_render` 返回 `ViewBlock([])`，`_render_and_cache` 去掉 `isinstance(dict)` 分支，直接读 `block.items`
- [x] 更新 `virtual_list.py` 的 render()（dict → ViewBlock 包装）
- [x] 更新 `demo/app.py` 的 4 个 render()（含 1 个 dict → ViewBlock 包装）
- [x] 更新 `tests/test_session.py` 的 9 个 render()（含 1 个 dict → ViewBlock 包装）
- [x] 更新 `tests/test_nesting.py` 的 9 个 render()
- [x] 更新 `tests/test_virtual_list.py` 的 2 个 render()（含 1 个 dict → ViewBlock 包装）
- [x] 运行测试验证
