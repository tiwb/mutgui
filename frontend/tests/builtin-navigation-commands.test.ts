import { describe, expect, test, vi } from 'vitest';

import {
  normalizeHashUrl,
  runHistoryCommand,
  runRedirectCommand,
  runReloadCommand,
  runSetHashCommand,
} from '../src/core/navigation';

describe('builtin navigation commands', () => {
  test('redirect 默认走 location.assign', () => {
    const runtime = {
      assign: vi.fn(),
      replace: vi.fn(),
      go: vi.fn(),
      reload: vi.fn(),
      pushState: vi.fn(),
      replaceState: vi.fn(),
    };

    runRedirectCommand({ url: '/next' }, runtime);

    expect(runtime.assign).toHaveBeenCalledWith('/next');
    expect(runtime.replace).not.toHaveBeenCalled();
  });

  test('redirect replace 模式走 location.replace', () => {
    const runtime = {
      assign: vi.fn(),
      replace: vi.fn(),
      go: vi.fn(),
      reload: vi.fn(),
      pushState: vi.fn(),
      replaceState: vi.fn(),
    };

    runRedirectCommand({ url: '/replaced', replace: true }, runtime);

    expect(runtime.replace).toHaveBeenCalledWith('/replaced');
    expect(runtime.assign).not.toHaveBeenCalled();
  });

  test('history 命令映射到 history.go', () => {
    const runtime = {
      assign: vi.fn(),
      replace: vi.fn(),
      go: vi.fn(),
      reload: vi.fn(),
      pushState: vi.fn(),
      replaceState: vi.fn(),
    };

    runHistoryCommand({ delta: -1 }, runtime);

    expect(runtime.go).toHaveBeenCalledWith(-1);
  });

  test('reload 命令映射到 location.reload', () => {
    const runtime = {
      assign: vi.fn(),
      replace: vi.fn(),
      go: vi.fn(),
      reload: vi.fn(),
      pushState: vi.fn(),
      replaceState: vi.fn(),
    };

    runReloadCommand(runtime);

    expect(runtime.reload).toHaveBeenCalled();
  });
});

describe('setHash command', () => {
  function makeRuntime() {
    return {
      assign: vi.fn(),
      replace: vi.fn(),
      go: vi.fn(),
      reload: vi.fn(),
      pushState: vi.fn(),
      replaceState: vi.fn(),
    };
  }

  test('默认走 history.pushState', () => {
    const runtime = makeRuntime();
    runSetHashCommand({ hash: '#/foo' }, runtime);
    expect(runtime.pushState).toHaveBeenCalledTimes(1);
    expect(runtime.replaceState).not.toHaveBeenCalled();
  });

  test('replace 模式走 history.replaceState', () => {
    const runtime = makeRuntime();
    runSetHashCommand({ hash: '#/foo', replace: true }, runtime);
    expect(runtime.replaceState).toHaveBeenCalledTimes(1);
    expect(runtime.pushState).not.toHaveBeenCalled();
  });

  test('裸串自动补 # 前缀', () => {
    const runtime = makeRuntime();
    runSetHashCommand({ hash: 'settings' }, runtime);
    const url = runtime.pushState.mock.calls[0][0] as string;
    expect(url.endsWith('#settings')).toBe(true);
  });

  test('已带 # 前缀保持原样', () => {
    const runtime = makeRuntime();
    runSetHashCommand({ hash: '#/foo/bar' }, runtime);
    const url = runtime.pushState.mock.calls[0][0] as string;
    expect(url.endsWith('#/foo/bar')).toBe(true);
  });

  test('空串清空 hash', () => {
    const runtime = makeRuntime();
    runSetHashCommand({ hash: '' }, runtime);
    const url = runtime.pushState.mock.calls[0][0] as string;
    expect(url.includes('#')).toBe(false);
  });

  test('永远不动 pathname / search', () => {
    // 显式传入 LocationBase 模拟浏览器上下文，验证输出始终以 base 开头。
    const loc = { pathname: '/app/test', search: '?x=1' };
    const base = loc.pathname + loc.search;
    expect(normalizeHashUrl('#/foo', loc).startsWith(base)).toBe(true);
    expect(normalizeHashUrl('settings', loc).startsWith(base)).toBe(true);
    expect(normalizeHashUrl('', loc)).toBe(base);
  });

  test('含 ? 假 query 的 hash 整体当作 hash 处理', () => {
    // "#/foo?bar=1" 是 hash 内部内容，整段保留，不能被识别成 query。
    const runtime = makeRuntime();
    runSetHashCommand({ hash: '#/foo?bar=1' }, runtime);
    const url = runtime.pushState.mock.calls[0][0] as string;
    expect(url.endsWith('#/foo?bar=1')).toBe(true);
  });
});
