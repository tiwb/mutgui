/**
 * mutgui 通用渲染器。
 *
 * 将 JSON 组件树渲染为 React 组件。
 * - 按 $component 查 registry 获取组件
 * - 含 $ 键的值由框架处理（生成事件转发函数）
 * - 其余 props（含 id、type 等）透传给组件
 * - children 如果是数组则递归渲染
 */
import { useRef, useState, useEffect } from 'react';
import { resolve } from './registry';
import { resolvePath } from './resolve-path';

/** 组件 schema 的基础类型。 */
export interface ComponentSchema {
  $component: string;
  id?: string;
  children?: ComponentSchema[] | string;
  [key: string]: unknown;
}

/** WebSocket 连接的最小接口。 */
export interface WsLike {
  send(data: string): void;
}

/** 未知组件的降级显示。 */
function UnknownComponent({ $component }: { $component: string }) {
  return <div style={{ color: 'red', border: '1px solid red', padding: 4 }}>Unknown: {$component}</div>;
}

/** 从 $ 标签生成事件转发函数。 */
function createHandler(
  spec: Record<string, unknown>,
  sourceId: string,
  eventName: string,
  ws: WsLike,
) {
  const extract = (spec.extract || {}) as Record<string, string>;
  return (...args: unknown[]) => {
    const data: Record<string, unknown> = {};
    for (const [key, path] of Object.entries(extract)) {
      data[key] = resolvePath(args, path);
    }
    ws.send(JSON.stringify({ source: sourceId, event: eventName, data }));
  };
}

/** 处理单个组件的 props：$ 标签 → 事件函数，其余透传。 */
function processProps(
  schema: ComponentSchema,
  ws: WsLike,
): Record<string, unknown> {
  const props: Record<string, unknown> = {};

  for (const [key, val] of Object.entries(schema)) {
    if (key === '$component') continue;

    if (key === 'children' && Array.isArray(val)) {
      // 子组件列表 → 递归渲染
      props[key] = <MutguiRenderer tree={val as ComponentSchema[]} ws={ws} />;
    } else if (
      val != null &&
      typeof val === 'object' &&
      !Array.isArray(val) &&
      '$' in (val as Record<string, unknown>)
    ) {
      // $ 标签 → 生成事件处理函数
      props[key] = createHandler(
        val as Record<string, unknown>,
        schema.id || '',
        key,
        ws,
      );
    } else {
      props[key] = val;
    }
  }

  return props;
}

/** 渲染单个组件节点。 */
function MutguiComponent({ schema, ws }: { schema: ComponentSchema; ws: WsLike }) {
  const composingRef = useRef(false);
  const imeValueRef = useRef<string | null>(null);
  const [imeValue, setImeValue] = useState<string | null>(null);

  const Component = resolve(schema.$component);
  if (!Component) return <UnknownComponent $component={schema.$component} />;

  const props = processProps(schema, ws);

  const hasTextInput = typeof props.value === 'string' && typeof props.onChange === 'function';
  const serverValue = hasTextInput ? (props.value as string) : '';

  // 服务端值更新且不在组合状态时，清除本地 IME 覆盖
  useEffect(() => {
    if (!composingRef.current) {
      setImeValue(null);
      imeValueRef.current = null;
    }
  }, [serverValue]);

  if (hasTextInput) {
    const origOnChange = props.onChange as (...args: unknown[]) => void;

    // 组合期间用本地值显示，防止服务端回显打断输入法
    if (imeValue !== null) {
      props.value = imeValue;
    }

    props.onChange = (...args: unknown[]) => {
      const e = args[0] as any;
      const val: string = e?.target?.value ?? String(e ?? '');

      if (composingRef.current) {
        // 组合期间：只更新本地状态，不发送到服务端
        imeValueRef.current = val;
        setImeValue(val);
        return;
      }

      // 正常输入：发送到服务端
      origOnChange(...args);
    };

    // 用包装 div 捕获组合事件（冒泡可靠，不依赖 Ant Design 转发）
    return (
      <div
        style={{ display: 'contents' }}
        onCompositionStart={() => { composingRef.current = true; }}
        onCompositionEnd={(e) => {
          composingRef.current = false;
          // 读取 DOM 输入元素的最终值
          const input = e.target as HTMLInputElement;
          const finalVal = input?.value ?? imeValueRef.current ?? '';
          imeValueRef.current = null;
          setImeValue(finalVal);

          // 发送最终值到服务端
          if (schema.id) {
            const spec = schema.onChange as Record<string, unknown> | undefined;
            if (spec && typeof spec === 'object' && '$' in spec) {
              const extract = ((spec as Record<string, unknown>).extract || {}) as Record<string, string>;
              const data: Record<string, unknown> = {};
              for (const key of Object.keys(extract)) {
                data[key] = finalVal;
              }
              ws.send(JSON.stringify({ source: schema.id, event: 'onChange', data }));
            }
          }
        }}
      >
        <Component {...props} />
      </div>
    );
  }

  return <Component {...props} />;
}

/** 渲染整个组件树。 */
export function MutguiRenderer({ tree, ws }: { tree: ComponentSchema[]; ws: WsLike }) {
  return (
    <>
      {tree.map((schema, i) => (
        <MutguiComponent key={schema.id || i} schema={schema} ws={ws} />
      ))}
    </>
  );
}
