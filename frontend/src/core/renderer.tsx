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
import { Menu, isMenuViewId, createMenuTriggerHandler, takePendingMenuTrigger, type TriggerInfo } from '../components/menu';

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
  // tree state 语义：[] = 空树（初始或后端合法返回空），[...] = 正常内容。
  // readCache 保证永不返回 undefined，故无需 null 状态。
  const conn = useConnection();
  const parentScope = useScope();
  const [tree, setTree] = useState<ComponentSchema[]>(() => {
    const path: ViewPath = viewId !== undefined ? [...parentScope, viewId] : [];
    return conn.readCache(path) as ComponentSchema[];
  });

  // 菜单分支：看到 menu viewId 那一刻同步 take 走 pendingTrigger，
  // 避免 Menu mount 被 received gating 延后后被后续 trigger 覆盖
  // （特别是 hover 子菜单连续 onMouseEnter 场景）。
  const [initialTrigger] = useState<TriggerInfo | null>(() =>
    isMenuViewId(viewId) ? takePendingMenuTrigger() : null,
  );

  const fullPath = useMemo<ViewPath>(
    () => (viewId !== undefined ? [...parentScope, viewId] : []),
    [parentScope, viewId],
  );

  useEffect(() => {
    return conn.subscribe(fullPath, (newTree) => {
      setTree(newTree as ComponentSchema[]);
    });
  }, [conn, fullPath]);

  // 菜单 View — 用 Menu 容器包装并 portal 渲染
  // 首帧 tree 未到之前不挂载 Menu，避免在空 children 上跳 useLayoutEffect 布局。
  if (isMenuViewId(viewId)) {
    if (tree.length === 0) return null;
    return (
      <ScopeProvider value={fullPath}>
        <Menu
          menuId={String(viewId)}
          conn={conn}
          viewPath={fullPath}
          initialTrigger={initialTrigger}
        >
          {renderTree(tree)}
        </Menu>
      </ScopeProvider>
    );
  }

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

function MutguiComponent({ schema }: { schema: ComponentSchema }) {
  const conn = useConnection();
  const scope = useScope();

  // IME 状态
  const composingRef = useRef(false);
  const imeValueRef = useRef<string | null>(null);
  const [imeValue, setImeValue] = useState<string | null>(null);

  const resolved = schema.$component ? resolve(schema.$component) : null;
  if (!resolved) {
    conn.send(JSON.stringify({
      type: 'render.error',
      component: schema.$component,
      source: [...scope, schema.$id ?? ''],
    }));
    return null;
  }

  // resolve 返回字符串（原生 HTML 元素）或 React 组件引用
  const Component = resolved as any;

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
              '$handler' in (spec as Record<string, unknown>)
            ) {
              const handlerSpec = spec as Record<string, unknown>;
              const handlerId = handlerSpec.$handler as number;
              const argPaths = (handlerSpec.args || []) as string[];
              const kwargPaths = (handlerSpec.kwargs || {}) as Record<string, string>;
              const data: Record<string, unknown> = {};
              for (const k of Object.keys(kwargPaths)) {
                data[k] = finalVal;
              }
              if (argPaths.length > 0) {
                data.$args = argPaths.map(() => finalVal);
              }
              conn.send(
                JSON.stringify({
                  source: [...scope, componentId],
                  event: 'onChange',
                  handlerId,
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
    } else {
      props[key] = processValue(val, conn, scope, nodeId, key);
    }
  }

  return props;
}

function processValue(
  value: unknown,
  conn: MutguiConnection,
  scope: ViewPath,
  nodeId: string | number,
  eventName: string,
): unknown {
  if (Array.isArray(value)) {
    return value.map((item, index) =>
      processValue(item, conn, scope, nodeId, `${eventName}.${index}`),
    );
  }

  if (value != null && typeof value === 'object') {
    const record = value as Record<string, unknown>;

    if ('$handler' in record) {
      return createHandler(record, scope, nodeId, eventName, conn);
    }
    if ('$view' in record || '$component' in record) {
      return renderTree([record as ComponentSchema])[0];
    }

    const next: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(record)) {
      const childEvent = eventName ? `${eventName}.${key}` : key;
      if (key === '$children' && Array.isArray(inner)) {
        next['children'] = renderTree(inner as ComponentSchema[]);
      } else {
        next[key] = processValue(inner, conn, scope, nodeId, childEvent);
      }
    }
    return next;
  }

  return value;
}

// ---------------------------------------------------------------------------
// createHandler — 从 $handler 标签生成事件转发函数
// ---------------------------------------------------------------------------

function createHandler(
  spec: Record<string, unknown>,
  scope: ViewPath,
  componentId: string | number,
  eventName: string,
  conn: MutguiConnection,
) {
  const handlerId = spec.$handler as number;
  const argPaths = (spec.args || []) as string[];
  const kwargPaths = (spec.kwargs || {}) as Record<string, string>;

  // menu 标记 → 走菜单触发逻辑
  if (spec.menu) {
    return createMenuTriggerHandler(spec, scope, componentId, eventName, conn);
  }
  const source = [...scope, componentId];
  return (...args: unknown[]) => {
    const extractedArgs = argPaths.map(p => resolvePath(args, p));
    const extractedKwargs: Record<string, unknown> = {};
    for (const [k, path] of Object.entries(kwargPaths)) {
      extractedKwargs[k] = resolvePath(args, path);
    }
    const data: Record<string, unknown> = { ...extractedKwargs };
    if (extractedArgs.length > 0) {
      data.$args = extractedArgs;
    }
    conn.send(JSON.stringify({ source, event: eventName, handlerId, data }));
  };
}
