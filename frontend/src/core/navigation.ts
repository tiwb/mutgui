export interface NavigationRuntime {
  assign(url: string): void;
  replace(url: string): void;
  go(delta: number): void;
  reload(): void;
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
