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

interface ComponentSource {
  __name__?: string;
  [key: string]: unknown;
}

const sources: ComponentSource[] = [];

/** 注册一组组件到解析链（后加入的优先级更高）。 */
export function registerComponents(source: ComponentSource): void {
  sources.unshift(source);
}

/**
 * 在命名空间源内沿属性路径查找。
 * 优先整体键（`Menu.Item`），再逐层属性访问（`Typography.Title` → `Typography['Title']`）。
 */
function walk(obj: unknown, parts: string[]): ComponentType<any> | null {
  if (obj == null) return null;
  if (parts.length === 0) {
    return typeof obj === 'function' ? (obj as ComponentType<any>) : null;
  }
  const whole = parts.join('.');
  const flat = (obj as Record<string, unknown>)[whole];
  if (flat) return flat as ComponentType<any>;
  return walk((obj as Record<string, unknown>)[parts[0]], parts.slice(1));
}

/** 按名字解析组件。返回 React 组件或字符串（原生 HTML 元素）。 */
export function resolve(name: string): ComponentType<any> | string {
  if (name.includes('.')) {
    const dot = name.indexOf('.');
    const prefix = name.substring(0, dot);
    const rest = name.substring(dot + 1).split('.');
    for (const src of sources) {
      if (src.__name__ === prefix) {
        const hit = walk(src, rest);
        if (hit) return hit;
      }
    }
    return name;
  }

  // 单段名字：只匹配无命名空间的源（手动覆盖），避免组件库名字劫持
  for (const src of sources) {
    if (src.__name__) continue;
    if (src[name]) return src[name] as ComponentType<any>;
  }
  return name;
}
