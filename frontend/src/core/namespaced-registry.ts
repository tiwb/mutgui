/**
 * 通用命名空间注册表解析。
 *
 * 规则与组件解析链一致：
 *   - 带点名字只在对应命名空间源内解析
 *   - 单段名字只匹配无命名空间的源
 *   - 后注册优先
 */

export interface NamespacedSource {
  __name__?: string;
  [key: string]: unknown;
}

function walk(obj: unknown, parts: string[]): unknown | null {
  if (obj == null) return null;
  if (parts.length === 0) return obj;
  const record = obj as Record<string, unknown>;
  const whole = parts.join('.');
  if (whole in record) return record[whole] ?? null;
  return walk(record[parts[0]], parts.slice(1));
}

export function resolveFromSources(
  sources: NamespacedSource[],
  name: string,
): unknown | null {
  if (name.includes('.')) {
    const dot = name.indexOf('.');
    const prefix = name.substring(0, dot);
    const rest = name.substring(dot + 1).split('.');
    for (const src of sources) {
      if (src.__name__ !== prefix) continue;
      const hit = walk(src, rest);
      if (hit) return hit;
    }
    return null;
  }

  for (const src of sources) {
    if (src.__name__) continue;
    if (src[name]) return src[name];
  }
  return null;
}
