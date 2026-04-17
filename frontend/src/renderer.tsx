/**
 * mutgui 渲染器 — MutguiView + renderTree。
 *
 * - MutguiView：有状态组件，持有 tree state，提供 scope context
 * - renderTree：无状态函数，遍历 JSON 树，生成 React 元素
 * - 遇到 $view 节点 → 创建 MutguiView（递归）
 * - $ 键 → 事件转发函数，source 使用 scope 数组 + 组件 $id
 * - $id、$view、$component 不透传
 * - $children → 递归渲染为 React children
 */
import { useRef, useState, useEffect, useMemo } from 'react';
import { resolve } from './registry';
import { resolvePath } from './resolve-path';
import {
  useScope,
  useConnection,
  ScopeProvider,
  type ViewPath,
  type MutguiConnection,
} from './context';

/** 组件 schema 的基础类型。 */
export interface ComponentSchema {
  $component?: string;
  $id?: string | number;
  $view?: string | number;
  $children?: ComponentSchema[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// MutguiView — View 在前端的对应物
// ---------------------------------------------------------------------------

/**
 * 每个后端 View 在前端对应一个 MutguiView 实例。
 *
 * 职责：
 * 1. 持有 tree state — 从后端接收这个 View 的 render 结果
 * 2. 提供事件作用域 — 通过 ScopeProvider 给内部 source 加上路径前缀
 * 3. 渲染 — 用 renderTree 渲染自己的组件树
 */
export function MutguiView({ viewId }: { viewId?: string | number }) {
  const [tree, setTree] = useState<ComponentSchema[]>([]);
  const conn = useConnection();
  const parentScope = useScope();

  const fullPath = useMemo<ViewPath>(
    () => (viewId !== undefined ? [...parentScope, viewId] : []),
    [parentScope, viewId],
  );

  useEffect(() => {
    return conn.subscribe(fullPath, (newTree) => {
      setTree(newTree as ComponentSchema[]);
    });
  }, [conn, fullPath]);

  return (
    <ScopeProvider value={fullPath}>
      {renderTree(tree)}
    </ScopeProvider>
  );
}

// ---------------------------------------------------------------------------
// renderTree — 纯渲染函数
// ---------------------------------------------------------------------------

export function renderTree(tree: ComponentSchema[]): React.ReactNode[] {
  return tree.map((schema, i) => {
    // $view 节点 → 创建独立的 MutguiView（递归）
    if (schema.$view !== undefined) {
      return <MutguiView key={schema.$view} viewId={schema.$view} />;
    }

    // 普通组件节点 → 查 registry 渲染
    return <MutguiComponent key={schema.$id ?? i} schema={schema} />;
  });
}

// ---------------------------------------------------------------------------
// MutguiComponent — 渲染单个组件节点
// ---------------------------------------------------------------------------

/** 未知组件的降级显示。 */
function UnknownComponent({ $component }: { $component: string }) {
  return (
    <div style={{ color: 'red', border: '1px solid red', padding: 4 }}>
      Unknown: {$component}
    </div>
  );
}

function MutguiComponent({ schema }: { schema: ComponentSchema }) {
  const conn = useConnection();
  const scope = useScope();

  // IME 状态
  const composingRef = useRef(false);
  const imeValueRef = useRef<string | null>(null);
  const [imeValue, setImeValue] = useState<string | null>(null);

  const Component = schema.$component ? resolve(schema.$component) : null;
  if (!Component) {
    return <UnknownComponent $component={schema.$component || '(none)'} />;
  }

  const props = processProps(schema, conn, scope);

  const hasTextInput =
    typeof props.value === 'string' && typeof props.onChange === 'function';
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

    if (imeValue !== null) {
      props.value = imeValue;
    }

    props.onChange = (...args: unknown[]) => {
      const e = args[0] as any;
      const val: string = e?.target?.value ?? String(e ?? '');

      if (composingRef.current) {
        imeValueRef.current = val;
        setImeValue(val);
        return;
      }

      origOnChange(...args);
    };

    const componentId = schema.$id ?? '';

    return (
      <div
        style={{ display: 'contents' }}
        onCompositionStart={() => {
          composingRef.current = true;
        }}
        onCompositionEnd={(e) => {
          composingRef.current = false;
          const input = e.target as HTMLInputElement;
          const finalVal = input?.value ?? imeValueRef.current ?? '';
          imeValueRef.current = null;
          setImeValue(finalVal);

          if (componentId) {
            const spec = (schema as Record<string, unknown>).onChange;
            if (
              spec &&
              typeof spec === 'object' &&
              '$' in (spec as Record<string, unknown>)
            ) {
              const extract = (
                (spec as Record<string, unknown>).extract || {}
              ) as Record<string, string>;
              const data: Record<string, unknown> = {};
              for (const key of Object.keys(extract)) {
                data[key] = finalVal;
              }
              conn.send(
                JSON.stringify({
                  source: [...scope, componentId],
                  event: 'onChange',
                  data,
                }),
              );
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

// ---------------------------------------------------------------------------
// processProps — 处理 props
// ---------------------------------------------------------------------------

function processProps(
  schema: ComponentSchema,
  conn: MutguiConnection,
  scope: ViewPath,
): Record<string, unknown> {
  const props: Record<string, unknown> = {};
  const nodeId = schema.$id ?? '';

  for (const [key, val] of Object.entries(schema)) {
    // 框架键：不透传
    if (key === '$component' || key === '$id' || key === '$view') continue;

    if (key === '$children' && Array.isArray(val)) {
      // $children → 递归渲染为 React children
      props['children'] = renderTree(val as ComponentSchema[]);
    } else if (
      val != null &&
      typeof val === 'object' &&
      !Array.isArray(val) &&
      '$' in (val as Record<string, unknown>)
    ) {
      // $ 标签 → 生成事件处理函数
      props[key] = createHandler(
        val as Record<string, unknown>,
        scope,
        nodeId,
        key,
        conn,
      );
    } else {
      props[key] = val;
    }
  }

  return props;
}

// ---------------------------------------------------------------------------
// createHandler — 从 $ 标签生成事件转发函数
// ---------------------------------------------------------------------------

function createHandler(
  spec: Record<string, unknown>,
  scope: ViewPath,
  componentId: string | number,
  eventName: string,
  conn: MutguiConnection,
) {
  const extract = (spec.extract || {}) as Record<string, string>;
  const source = [...scope, componentId];
  return (...args: unknown[]) => {
    const data: Record<string, unknown> = {};
    for (const [key, path] of Object.entries(extract)) {
      data[key] = resolvePath(args, path);
    }
    conn.send(JSON.stringify({ source, event: eventName, data }));
  };
}
