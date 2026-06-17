import { useEffect, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';

import './index.css';

import { registerComponents } from './core/registry';
import { registerCommands, resolveCommand } from './core/commands';
import { runHistoryCommand, runRedirectCommand, runReloadCommand, runSetHashCommand } from './core/navigation';
import { setupSystemEvents } from './core/system-events';
import { MutguiView } from './core/renderer';
import { VirtualList } from './components/virtual-list';
import { DockPanel, DockPanelSplit, DockPanelTabSet } from './components/dock-panel';
import { Menu, MenuDivider, MenuItem } from './components/menu';
import {
  Toolbar,
  ToolbarSection,
  ToolbarSpacer,
  ToolbarButton,
  ToolbarSplitButton,
  ToolbarDropdown,
  ToolbarDivider,
} from './components/toolbar';
import {
  ConnectionProvider,
  type MutguiConnection,
  type RenderCallback,
  type ViewPath,
} from './core/context';

registerComponents({
  __name__: 'mutgui',
  DockPanel,
  'DockPanel.Split': DockPanelSplit,
  'DockPanel.TabSet': DockPanelTabSet,
  Menu,
  'Menu.Item': MenuItem,
  'Menu.Divider': MenuDivider,
  Toolbar,
  'Toolbar.Section': ToolbarSection,
  'Toolbar.Spacer': ToolbarSpacer,
  'Toolbar.Button': ToolbarButton,
  'Toolbar.SplitButton': ToolbarSplitButton,
  'Toolbar.Dropdown': ToolbarDropdown,
  'Toolbar.Divider': ToolbarDivider,
  VirtualList,
});

registerCommands({
  __name__: 'mutgui',
  redirect: (args: { url: string; replace?: boolean }) => {
    runRedirectCommand(args);
  },
  history: (args: { delta: number }) => {
    runHistoryCommand(args);
  },
  reload: () => {
    runReloadCommand();
  },
  setHash: (args: { hash: string; replace?: boolean }) => {
    runSetHashCommand(args);
  },
});

type InboundMessage =
  | { type: 'render'; viewId?: ViewPath; tree: unknown[] }
  | { type: 'command'; viewId?: ViewPath; name: string; args?: Record<string, unknown> };

export interface RuntimeConnection extends MutguiConnection {
  handleMessage(message: unknown): void;
}

export function createConnection(sendRaw: (data: string) => void): RuntimeConnection {
  const subs = new Map<string, RenderCallback>();
  const cache = new Map<string, unknown[]>();
  const teardownSystemEvents = setupSystemEvents(sendRaw);

  const handleMessage = (message: unknown) => {
    const msg = message as Partial<InboundMessage>;
    if (msg.type === 'render') {
      const viewId: ViewPath = msg.viewId ?? [];
      const key = JSON.stringify(viewId);
      cache.set(key, msg.tree ?? []);
      const cb = subs.get(key);
      if (cb) cb(msg.tree ?? []);
      return;
    }

    if (msg.type === 'command') {
      const viewId: ViewPath = msg.viewId ?? [];
      const cmd = resolveCommand(msg.name ?? '');
      if (!cmd) {
        console.warn(`[mutgui] Unknown command: ${String(msg.name)}`, msg);
        return;
      }
      cmd((msg.args || {}) as Record<string, unknown>, { viewId });
    }
  };

  return {
    handleMessage,
    send: (data: string) => sendRaw(data),
    subscribe: (viewId: ViewPath, callback: RenderCallback) => {
      const key = JSON.stringify(viewId);
      subs.set(key, callback);
      const cached = cache.get(key);
      if (cached) callback(cached);
      return () => subs.delete(key);
    },
    teardown: () => {
      teardownSystemEvents();
    },
  };
}

interface AppProps {
  connection: MutguiConnection;
}

function App({ connection }: AppProps) {
  return (
    <ConnectionProvider value={connection}>
      <MutguiView />
    </ConnectionProvider>
  );
}

interface ConnectedAppProps {
  wsUrl: string;
  onStatus?: (status: string) => void;
}

function ConnectedApp({ wsUrl, onStatus }: ConnectedAppProps) {
  const [status, setStatus] = useState('Connecting...');
  const [conn, setConn] = useState<MutguiConnection | null>(null);

  const updateStatus = (s: string) => {
    setStatus(s);
    onStatus?.(s);
  };

  useEffect(() => {
    const ws = new WebSocket(wsUrl);
    const connection = createConnection((data) => ws.send(data));
    ws.addEventListener('message', (e) => {
      connection.handleMessage(JSON.parse(e.data));
    });
    ws.onopen = () => {
      updateStatus('Connected');
      setConn(connection);
    };
    ws.onclose = () => updateStatus('Disconnected');
    return () => {
      connection.teardown?.();
      ws.close();
    };
  }, [wsUrl]);

  if (!conn) {
    return <div style={{ color: 'var(--mutgui-text-dim)', fontSize: 12 }}>{status}</div>;
  }

  return <App connection={conn} />;
}

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
    addBodyClass(className) {
      document.body.classList.add(className);
    },
    wrapRoot(wrap) {
      wrappers.push(wrap);
    },
  };
  for (const plugin of plugins) plugin(ctx);
  return wrappers;
}

function wrapWithPlugins(children: ReactNode, plugins?: MutguiPlugin[]): ReactNode {
  const wrappers = applyPlugins(plugins ?? []);
  let tree = children;
  for (let i = wrappers.length - 1; i >= 0; i--) {
    tree = wrappers[i](tree);
  }
  return tree;
}

export function mountWithConnection(
  el: HTMLElement,
  connection: MutguiConnection,
  plugins?: MutguiPlugin[],
): void {
  createRoot(el).render(wrapWithPlugins(<App connection={connection} />, plugins));
}

export function mount(
  el: HTMLElement,
  wsUrl: string,
  plugins?: MutguiPlugin[],
  options?: { onStatus?: (status: string) => void },
): void {
  createRoot(el).render(wrapWithPlugins(
    <ConnectedApp wsUrl={wsUrl} onStatus={options?.onStatus} />,
    plugins,
  ));
}

export { registerComponents, registerNamespace, resolve } from './core/registry';
export type { NamespaceResolver } from './core/registry';
export { registerCommands, resolveCommand } from './core/commands';
export type { CommandContext, MutguiCommand, CommandSource } from './core/commands';
export { MutguiView, renderTree } from './core/renderer';
export type { ComponentSchema } from './core/renderer';
export {
  ConnectionProvider,
  ScopeProvider,
  useScope,
  useConnection,
  arrayEquals,
} from './core/context';
export type { ViewPath, MutguiConnection, RenderCallback } from './core/context';
export { resolvePath } from './core/resolve-path';
export { VirtualList } from './components/virtual-list';
export { DockPanel, DockPanelSplit, DockPanelTabSet } from './components/dock-panel';
export {
  Toolbar,
  ToolbarSection,
  ToolbarSpacer,
  ToolbarButton,
  ToolbarSplitButton,
  ToolbarDropdown,
  ToolbarDivider,
} from './components/toolbar';
