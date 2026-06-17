/**
 * mutgui 组件解析器 — 基于解析链的组件查找。
 *
 * 解析规则（优先级从高到低）：
 *   - 动态命名空间（registerNamespace）—— 如 `html.div` → 调用 resolveFn("div")
 *   - 带点名字（如 `antd.Button`、`mutgui.Menu.Item`）只在命名空间源
 *     （`__name__` 与首段匹配）内解析，命中后允许逐层属性访问
 *   - 单段名字只在无命名空间的源（手动覆盖）内匹配，不会命中任何 `__name__`
 *     标注的组件库——避免 `Button`、`Input` 等常见名字被组件库劫持
 *   - 全部未命中返回 null（不再 fallback 到裸字符串）
 */
import type { ComponentType } from 'react';
import { resolveFromSources, type NamespacedSource } from './namespaced-registry';

export interface ComponentSource extends NamespacedSource {}

/** 动态命名空间解析函数：输入 key，返回组件或字符串（HTML 标签/Web Component）或 null。 */
export type NamespaceResolver = (key: string) => ComponentType<any> | string | null;

const sources: ComponentSource[] = [];
const namespaces = new Map<string, NamespaceResolver>();

function isRenderableComponentType(hit: unknown): hit is ComponentType<any> {
  if (typeof hit === 'function') return true;
  if (typeof hit !== 'object' || hit == null) return false;
  return '$$typeof' in (hit as Record<string, unknown>);
}

/** 注册一组组件到解析链（后加入的优先级更高）。 */
export function registerComponents(source: ComponentSource): void {
  sources.unshift(source);
}

/**
 * 注册动态命名空间。用于无穷标签集合（如 html — 原生 100+ 标签 + 任意 Web Components），
 * 不适合枚举注册的场景。
 *
 * resolveFn 接收 key（如 "div"、"my-widget"），返回组件或字符串标签名或 null。
 */
export function registerNamespace(
  name: string,
  resolveFn: NamespaceResolver,
): void {
  namespaces.set(name, resolveFn);
}

/** 按名字解析组件。返回 React 组件、字符串（原生 HTML 元素）或 null（未解析）。 */
export function resolve(name: string): ComponentType<any> | string | null {
  // 带点名字 → 先检查动态命名空间
  if (name.includes('.')) {
    const dot = name.indexOf('.');
    const prefix = name.substring(0, dot);
    const key = name.substring(dot + 1);
    const nsResolver = namespaces.get(prefix);
    if (nsResolver) {
      const result = nsResolver(key);
      if (result !== null) return result;
    }
  }

  // 回退到枚举组件源
  const hit = resolveFromSources(sources, name);
  if (isRenderableComponentType(hit)) return hit;

  // 关闭 bare name fallback — 未命中返回 null
  return null;
}
