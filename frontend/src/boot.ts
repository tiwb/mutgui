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
type MountFn = (el: HTMLElement, wsUrl: string, plugins?: MutguiPlugin[]) => void;

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

async function start(): Promise<void> {
  const targets = Array.from(document.querySelectorAll<HTMLElement>('[data-mutgui-app]'));
  if (targets.length === 0) {
    throw new Error('No <div data-mutgui-app> found on page');
  }

  const manifest = readManifest();

  for (const href of manifest.css) {
    if (document.querySelector(`link[href="${href}"]`)) {
      continue;
    }
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  }

  const pluginTable = new Map<string, MutguiPlugin>();
  for (const entry of manifest.entries) {
    const mod = await import(/* @vite-ignore */ entry.name);
    if (entry.kind === 'plugin') {
      pluginTable.set(entry.name, mod.default as MutguiPlugin);
    }
  }

  const core = await import('@mutgui/core');
  const mount = core.mount as MountFn;
  for (const el of targets) {
    mount(el, resolveWsUrl(el.dataset.wsUrl), readPlugins(el, pluginTable));
  }
}

start().catch((err: unknown) => {
  const message = err instanceof Error ? err.stack ?? err.message : String(err);
  document.body.innerHTML = `<pre style="color:red">${message}</pre>`;
});
