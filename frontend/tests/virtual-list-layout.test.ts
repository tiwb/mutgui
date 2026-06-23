import { describe, expect, test } from 'vitest';

import { FOLLOW_THRESHOLD_PX } from '../src/components/virtual-list';

describe('FOLLOW_THRESHOLD_PX', () => {
  test('阈值常量存在且为正值', () => {
    expect(FOLLOW_THRESHOLD_PX).toBeGreaterThan(0);
  });
});
