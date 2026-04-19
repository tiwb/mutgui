/**
 * mutgui 组件解析器 — 基于解析链的组件查找。
 *
 * 组件源按优先级排列（后加入的优先），resolve 依次查找。
 * 未找到的名字返回字符串，由 React.createElement 作为原生 HTML 元素渲染。
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

/** 按名字解析组件。返回 React 组件或字符串（原生 HTML 元素）。 */
export function resolve(name: string): ComponentType<any> | string {
  // 属性路径：Input.TextArea → 先完整匹配，再尝试属性访问
  if (name.includes('.')) {
    const [prefix, suffix] = name.split('.', 2);

    // 1. 命名空间查找：__name__ 匹配 prefix，取 suffix
    for (const src of sources) {
      if (src.__name__ === prefix && src[suffix]) {
        return src[suffix] as ComponentType<any>;
      }
    }

    // 2. 属性路径查找：src[prefix][suffix]
    for (const src of sources) {
      const parent = src[prefix];
      if (parent && typeof parent === 'object' && (parent as any)[suffix]) {
        return (parent as any)[suffix] as ComponentType<any>;
      }
    }
  }

  // 直接名字查找
  for (const src of sources) {
    if (src[name]) {
      return src[name] as ComponentType<any>;
    }
  }

  // 兜底：返回字符串，React.createElement 当原生 HTML 元素渲染
  return name;
}
