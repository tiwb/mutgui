/**
 * mutgui 独立入口 — 核心渲染器 + React，不含组件库。
 *
 * 用法（纯 HTML）：
 *   <div id="app"></div>
 *   <script src="/static/mutgui.js"></script>
 *   <script src="/static/mutgui-antd.js"></script>
 *   <script src="/static/mutgui-theme-dark.js"></script>  <!-- 可选 plugin -->
 *   <script>
 *     MutguiApp.mount(
 *       document.getElementById('app'),
 *       `ws://${location.host}/ws`,
 *       [MutguiThemeDark]   // 可选 plugin 数组
 *     )
 *   </script>
 *
 * 组件库通过额外的 <script> 标签加载，加载后自动调用
 * MutguiApp.registerComponents()/registerCommands() 注册。
 *
 * Plugin 协议:
 *   plugin = (ctx) => void
 *   ctx.addCss(css)         注入 <style> 到 document.head
 *   ctx.addBodyClass(name)  给 document.body 加 class
 *   ctx.wrapRoot(wrap)      根渲染树外包一层 React(Provider 等)
 */
import React, { useState, useEffect, useRef, type ReactNode } from 'react';
import ReactDOM from 'react-dom';
import { createRoot } from 'react-dom/client';
import * as jsxRuntime from 'react/jsx-runtime';
import { registerComponents } from './core/registry';
import { registerCommands, resolveCommand } from './core/commands';
import { MutguiView } from './core/renderer';
import { VirtualList } from './components/virtual-list';
import { DockPanel, DockPanelSplit, DockPanelTabSet } from './components/dock-panel';
import { Menu, MenuItem, MenuDivider } from './components/menu';
import {
  ConnectionProvider,
  type MutguiConnection,
  type ViewPath,
  type RenderCallback,
} from './core/context';
// 内联读取 CSS 源码（Vite ?inline query），在 mount 时注入 <style>
// 确保 standalone IIFE 产物自带样式，用户零配置
import mutguiStyles from './index.css?inline';

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected || typeof document === 'undefined') return;
  stylesInjected = true;
  const style = document.createElement('style');
  style.setAttribute('data-mutgui', 'styles');
  style.textContent = mutguiStyles;
  document.head.appendChild(style);
}

// 注册框架内置组件（命名空间源，$component 必须写成 "mutgui.XXX"）
registerComponents({
  __name__: 'mutgui',
  DockPanel,
  'DockPanel.Split': DockPanelSplit,
  'DockPanel.TabSet': DockPanelTabSet,
  Menu,
  'Menu.Item': MenuItem,
  'Menu.Divider': MenuDivider,
  VirtualList,
});

registerCommands({
  __name__: 'mutgui',
  redirect: ({ url, replace }: { url: string; replace?: boolean }) => {
    if (replace) {
      window.location.replace(url);
      return;
    }
    window.location.href = url;
  },
});

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
      return;
    }

    if (msg.type === 'command') {
      const viewId: ViewPath = msg.viewId || [];
      const cmd = resolveCommand(msg.name);
      if (!cmd) {
        console.warn(`[mutgui] Unknown command: ${String(msg.name)}`, msg);
        return;
      }
      cmd((msg.args || {}) as Record<string, unknown>, { viewId });
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

interface AppProps {
  wsUrl: string;
  onStatus?: (status: string) => void;
}

function App({ wsUrl, onStatus }: AppProps) {
  const [status, setStatus] = useState('Connecting...');
  const connRef = useRef<MutguiConnection | null>(null);
  const [conn, setConn] = useState<MutguiConnection | null>(null);

  const updateStatus = (s: string) => {
    setStatus(s);
    onStatus?.(s);
  };

  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    const connection = createConnection(ws);
    connRef.current = connection;
    ws.onopen = () => {
      updateStatus('Connected');
      setConn(connection);
    };
    ws.onclose = () => updateStatus('Disconnected');
    return () => ws.close();
  }, [wsUrl]);

  if (!conn) {
    return <div style={{ color: 'var(--mutgui-text-dim)', fontSize: 12 }}>{status}</div>;
  }

  return (
    <ConnectionProvider value={conn}>
      <MutguiView />
    </ConnectionProvider>
  );
}

// Plugin 协议类型
export type RootWrapper = (children: ReactNode) => ReactNode;
export interface PluginContext {
  addCss(css: string): void;
  addBodyClass(className: string): void;
  wrapRoot(wrap: RootWrapper): void;
}
export type MutguiPlugin = (ctx: PluginContext) => void;

function applyPlugins(plugins: MutguiPlugin[]): RootWrapper[] {
  const wrappers: RootWrapper[] = [];
  const ctx: PluginContext = {
    addCss(css) {
      const style = document.createElement('style');
      style.setAttribute('data-mutgui-plugin', '');
      style.textContent = css;
      document.head.appendChild(style);
    },
    addBodyClass(name) {
      document.body.classList.add(name);
    },
    wrapRoot(wrap) {
      wrappers.push(wrap);
    },
  };
  for (const p of plugins) p(ctx);
  return wrappers;
}

function mount(
  el: HTMLElement,
  wsUrl: string,
  plugins?: MutguiPlugin[],
  options?: { onStatus?: (status: string) => void },
) {
  injectStyles();
  const wrappers = applyPlugins(plugins ?? []);
  let tree: ReactNode = <App wsUrl={wsUrl} onStatus={options?.onStatus} />;
  // 数组中靠前的 plugin 在外层,靠后的在内层
  for (let i = wrappers.length - 1; i >= 0; i--) {
    tree = wrappers[i](tree);
  }
  createRoot(el).render(tree);
}

// 暴露到全局：核心 API + React 供组件库 JS 共享
(window as unknown as Record<string, unknown>).MutguiApp = {
  mount,
  registerComponents,
  registerCommands,
  React,
  ReactDOM,
  jsxRuntime,
};
