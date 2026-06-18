import { describe, expect, test } from 'vitest';

import {
  calculateScrollAnchor,
  calculateVirtualLayout,
  calculateViewportRange,
  getEstimatedItemHeight,
  resolveFollowState,
  resolveFollowStateOnScroll,
  resolveFollowStateOnUserScroll,
  resolveScrollCause,
  shouldAutoRefreshViewport,
  FOLLOW_THRESHOLD_PX,
} from '../src/components/virtual-list';

describe('virtual list layout helpers', () => {
  test('已测量高度参与 offset 与总高度计算，未知项回退到自适应估算', () => {
    const indexToId = new Map<number, string>([
      [0, 'a'],
      [1, 'b'],
      [2, 'c'],
      [3, 'd'],
      [4, 'e'],
    ]);
    const heightMap = new Map<string, number>([
      ['a', 40],
      ['b', 60],
      ['d', 20],
      ['stale', 999],
    ]);

    const layout = calculateVirtualLayout({
      itemCount: 5,
      viewportStart: 1,
      visibleItemIds: ['b', 'c'],
      indexToId,
      heightMap,
      estimatedItemHeight: 40,
    });
    const viewportRange = calculateViewportRange({
      itemCount: 5,
      scrollTop: 45,
      clientHeight: 70,
      overscan: 1,
      viewportStart: 1,
      visibleItemIds: ['b', 'c'],
      indexToId,
      heightMap,
      estimatedItemHeight: 40,
    });

    expect(layout.offsetTop).toBe(40);
    expect(layout.totalHeight).toBe(200);
    expect(viewportRange).toEqual({ start: 0, end: 4 });
  });

  test('超高 item 仍会被视口相交判定命中', () => {
    const indexToId = new Map<number, string>([[0, 'huge']]);
    const heightMap = new Map<string, number>([['huge', 300]]);

    const anchor = calculateScrollAnchor({
      itemCount: 1,
      scrollTop: 120,
      viewportStart: 0,
      visibleItemIds: ['huge'],
      indexToId,
      heightMap,
      estimatedItemHeight: 300,
    });
    const viewportRange = calculateViewportRange({
      itemCount: 1,
      scrollTop: 120,
      clientHeight: 100,
      overscan: 0,
      viewportStart: 0,
      visibleItemIds: ['huge'],
      indexToId,
      heightMap,
      estimatedItemHeight: 300,
    });

    expect(anchor).toEqual({ index: 0, offsetWithinItem: 120 });
    expect(viewportRange).toEqual({ start: 0, end: 1 });
  });

  test('测量均值优先于 bootstrap 估算高度', () => {
    expect(getEstimatedItemHeight(0, 0, 32)).toBe(32);
    expect(getEstimatedItemHeight(180, 3, 32)).toBe(60);
  });

  test('stick-to-bottom 跟随状态按距底阈值切换', () => {
    expect(resolveFollowState({
      scrollTop: 268,
      clientHeight: 100,
      scrollHeight: 400,
    })).toBe('FOLLOWING');

    expect(resolveFollowState({
      scrollTop: 200,
      clientHeight: 100,
      scrollHeight: 400,
      threshold: FOLLOW_THRESHOLD_PX,
    })).toBe('DETACHED');
  });

  test('用户向上滚动时立即切到 DETACHED，不等阈值耗尽', () => {
    expect(resolveFollowStateOnUserScroll({
      previousState: 'FOLLOWING',
      previousScrollTop: 900,
      currentScrollTop: 880,
      clientHeight: 100,
      scrollHeight: 1000,
    })).toBe('DETACHED');

    expect(resolveFollowStateOnUserScroll({
      previousState: 'DETACHED',
      previousScrollTop: 880,
      currentScrollTop: 900,
      clientHeight: 100,
      scrollHeight: 1000,
    })).toBe('FOLLOWING');
  });

  test('显式用户意图才会把 scroll 视为 USER', () => {
    expect(resolveScrollCause({
      isProgrammaticScroll: false,
      hasPendingUserIntent: true,
      isPointerDragging: false,
      isUserScrolling: false,
    })).toBe('USER');

    expect(resolveScrollCause({
      isProgrammaticScroll: false,
      hasPendingUserIntent: false,
      isPointerDragging: true,
      isUserScrolling: false,
    })).toBe('USER');

    expect(resolveScrollCause({
      isProgrammaticScroll: false,
      hasPendingUserIntent: false,
      isPointerDragging: false,
      isUserScrolling: true,
    })).toBe('USER');

    expect(resolveScrollCause({
      isProgrammaticScroll: false,
      hasPendingUserIntent: false,
      isPointerDragging: false,
      isUserScrolling: false,
    })).toBe('LAYOUT_OR_PROGRAMMATIC');

    expect(resolveScrollCause({
      isProgrammaticScroll: true,
      hasPendingUserIntent: true,
      isPointerDragging: true,
      isUserScrolling: true,
    })).toBe('LAYOUT_OR_PROGRAMMATIC');
  });

  test('layout clamp 产生的 scroll 不会把 FOLLOWING 污染成 DETACHED', () => {
    expect(resolveFollowStateOnScroll({
      cause: 'LAYOUT_OR_PROGRAMMATIC',
      previousState: 'FOLLOWING',
      previousScrollTop: 1226,
      currentScrollTop: 1026,
      clientHeight: 560,
      scrollHeight: 1586,
    })).toBe('FOLLOWING');
  });

  test('layout/programmatic scroll 回到底部时会收敛回 FOLLOWING', () => {
    expect(resolveFollowStateOnScroll({
      cause: 'LAYOUT_OR_PROGRAMMATIC',
      previousState: 'DETACHED',
      previousScrollTop: 880,
      currentScrollTop: 900,
      clientHeight: 100,
      scrollHeight: 1000,
    })).toBe('FOLLOWING');
  });

  test('贴底聊天场景在 DETACHED 时不自动回推 viewport', () => {
    expect(shouldAutoRefreshViewport({
      stickToBottom: true,
      followState: 'DETACHED',
    })).toBe(false);

    expect(shouldAutoRefreshViewport({
      stickToBottom: true,
      followState: 'FOLLOWING',
    })).toBe(true);

    expect(shouldAutoRefreshViewport({
      stickToBottom: false,
      followState: 'DETACHED',
    })).toBe(true);
  });
});
