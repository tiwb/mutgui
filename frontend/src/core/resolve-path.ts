/**
 * 解析 $ 标签中的提取路径。
 *
 * 路径语法：
 *   $0                  → args[0]
 *   $0.target           → args[0].target
 *   $0.target.value     → args[0].target.value
 *   $0.touches[0].x     → args[0].touches[0].x
 *   $1.items[2].id      → args[1].items[2].id
 *   $0.toHexString()    → args[0].toHexString()
 *
 * 与 host 端表达式语法保持对称（点分属性链 + [int] 下标）。
 */
export function resolvePath(args: unknown[], path: string): unknown {
  // 解析 $N 前缀
  const match = path.match(/^\$(\d+)(.*)/);
  if (!match) return undefined;

  const argIndex = parseInt(match[1], 10);
  const rest = match[2]; // e.g. ".touches[0].x" or ".toHexString()"

  let val: any = args[argIndex];
  if (!rest) return val;

  // 按 . 分割剩余路径，逐段访问
  const segments = rest.split('.').filter(Boolean);
  for (const seg of segments) {
    if (val == null) return undefined;
    // 方法调用 foo()
    const callMatch = seg.match(/^(\w+)\(\)$/);
    if (callMatch) {
      val = val[callMatch[1]]();
      continue;
    }
    // name[idx][idx]... 形式：先取 name，再依次走整数下标
    const indexMatch = seg.match(/^(\w+)((?:\[\d+\])+)$/);
    if (indexMatch) {
      val = val[indexMatch[1]];
      const indices = [...indexMatch[2].matchAll(/\[(\d+)\]/g)];
      for (const m of indices) {
        if (val == null) return undefined;
        val = val[parseInt(m[1], 10)];
      }
      continue;
    }
    val = val[seg];
  }
  return val;
}
