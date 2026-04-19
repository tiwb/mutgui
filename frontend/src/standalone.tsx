/**
 * mutgui 独立入口 — 核心渲染器 + React，不含组件库。
 *
 * 用法（纯 HTML）：
 *   <div id="app"></div>
 *   <script src="/static/mutgui.js"></script>
 *   <script src="/static/libs/antd.js"></script>
 *   <script>MutguiApp.mount(document.getElementById('app'), `ws://${location.host}/ws`)</script>
 *
 * 组件库通过额外的 <script> 标签加载，加载后自动调用
 * MutguiApp.registerComponents() 注册。
 */
import React, { useState, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { createRoot } from 'react-dom/client';
import * as jsxRuntime from 'react/jsx-runtime';
import { registerComponents } from './registry';
import { MutguiView } from './renderer';
import { VirtualList } from './virtual-list';
import {
  ConnectionProvider,
  type MutguiConnection,
  type ViewPath,
  type RenderCallback,
} from './context';

// 注册框架内置组件
registerComponents({ VirtualList });

function createConnection(ws: WebSocket): MutguiConnection {
  const subs = new Map<string, RenderCallback>();
  const cache = new Map<string, unknown[]>();

  ws.addEventListener('message', (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'render') {
      const viewId: ViewPath = msg.viewId || [];
      const key = JSON.stringify(viewId);
      cache.set(key, msg.tree);
      const cb = subs.get(key);
      if (cb) cb(msg.tree);
    }
  });

  return {
    send: (data: string) => ws.send(data),
    subscribe: (viewId: ViewPath, callback: RenderCallback) => {
      const key = JSON.stringify(viewId);
      subs.set(key, callback);
      // 回放缓存：render 消息可能在 subscribe 之前到达
      const cached = cache.get(key);
      if (cached) callback(cached);
      return () => subs.delete(key);
    },
  };
}

function App({ wsUrl }: { wsUrl: string }) {
  const [status, setStatus] = useState('Connecting...');
  const connRef = useRef<MutguiConnection | null>(null);
  const [conn, setConn] = useState<MutguiConnection | null>(null);

  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    const connection = createConnection(ws);
    connRef.current = connection;
    ws.onopen = () => {
      setStatus('Connected');
      setConn(connection);
    };
    ws.onclose = () => setStatus('Disconnected');
    return () => ws.close();
  }, [wsUrl]);

  if (!conn) {
    return <div style={{ color: '#999', fontSize: 12 }}>{status}</div>;
  }

  return (
    <ConnectionProvider value={conn}>
      <div style={{ color: '#999', fontSize: 12, marginBottom: 16 }}>{status}</div>
      <MutguiView />
    </ConnectionProvider>
  );
}

function mount(el: HTMLElement, wsUrl: string) {
  createRoot(el).render(<App wsUrl={wsUrl} />);
}

// 暴露到全局：核心 API + React 供组件库 JS 共享
(window as unknown as Record<string, unknown>).MutguiApp = {
  mount,
  registerComponents,
  React,
  ReactDOM,
  jsxRuntime,
};
