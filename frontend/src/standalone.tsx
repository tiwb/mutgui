/**
 * mutgui 独立入口 — 全量打包，暴露 MutguiApp.mount()。
 *
 * 用法（纯 HTML）：
 *   <div id="app"></div>
 *   <script src="/static/mutgui.js"></script>
 *   <script>MutguiApp.mount(document.getElementById('app'), `ws://${location.host}/ws`)</script>
 */
import { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { registerAntd } from './antd';
import { MutguiView } from './renderer';
import {
  ConnectionProvider,
  type MutguiConnection,
  type ViewPath,
  type RenderCallback,
} from './context';

registerAntd();

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

// 暴露到全局
(window as unknown as Record<string, unknown>).MutguiApp = { mount };
