export interface NavigationRuntime {
  assign(url: string): void;
  replace(url: string): void;
  go(delta: number): void;
  reload(): void;
  pushState(url: string): void;
  replaceState(url: string): void;
}

const browserNavigation: NavigationRuntime = {
  assign(url) {
    window.location.assign(url);
  },
  replace(url) {
    window.location.replace(url);
  },
  go(delta) {
    window.history.go(delta);
  },
  reload() {
    window.location.reload();
  },
  pushState(url) {
    window.history.pushState(null, '', url);
  },
  replaceState(url) {
    window.history.replaceState(null, '', url);
  },
};

export function runRedirectCommand(
  { url, replace }: { url: string; replace?: boolean },
  runtime: NavigationRuntime = browserNavigation,
): void {
  if (replace) {
    runtime.replace(url);
    return;
  }
  runtime.assign(url);
}

export function runHistoryCommand(
  { delta }: { delta: number },
  runtime: NavigationRuntime = browserNavigation,
): void {
  runtime.go(delta);
}

export function runReloadCommand(runtime: NavigationRuntime = browserNavigation): void {
  runtime.reload();
}

/**
 * 把用户传入的 hash 字符串规范化为「pathname + search + #...」完整 URL。
 *
 * 直接 pushState(hash) 会被当成相对 URL 解析（例如 "settings" 会替换 pathname 末段），
 * 必须显式拼成绝对 URL 才能保证只动 hash、不动 pathname/search。
 */
export interface LocationBase {
  pathname: string;
  search: string;
}

export function normalizeHashUrl(hash: string, loc?: LocationBase): string {
  const source: LocationBase = loc ?? (typeof window !== 'undefined'
    ? window.location
    : { pathname: '', search: '' });
  const base = source.pathname + source.search;
  if (hash === '') return base;                 // 清空 hash，导航到 pathname
  if (hash.startsWith('#')) return base + hash; // 已带 # 前缀
  return base + '#' + hash;                     // 自动补 #
}

export function runSetHashCommand(
  { hash, replace }: { hash: string; replace?: boolean },
  runtime: NavigationRuntime = browserNavigation,
): void {
  const url = normalizeHashUrl(hash);
  if (replace) {
    runtime.replaceState(url);
    return;
  }
  runtime.pushState(url);
}
