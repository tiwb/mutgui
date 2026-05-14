# DockPanel 测试用例补充 设计规范

**状态**：✅ 已完成
**日期**：2026-04-21
**类型**：测试

## 需求

1. DockPanel 目前只有 per-viewport 功能的测试（`test_dock_panel.py`），缺少基础功能的测试覆盖
2. 需要补充：布局树操作（tab_move、tab_dock、edge_dock、split_resize）、坍缩算法、merge_bars、cleanup_tree 等核心逻辑的单元测试

## 关键参考

- `tests/test_dock_panel.py` — 已有的 per-viewport 测试（15 个）
- `tests/test_virtual_list.py` — 测试模式参考（MockChannel + 同步/异步混合）
- `src/mutgui/dock_panel.py` — 被测源码

## 设计方案

新建 `tests/test_dock_panel_core.py`，纯单元测试，不需要 MockChannel / ViewPort。

按三层组织：

### 纯函数（布局树操作）

| 函数 | 测试要点 |
|------|---------|
| `collect_all_panels` | 单 TabSet、两层 Split、嵌套 Split |
| `find_node` | 找根、找叶、找嵌套、未找到 |
| `find_parent_split` | 直接子节点、嵌套子节点、根节点、未找到 |
| `find_active_in_subtree` | 有 active、无 active、嵌套取第一个 |
| `set_active_in_subtree` | 存在 → True、不存在 → False、嵌套定位 |
| `replace_node` | 替换根、替换子节点、未找到保持 identity |
| `remove_panel_from_subtree` | 移除非 active、移除 active（回退）、移除最后一个、未找到 |
| `cleanup_tree` | 空左清除、空右清除、merge_bars 修正、无变更 identity、嵌套递归 |

### 事件处理器（布局变更）

| 处理器 | 测试要点 |
|--------|---------|
| `_on_tab_move` | 正常移动、源 TabSet 清空 → cleanup、index clamp |
| `_on_split_resize` | 正常更新、clamp 到 [0, 1] |
| `_on_tab_dock` | left/right/top/bottom 四个方位、源清空 → cleanup |
| `_on_edge_dock` | left/right/top/bottom 四个边缘 |

### merge_bars 渲染

| 场景 | 测试要点 |
|------|---------|
| `_build_split_wire` | merge_bars=True 两 TabSet → mergedTabs + hideBar |

## 实施步骤清单

- [x] 创建 `tests/test_dock_panel_core.py`，实现纯函数测试（8 个函数）
- [x] 实现事件处理器测试（tab_move、split_resize、tab_dock、edge_dock）
- [x] 实现 merge_bars 渲染测试
- [x] 运行测试确认全部通过
