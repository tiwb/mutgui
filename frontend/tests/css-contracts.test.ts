/**
 * CSS 契约测试
 *
 * 这个文件不是普通意义上的"单元测试"——它是 mutgui 前端样式系统的"不可违反的铁律"。
 * 每条契约背后都是一个经过讨论的核心设计决策，违反它会破坏 mutgui 的基本使用契约。
 *
 * 每条契约的 describe 块顶部写明:
 *   - 契约本身(What)
 *   - 这条契约存在的理由(Why)
 *   - 历史上违反它的后果(如有)
 *   - 修改此契约的前提条件(When to change)
 *
 * 如果你（或 AI 助手）正在读这个注释并考虑修改或删除某条测试,
 * 请先停下来和用户确认。绕过这里的契约等同于拆掉地基,不应作为修 bug 的手段。
 *
 * 技术实现:用 postcss 解析 CSS 源文件,AST 遍历。
 */
import { describe, test, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import postcss, { Root, Rule, AtRule } from 'postcss';

const __dirname = dirname(fileURLToPath(import.meta.url));
const srcDir = resolve(__dirname, '../src');

/** mutgui 自有的所有 CSS 源文件(不含 index.css,它只有 @layer 声明和 @import) */
const ALL_CSS_FILES = [
  'core/base.css',
  'components/menu.css',
  'components/dock-panel.css',
  'components/virtual-list.css',
  'plugins/theme-dark/dark.css',
];

function parseFile(relPath: string): Root {
  const full = resolve(srcDir, relPath);
  const content = readFileSync(full, 'utf8');
  return postcss.parse(content);
}

// ---------------------------------------------------------------------------
// 铁律 A: 所有规则必须包在 @layer 里
// ---------------------------------------------------------------------------
// 契约:
//   mutgui 自有的所有 CSS 规则(Rule / 选择器定义)必须位于 @layer mutgui.base,
//   mutgui.components, 或 mutgui.theme 之中。CSS 文件的根节点下不允许
//   直接出现规则(包括伪元素规则如 ::-webkit-scrollbar)。
//
// Why:
//   CSS cascade 优先级:
//     用户未入 layer 的 CSS > 任何 @layer 内的 CSS
//   这是 mutgui 和宿主之间的核心契约 —— 宿主(antd / flexlayout / 用户
//   自己的 CSS)不需要 !important,只要挂在 layer 之外就能覆盖 mutgui 默认。
//   把规则写在 layer 外等于强占优先级,剥夺了下游覆盖能力。
//
// 历史事件(2026-04-22):
//   在修复 VirtualList 滚动条宽度问题时, AI 假设"antd 覆盖了我们的
//   ::-webkit-scrollbar width",于是把滚动条规则从 @layer mutgui.base 提到了
//   layer 外部以"提优先级"。事后 CDP 验证发现 antd 根本没定义 scrollbar 规则,
//   跳层没解决问题,但已经破坏了契约。此测试就是防止这类反应式违规。
//
// 修改此契约的前提:
//   需要用户明确授权。放弃这个契约是 breaking change,会让所有依赖"宿主
//   CSS 无需 !important 即可覆盖"的调用方受影响。遇到"优先级不够"
//   99% 是选择器写法问题或根因误判,不是层级问题。
// ---------------------------------------------------------------------------
describe('铁律 A: 所有规则必须包在 @layer 里', () => {
  for (const relPath of ALL_CSS_FILES) {
    test(relPath, () => {
      const root = parseFile(relPath);
      const violations: string[] = [];

      root.walk((node) => {
        // 只看根节点的直接子节点
        if (node.parent !== root) return;

        // Rule: 普通规则或伪元素规则(如 ::-webkit-scrollbar)
        if (node.type === 'rule') {
          violations.push(
            `第 ${node.source?.start?.line ?? '?'} 行: "${node.selector.substring(0, 80)}" 未包在 @layer 内`,
          );
        }
        // AtRule: 只允许 @layer, @import, @charset, @namespace
        if (node.type === 'atrule') {
          const allowed = ['layer', 'import', 'charset', 'namespace'];
          if (!allowed.includes(node.name)) {
            violations.push(
              `第 ${node.source?.start?.line ?? '?'} 行: @${node.name} 未包在 @layer 内`,
            );
          }
        }
      });

      expect(violations, `${relPath} 有规则跳出 @layer:\n${violations.join('\n')}`).toEqual([]);
    });
  }
});

// ---------------------------------------------------------------------------
// 铁律 B: 禁用 !important
// ---------------------------------------------------------------------------
// 契约:
//   mutgui 自有的 CSS 源码中任何地方不允许出现 !important。
//
// Why:
//   !important 是 CSS 的"核选项"——一旦 mutgui 用了,下游想覆盖就
//   只能也用 !important,这污染会传染到用户代码里,形成军备竞赛。
//   几乎所有 !important 都是"选择器优先级调得不对"或"放错了 layer"的
//   惰性解法,掩盖真正的结构问题。
//
// 修改此契约的前提:
//   需要用户明确授权。先看是否能通过选择器重写、layer 归属、或继承关系
//   修正解决。只有在"绝对无法用其他方式解决"并且用户同意的前提下才添加,
//   添加时必须在同一处写注释说明为什么这里必须 !important。
// ---------------------------------------------------------------------------
describe('铁律 B: 禁用 !important', () => {
  for (const relPath of ALL_CSS_FILES) {
    test(relPath, () => {
      const root = parseFile(relPath);
      const violations: string[] = [];

      root.walkDecls((decl) => {
        if (decl.important) {
          violations.push(
            `第 ${decl.source?.start?.line ?? '?'} 行: "${decl.prop}: ${decl.value} !important"`,
          );
        }
      });

      expect(violations, `${relPath} 使用了 !important:\n${violations.join('\n')}`).toEqual([]);
    });
  }
});

// ---------------------------------------------------------------------------
// 铁律 C: Token 定义(--mutgui-*)只允许在 mutgui.theme 层
// ---------------------------------------------------------------------------
// 契约:
//   以 --mutgui- 开头的 CSS 变量定义(不是使用)只能出现在 @layer mutgui.theme
//   的规则内。components 层、base 层、或 layer 外都不允许定义 --mutgui-*。
//   使用(var(--mutgui-*))不受限制,可以在任何层。
//
// Why:
//   @layer 声明顺序是 base, components, theme,theme 是最后一层,优先级最高。
//   Token 放在 theme 层,插件(如 theme-dark)才能通过同样在 theme 层的规则
//   可靠地覆盖默认值。如果有人在 components 层定义了 --mutgui-bg,
//   它会在 cascade 中被 theme 层的任何同名定义覆盖 —— 这是对的(插件应该能覆盖),
//   但如果 components 层的定义依赖该值,插件切换时会导致不一致行为。
//
//   更简单的说法:Token 是"契约变量",契约应该集中定义,不能零散在各处。
//
// 修改此契约的前提:
//   需要用户明确授权。如果某个组件确实需要专有 token(如 --mutgui-dock-splitter-bg),
//   它也应该挂在 theme 层,用 fallback 引用核心 token:
//     --mutgui-dock-splitter-bg: var(--mutgui-surface);
//   不应该直接在 components 层的规则里定义全新 token。
// ---------------------------------------------------------------------------
describe('铁律 C: Token 定义只允许在 mutgui.theme 层', () => {
  for (const relPath of ALL_CSS_FILES) {
    test(relPath, () => {
      const root = parseFile(relPath);
      const violations: string[] = [];

      root.walkDecls((decl) => {
        if (!decl.prop.startsWith('--mutgui-')) return;

        // 向上找最近的 @layer
        let cur: postcss.Container | undefined = decl.parent;
        let layerName: string | null = null;
        while (cur) {
          if (cur.type === 'atrule' && (cur as AtRule).name === 'layer') {
            layerName = (cur as AtRule).params.trim();
            break;
          }
          cur = cur.parent as postcss.Container | undefined;
        }

        if (layerName !== 'mutgui.theme') {
          const loc = `第 ${decl.source?.start?.line ?? '?'} 行`;
          const where = layerName ? `在 @layer ${layerName}` : '在 layer 外';
          violations.push(`${loc}: "${decl.prop}" 定义 ${where},应在 @layer mutgui.theme`);
        }
      });

      expect(
        violations,
        `${relPath} 的 --mutgui-* token 定义不在 theme 层:\n${violations.join('\n')}`,
      ).toEqual([]);
    });
  }
});
