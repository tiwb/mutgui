import { describe, expect, test, vi } from 'vitest';

import { registerCommands, resolveCommand } from '../src/core/commands';

describe('command registry', () => {
  test('后注册的命名空间命令优先级更高', () => {
    const first = vi.fn();
    const second = vi.fn();

    registerCommands({ __name__: 'testcmd', ping: first });
    registerCommands({ __name__: 'testcmd', ping: second });

    const resolved = resolveCommand('testcmd.ping');
    expect(resolved).toBe(second);
  });

  test('单段名字只匹配无命名空间 source', () => {
    const plain = vi.fn();
    const namespaced = vi.fn();

    registerCommands({ __name__: 'singlecmd', ping: namespaced });
    registerCommands({ pong: plain });

    expect(resolveCommand('pong')).toBe(plain);
    expect(resolveCommand('ping')).toBeNull();
  });

  test('命令调用时接收 args 与 view scope', () => {
    const handler = vi.fn();

    registerCommands({ __name__: 'ctxcmd', run: handler });
    const resolved = resolveCommand('ctxcmd.run');

    expect(resolved).not.toBeNull();
    resolved?.({ value: 42 }, { viewId: ['child', 1] });

    expect(handler).toHaveBeenCalledWith(
      { value: 42 },
      { viewId: ['child', 1] },
    );
  });
});
