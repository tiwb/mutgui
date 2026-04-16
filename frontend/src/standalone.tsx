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
import { MutguiRenderer } from './renderer';
import type { ComponentSchema, WsLike } from './renderer';

registerAntd();

function App({ wsUrl }: { wsUrl: string }) {
  const [tree, setTree] = useState<ComponentSchema[]>([]);
  const [status, setStatus] = useState('Connecting...');
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => setStatus('Connected');
    ws.onclose = () => setStatus('Disconnected');
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'render') setTree(msg.tree);
    };
    return () => ws.close();
  }, [wsUrl]);

  const wsLike: WsLike = {
    send: (data: string) => wsRef.current?.send(data),
  };

  return (
    <>
      <div style={{ color: '#999', fontSize: 12, marginBottom: 16 }}>{status}</div>
      <MutguiRenderer tree={tree} ws={wsLike} />
    </>
  );
}

function mount(el: HTMLElement, wsUrl: string) {
  createRoot(el).render(<App wsUrl={wsUrl} />);
}

// 暴露到全局
(window as unknown as Record<string, unknown>).MutguiApp = { mount };
