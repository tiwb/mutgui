/**
 * 解析 $ 标签中的提取路径。
 *
 * 路径语法：
 *   $0            → args[0]
 *   $0.target     → args[0].target
 *   $0.target.value → args[0].target.value
 *   $0.toHexString() → args[0].toHexString()
 */
export function resolvePath(args: unknown[], path: string): unknown {
  // 解析 $N 前缀
  const match = path.match(/^\$(\d+)(.*)/);
  if (!match) return undefined;

  const argIndex = parseInt(match[1], 10);
  const rest = match[2]; // e.g. ".target.value" or ".toHexString()"

  let val: any = args[argIndex];
  if (!rest) return val;

  // 按 . 分割剩余路径，逐段访问
  const segments = rest.split('.').filter(Boolean);
  for (const seg of segments) {
    if (val == null) return undefined;
    // 检查是否是方法调用 foo()
    const callMatch = seg.match(/^(\w+)\(\)$/);
    if (callMatch) {
      val = val[callMatch[1]]();
    } else {
      val = val[seg];
    }
  }
  return val;
}
