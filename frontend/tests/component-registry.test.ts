import { describe, expect, test } from 'vitest';

import { registerComponents, resolve } from '../src/core/registry';

describe('component registry', () => {
  test('支持 React object 形态组件（如 forwardRef / memo）', () => {
    const reactObjectComponent = {
      $$typeof: Symbol.for('react.forward_ref'),
      render: () => null,
    };

    registerComponents({
      __name__: 'antdtest',
      Button: reactObjectComponent,
    });

    expect(resolve('antdtest.Button')).toBe(reactObjectComponent);
  });

  test('未命中时返回 null（关闭 bare name fallback）', () => {
    expect(resolve('div')).toBeNull();
    expect(resolve('unknown.Component')).toBeNull();
  });
});
