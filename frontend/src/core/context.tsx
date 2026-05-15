/**
 * mutgui 框架 Context — Scope（View 路径）和 Connection（消息收发）。
 */
import { createContext, useContext } from 'react';

// ---------------------------------------------------------------------------
// Scope — 跟踪当前 View 的路径数组
// ---------------------------------------------------------------------------

export type ViewPath = (string | number)[];

const ScopeContext = createContext<ViewPath>([]);
export const ScopeProvider = ScopeContext.Provider;
export function useScope(): ViewPath {
  return useContext(ScopeContext);
}

// ---------------------------------------------------------------------------
// Connection — 消息收发接口
// ---------------------------------------------------------------------------

export type RenderCallback = (tree: unknown[]) => void;

export interface MutguiConnection {
  send(data: string): void;
  subscribe(viewId: ViewPath, callback: RenderCallback): () => void;
  /** 可选：连接销毁时调用，用于解绑全局事件监听器。 */
  teardown?(): void;
}

const ConnectionContext = createContext<MutguiConnection | null>(null);
export const ConnectionProvider = ConnectionContext.Provider;

export function useConnection(): MutguiConnection {
  const conn = useContext(ConnectionContext);
  if (!conn) throw new Error('MutguiConnection not provided');
  return conn;
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

export function arrayEquals(a: ViewPath, b: ViewPath): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}
