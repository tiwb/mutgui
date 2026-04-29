import { describe, expect, test, vi } from 'vitest';

import {
  runHistoryCommand,
  runRedirectCommand,
  runReloadCommand,
} from '../src/core/navigation';

describe('builtin navigation commands', () => {
  test('redirect 默认走 location.assign', () => {
    const runtime = {
      assign: vi.fn(),
      replace: vi.fn(),
      go: vi.fn(),
      reload: vi.fn(),
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
    };

    runReloadCommand(runtime);

    expect(runtime.reload).toHaveBeenCalled();
  });
});
