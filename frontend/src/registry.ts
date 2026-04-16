/**
 * mutgui 组件注册表。
 *
 * 纯 type 名 → React 组件的映射。事件提取逻辑由 $ 标签驱动，不在注册表中。
 */
import type { ComponentType } from 'react';

const registry = new Map<string, ComponentType<any>>();

/** 注册一个组件类型。 */
export function register(type: string, component: ComponentType<any>): void {
  registry.set(type, component);
}

/** 按 type 名查找组件。 */
export function resolve(type: string): ComponentType<any> | undefined {
  return registry.get(type);
}

/** 批量注册。 */
export function registerAll(
  components: Record<string, unknown>,
): void {
  for (const [name, comp] of Object.entries(components)) {
    if (typeof comp === 'function' || (typeof comp === 'object' && comp !== null && 'render' in comp)) {
      register(name, comp as ComponentType<any>);
    }
  }
}
