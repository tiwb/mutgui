/**
 * mutgui 组件解析器 — 基于解析链的组件查找。
 *
 * 解析规则：
 *   - 带点名字（如 `antd.Button`、`mutgui.Menu.Item`）只在命名空间源
 *     （`__name__` 与首段匹配）内解析，命中后允许逐层属性访问
 *   - 单段名字只在无命名空间的源（手动覆盖）内匹配，不会命中任何 `__name__`
 *     标注的组件库——避免 `Button`、`Input` 等常见名字被组件库劫持
 *   - 未命中则返回字符串，由 React.createElement 作为原生 HTML 元素渲染
 */
import type { ComponentType } from 'react';
import { resolveFromSources, type NamespacedSource } from './namespaced-registry';

export interface ComponentSource extends NamespacedSource {}

const sources: ComponentSource[] = [];

function isRenderableComponentType(hit: unknown): hit is ComponentType<any> {
  if (typeof hit === 'function') return true;
  if (typeof hit !== 'object' || hit == null) return false;
  return '$$typeof' in (hit as Record<string, unknown>);
}

/** 注册一组组件到解析链（后加入的优先级更高）。 */
export function registerComponents(source: ComponentSource): void {
  sources.unshift(source);
}

/** 按名字解析组件。返回 React 组件或字符串（原生 HTML 元素）。 */
export function resolve(name: string): ComponentType<any> | string {
  const hit = resolveFromSources(sources, name);
  if (isRenderableComponentType(hit)) return hit;
  return name;
}
