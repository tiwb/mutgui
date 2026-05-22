interface RuntimeManifestEntry {
  name: string;
  kind: 'lib' | 'plugin';
}

interface RuntimeManifest {
  importMap: Record<string, string>;
  css: string[];
  entries: RuntimeManifestEntry[];
}

type MutguiPlugin = (ctx: unknown) => void;
interface RuntimeConnection {
  handleMessage(message: unknown): void;
}

interface CoreModule {
  createConnection(sendRaw: (data: string) => void): RuntimeConnection;
  mountWithConnection(el: HTMLElement, connection: RuntimeConnection, plugins?: MutguiPlugin[]): void;
  mount(el: HTMLElement, wsUrl: string, plugins?: MutguiPlugin[]): void;
}

interface RuntimeCssMessage {
  type: 'runtime.css';
  href: string;
}

interface RuntimeImportMessage {
  type: 'runtime.import';
  module: string;
}

interface RuntimeInstallMessage {
  type: 'runtime.install';
  module: string;
}

interface RuntimeMountMessage {
  type: 'runtime.mount';
}

type RuntimeMessage =
  | RuntimeCssMessage
  | RuntimeImportMessage
  | RuntimeInstallMessage
  | RuntimeMountMessage
  | { type: string; [key: string]: unknown };

const importedModules = new Map<string, Promise<unknown>>();
const loadedCss = new Set<string>();

function readManifest(): RuntimeManifest {
  const el = document.getElementById('mutgui-manifest');
  if (!el?.textContent) {
    throw new Error('Missing #mutgui-manifest JSON script');
  }
  return JSON.parse(el.textContent) as RuntimeManifest;
}

function resolveWsUrl(raw: string | undefined): string {
  const value = raw?.trim();
  if (!value) {
    return buildWsUrl(location.pathname);
  }
  if (value.startsWith('ws://') || value.startsWith('wss://')) {
    return value;
  }
  return buildWsUrl(value);
}

function buildWsUrl(path: string): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${location.host}${path}`;
}

function ensureCss(href: string): void {
  if (loadedCss.has(href)) {
    return;
  }
  const existing = document.querySelector(`link[href="${href}"]`);
  if (existing) {
    loadedCss.add(href);
    return;
  }
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  document.head.appendChild(link);
  loadedCss.add(href);
}

function importModule(name: string): Promise<unknown> {
  let pending = importedModules.get(name);
  if (!pending) {
    pending = import(/* @vite-ignore */ name);
    importedModules.set(name, pending);
  }
  return pending;
}

function readPlugins(el: HTMLElement, table: Map<string, MutguiPlugin>): MutguiPlugin[] {
  const names = (el.dataset.plugins ?? '')
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean);
  return names.map((name) => {
    const plugin = table.get(name);
    if (!plugin) {
      throw new Error(`Unknown plugin requested by mount point: ${name}`);
    }
    return plugin;
  });
}

class RuntimeSession {
  private readonly plugins: MutguiPlugin[] = [];

  private readonly installed = new Set<string>();

  private connection: RuntimeConnection | null = null;

  private mounted = false;

  private chain: Promise<void> = Promise.resolve();

  constructor(
    private readonly el: HTMLElement,
    private readonly wsUrl: string,
    private readonly mountId: string,
  ) {}

  start(): void {
    const ws = new WebSocket(this.wsUrl);
    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({
        type: 'mount.attach',
        mountId: this.mountId,
        protocol: 1,
        client: { hash: window.location.hash },
      }));
    });
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data) as RuntimeMessage;
      this.chain = this.chain.then(() => this.handleMessage(ws, message));
      this.chain.catch((error: unknown) => this.fail(error));
    });
  }

  private async handleMessage(ws: WebSocket, message: RuntimeMessage): Promise<void> {
    switch (message.type) {
      case 'runtime.css': {
        const { href } = message as RuntimeCssMessage;
        ensureCss(href);
        return;
      }
      case 'runtime.import': {
        const { module } = message as RuntimeImportMessage;
        await importModule(module);
        return;
      }
      case 'runtime.install': {
        const { module } = message as RuntimeInstallMessage;
        if (this.installed.has(module)) {
          return;
        }
        const mod = await importModule(module) as { default?: MutguiPlugin; install?: MutguiPlugin };
        const install = mod.install ?? mod.default;
        if (typeof install !== 'function') {
          throw new Error(`Runtime install module ${module} is missing a default/install function`);
        }
        this.plugins.push(install);
        this.installed.add(module);
        return;
      }
      case 'runtime.mount': {
        if (this.mounted) {
          return;
        }
        const core = await importModule('@mutgui/core') as CoreModule;
        this.connection = core.createConnection((data) => ws.send(data));
        core.mountWithConnection(this.el, this.connection, this.plugins);
        this.mounted = true;
        return;
      }
      default:
        if (!this.connection) {
          throw new Error(`Received ${message.type} before runtime.mount`);
        }
        this.connection.handleMessage(message);
    }
  }

  private fail(error: unknown): void {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    this.el.innerHTML = `<pre style="color:red">${message}</pre>`;
  }
}

async function startFromManifest(targets: HTMLElement[]): Promise<void> {
  const manifest = readManifest();
  for (const href of manifest.css) {
    ensureCss(href);
  }
  const pluginTable = new Map<string, MutguiPlugin>();
  for (const entry of manifest.entries) {
    const mod = await importModule(entry.name) as { default?: MutguiPlugin };
    if (entry.kind === 'plugin') {
      pluginTable.set(entry.name, mod.default as MutguiPlugin);
    }
  }

  const core = await importModule('@mutgui/core') as CoreModule;
  for (const el of targets) {
    core.mount(el, resolveWsUrl(el.dataset.wsUrl), readPlugins(el, pluginTable));
  }
}

function startFromRuntimeStream(targets: HTMLElement[]): void {
  if (targets.length !== 1) {
    throw new Error('Runtime stream mode currently expects exactly one [data-mutgui-app] target');
  }
  const el = targets[0];
  const mountId = el.id || 'mutgui-root';
  new RuntimeSession(el, resolveWsUrl(el.dataset.wsUrl), mountId).start();
}

async function start(): Promise<void> {
  const targets = Array.from(document.querySelectorAll<HTMLElement>('[data-mutgui-app]'));
  if (targets.length === 0) {
    throw new Error('No <div data-mutgui-app> found on page');
  }

  if (document.getElementById('mutgui-manifest')) {
    await startFromManifest(targets);
    return;
  }

  startFromRuntimeStream(targets);
}

start().catch((err: unknown) => {
  const message = err instanceof Error ? err.stack ?? err.message : String(err);
  document.body.innerHTML = `<pre style="color:red">${message}</pre>`;
});
