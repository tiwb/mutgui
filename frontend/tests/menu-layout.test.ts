import { describe, expect, test } from 'vitest';

import {
  computeMenuLayout,
  recomputePosition,
  resolveAnchor,
  type Placement,
} from '../src/components/menu-layout';

function makeRect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON() {
      return {};
    },
  } as DOMRect;
}

describe('menu layout helpers', () => {
  test('11 种 placement 在宽松视口下遵循 point + menuAlign 公式', () => {
    const rect = makeRect(100, 80, 40, 20);
    const menuSize = { width: 60, height: 30 };
    const viewport = { width: 500, height: 400 };
    const cases: Array<[Placement, { left: number; top: number }]> = [
      ['cursor', { left: 200, top: 150 }],
      ['top-start', { left: 100, top: 50 }],
      ['top-center', { left: 90, top: 50 }],
      ['top-end', { left: 80, top: 50 }],
      ['bottom-start', { left: 100, top: 100 }],
      ['bottom-center', { left: 90, top: 100 }],
      ['bottom-end', { left: 80, top: 100 }],
      ['left-start', { left: 40, top: 80 }],
      ['left-end', { left: 40, top: 70 }],
      ['right-start', { left: 140, top: 80 }],
      ['right-end', { left: 140, top: 70 }],
    ];

    for (const [placement, expected] of cases) {
      const result = computeMenuLayout({
        anchor: resolveAnchor(
          placement,
          placement === 'cursor' ? undefined : rect,
          placement === 'cursor' ? { x: 200, y: 150 } : undefined,
        ),
        menuSize,
        viewport,
      });
      expect({ left: result.left, top: result.top }).toEqual(expected);
    }
  });

  test('主轴溢出时翻到对侧', () => {
    const rect = makeRect(80, 180, 40, 20);
    const result = computeMenuLayout({
      anchor: resolveAnchor('bottom-start', rect, undefined),
      menuSize: { width: 80, height: 60 },
      viewport: { width: 220, height: 220 },
    });

    expect(result.left).toBe(80);
    expect(result.top).toBe(120);
    expect(result.effectiveAnchor.menuAlign.y).toBe('end');
  });

  test('cursor 模式按两轴独立 flip', () => {
    const result = computeMenuLayout({
      anchor: resolveAnchor('cursor', undefined, { x: 190, y: 190 }),
      menuSize: { width: 50, height: 50 },
      viewport: { width: 200, height: 200 },
    });

    expect(result.left).toBe(140);
    expect(result.top).toBe(140);
    expect(result.effectiveAnchor.menuAlign).toEqual({ x: 'end', y: 'end' });
  });

  test('交叉轴溢出时仅沿交叉轴贴边 shift', () => {
    const rect = makeRect(0, 120, 20, 20);
    const result = computeMenuLayout({
      anchor: resolveAnchor('top-center', rect, undefined),
      menuSize: { width: 100, height: 40 },
      viewport: { width: 150, height: 220 },
    });

    expect(result.left).toBe(4);
    expect(result.top).toBe(80);
  });

  test('视口过小时返回 maxHeight / maxWidth 约束', () => {
    const result = computeMenuLayout({
      anchor: resolveAnchor('cursor', undefined, { x: 100, y: 80 }),
      menuSize: { width: 400, height: 300 },
      viewport: { width: 200, height: 160 },
    });

    expect(result.maxWidth).toBe(192);
    expect(result.maxHeight).toBe(152);
    expect(result.left).toBe(4);
    expect(result.top).toBe(4);
  });

  test('固定 anchor 时 end 角随尺寸变化保持不动', () => {
    const anchor = resolveAnchor('top-end', makeRect(120, 160, 40, 20), undefined);
    const viewport = { width: 600, height: 400 };
    const small = recomputePosition(anchor, { width: 60, height: 30 }, viewport);
    const large = recomputePosition(anchor, { width: 100, height: 70 }, viewport);

    expect(small.left + 60).toBe(large.left + 100);
    expect(small.top + 30).toBe(large.top + 70);
  });

  test('recomputePosition 不重新 flip，只做最小 shift 兜底', () => {
    const anchor = resolveAnchor('bottom-start', makeRect(100, 120, 40, 20), undefined);
    const result = recomputePosition(
      anchor,
      { width: 80, height: 70 },
      { width: 220, height: 160 },
    );

    expect(result.left).toBe(100);
    expect(result.top).toBe(86);
  });
});
