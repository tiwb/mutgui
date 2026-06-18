/**
 * VirtualList - 虚拟滚动列表组件。
 *
 * 后端控制可见 item 列表(通过 onViewport 事件),
 * 前端负责滚动容器、高度估算、viewport 计算和防抖。
 * children 由框架从 $children 渲染为 MutguiView 列表。
 */
import { useRef, useState, useCallback, useEffect, useLayoutEffect, useMemo, Children } from 'react';

const DEFAULT_ITEM_HEIGHT = 32;
const DEFAULT_OVERSCAN = 5;
const VIEWPORT_THROTTLE_MS = 50;
const USER_SCROLL_IDLE_MS = 100;
export const FOLLOW_THRESHOLD_PX = 32;
const USER_SCROLL_KEYS = new Set([
  'ArrowDown',
  'ArrowUp',
  'End',
  'Home',
  'PageDown',
  'PageUp',
  'Space',
  ' ',
 ]);

export type FollowState = 'FOLLOWING' | 'DETACHED';
export type ScrollCause = 'USER' | 'LAYOUT_OR_PROGRAMMATIC';

export interface FollowStateInput {
  previousState: FollowState;
  previousScrollTop: number;
  currentScrollTop: number;
  clientHeight: number;
  scrollHeight: number;
  threshold?: number;
}

export interface FollowStateOnScrollInput extends FollowStateInput {
  cause: ScrollCause;
}

export interface ScrollCauseInput {
  isProgrammaticScroll: boolean;
  hasPendingUserIntent: boolean;
  isPointerDragging: boolean;
  isUserScrolling: boolean;
}

export interface VirtualLayoutInput {
  itemCount: number;
  viewportStart: number;
  visibleItemIds: string[];
  indexToId: ReadonlyMap<number, string>;
  heightMap: ReadonlyMap<string, number>;
  estimatedItemHeight: number;
}

export interface ViewportRangeInput extends VirtualLayoutInput {
  scrollTop: number;
  clientHeight: number;
  overscan: number;
}

export interface ScrollAnchor {
  index: number;
  offsetWithinItem: number;
}

export interface VirtualLayout {
  totalHeight: number;
  offsetTop: number;
}

export interface ViewportRange {
  start: number;
  end: number;
}

function getItemIdAtIndex(
  index: number,
  viewportStart: number,
  visibleItemIds: string[],
  indexToId: ReadonlyMap<number, string>,
): string | null {
  const visibleOffset = index - viewportStart;
  if (visibleOffset >= 0 && visibleOffset < visibleItemIds.length) {
    return visibleItemIds[visibleOffset] ?? null;
  }
  return indexToId.get(index) ?? null;
}

export function getEstimatedItemHeight(
  measuredHeightSum: number,
  measuredCount: number,
  bootstrapEstimatedItemHeight: number,
): number {
  if (measuredCount <= 0) {
    return bootstrapEstimatedItemHeight;
  }
  return measuredHeightSum / measuredCount;
}

function getItemHeightAtIndex(
  index: number,
  estimatedItemHeight: number,
  viewportStart: number,
  visibleItemIds: string[],
  indexToId: ReadonlyMap<number, string>,
  heightMap: ReadonlyMap<string, number>,
): number {
  const itemId = getItemIdAtIndex(index, viewportStart, visibleItemIds, indexToId);
  if (!itemId) {
    return estimatedItemHeight;
  }
  return heightMap.get(itemId) ?? estimatedItemHeight;
}

export function calculateScrollAnchor(input: {
  itemCount: number;
  scrollTop: number;
  viewportStart: number;
  visibleItemIds: string[];
  indexToId: ReadonlyMap<number, string>;
  heightMap: ReadonlyMap<string, number>;
  estimatedItemHeight: number;
}): ScrollAnchor {
  if (input.itemCount <= 0) {
    return { index: 0, offsetWithinItem: 0 };
  }

  let offsetTop = 0;
  for (let index = 0; index < input.itemCount; index += 1) {
    const height = getItemHeightAtIndex(
      index,
      input.estimatedItemHeight,
      input.viewportStart,
      input.visibleItemIds,
      input.indexToId,
      input.heightMap,
    );
    if (input.scrollTop < offsetTop + height) {
      return {
        index,
        offsetWithinItem: Math.max(0, input.scrollTop - offsetTop),
      };
    }
    offsetTop += height;
  }

  const lastIndex = input.itemCount - 1;
  const lastHeight = getItemHeightAtIndex(
    lastIndex,
    input.estimatedItemHeight,
    input.viewportStart,
    input.visibleItemIds,
    input.indexToId,
    input.heightMap,
  );
  return {
    index: lastIndex,
    offsetWithinItem: Math.max(0, Math.min(lastHeight, input.scrollTop - (offsetTop - lastHeight))),
  };
}

export function calculateVirtualLayout(input: VirtualLayoutInput): VirtualLayout {
  let totalHeight = 0;
  for (let index = 0; index < input.itemCount; index += 1) {
    totalHeight += getItemHeightAtIndex(
      index,
      input.estimatedItemHeight,
      input.viewportStart,
      input.visibleItemIds,
      input.indexToId,
      input.heightMap,
    );
  }

  let offsetTop = 0;
  for (let index = 0; index < input.viewportStart; index += 1) {
    offsetTop += getItemHeightAtIndex(
      index,
      input.estimatedItemHeight,
      input.viewportStart,
      input.visibleItemIds,
      input.indexToId,
      input.heightMap,
    );
  }

  return {
    totalHeight,
    offsetTop,
  };
}

export function calculateViewportRange(input: ViewportRangeInput): ViewportRange {
  const anchor = calculateScrollAnchor({
    itemCount: input.itemCount,
    scrollTop: input.scrollTop,
    viewportStart: input.viewportStart,
    visibleItemIds: input.visibleItemIds,
    indexToId: input.indexToId,
    heightMap: input.heightMap,
    estimatedItemHeight: input.estimatedItemHeight,
  });
  const visibleStart = anchor.index;

  let visibleEnd = visibleStart;
  let remaining = anchor.offsetWithinItem + input.clientHeight;
  while (visibleEnd < input.itemCount && remaining > 0) {
    remaining -= getItemHeightAtIndex(
      visibleEnd,
      input.estimatedItemHeight,
      input.viewportStart,
      input.visibleItemIds,
      input.indexToId,
      input.heightMap,
    );
    visibleEnd += 1;
  }
  if (input.itemCount > 0 && visibleEnd === visibleStart) {
    visibleEnd = visibleStart + 1;
  }

  return {
    start: Math.max(0, visibleStart - input.overscan),
    end: Math.min(input.itemCount, visibleEnd + input.overscan),
  };
}

export function resolveFollowState(params: {
  scrollTop: number;
  clientHeight: number;
  scrollHeight: number;
  threshold?: number;
}): FollowState {
  const distanceFromBottom = Math.max(0, params.scrollHeight - params.clientHeight - params.scrollTop);
  return distanceFromBottom <= (params.threshold ?? FOLLOW_THRESHOLD_PX) ? 'FOLLOWING' : 'DETACHED';
}

export function resolveFollowStateOnUserScroll(params: FollowStateInput): FollowState {
  const threshold = params.threshold ?? FOLLOW_THRESHOLD_PX;
  const distanceFromBottom = Math.max(
    0,
    params.scrollHeight - params.clientHeight - params.currentScrollTop,
  );
  const isScrollingUp = params.currentScrollTop < params.previousScrollTop - 1;

  if (isScrollingUp || distanceFromBottom > threshold) {
    return 'DETACHED';
  }
  if (distanceFromBottom <= threshold) {
    return 'FOLLOWING';
  }
  return params.previousState;
}

export function resolveScrollCause(params: ScrollCauseInput): ScrollCause {
  if (params.isProgrammaticScroll) {
    return 'LAYOUT_OR_PROGRAMMATIC';
  }
  if (params.hasPendingUserIntent || params.isPointerDragging || params.isUserScrolling) {
    return 'USER';
  }
  return 'LAYOUT_OR_PROGRAMMATIC';
}

export function resolveFollowStateOnScroll(params: FollowStateOnScrollInput): FollowState {
  if (params.cause === 'USER') {
    return resolveFollowStateOnUserScroll(params);
  }
  const nextState = resolveFollowState({
    scrollTop: params.currentScrollTop,
    clientHeight: params.clientHeight,
    scrollHeight: params.scrollHeight,
    threshold: params.threshold,
  });
  return nextState === 'FOLLOWING' ? 'FOLLOWING' : params.previousState;
}

export function shouldAutoRefreshViewport(params: {
  stickToBottom: boolean;
  followState: FollowState;
}): boolean {
  if (!params.stickToBottom) {
    return true;
  }
  return params.followState === 'FOLLOWING';
}

interface VirtualListProps {
  itemCount: number;
  children?: React.ReactNode;
  onViewport?: (info: { start: number; end: number }) => void;
  onScroll?: (info: { scrollTop: number }) => void;
  scrollTop?: number;
  overscan?: number;
  style?: React.CSSProperties;
  stickToBottom?: boolean;
  estimatedItemHeight?: number;
  itemIds?: string[];
  viewportStart?: number;
}

export function VirtualList({
  itemCount,
  children,
  onViewport,
  onScroll: onScrollHandler,
  scrollTop: scrollTopProp,
  overscan = DEFAULT_OVERSCAN,
  style,
  stickToBottom = false,
  estimatedItemHeight = DEFAULT_ITEM_HEIGHT,
  itemIds = [],
  viewportStart = 0,
}: VirtualListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const heightMapRef = useRef(new Map<string, number>());
  const indexToIdRef = useRef(new Map<number, string>());
  const idToIndexRef = useRef(new Map<string, number>());
  const itemElementsRef = useRef(new Map<string, HTMLDivElement>());
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const pendingMeasureIdsRef = useRef(new Set<string>());
  const stagedHeightUpdatesRef = useRef(new Map<string, number>());
  const measureRafRef = useRef<number | null>(null);
  const measuredHeightSumRef = useRef(0);
  const measuredCountRef = useRef(0);
  const followStateRef = useRef<FollowState>('FOLLOWING');
  const userScrollingRef = useRef(false);
  const userScrollIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingLayoutApplyRef = useRef(false);
  const lastFireRef = useRef(0);
  const lastScrollTopRef = useRef(0);
  const trailingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sentViewportRef = useRef<{ start: number; end: number }>({
    start: -1,
    end: -1,
  });
  const [layoutVersion, setLayoutVersion] = useState(0);
  const isProgrammaticScrollRef = useRef(false);
  const pendingUserScrollIntentRef = useRef(false);
  const pointerDraggingRef = useRef(false);

  const visibleChildren = Children.toArray(children);
  const effectiveEstimatedItemHeight = getEstimatedItemHeight(
    measuredHeightSumRef.current,
    measuredCountRef.current,
    estimatedItemHeight,
  );

  const layout = useMemo(
    () => calculateVirtualLayout({
      itemCount,
      viewportStart,
      visibleItemIds: itemIds,
      indexToId: indexToIdRef.current,
      heightMap: heightMapRef.current,
      estimatedItemHeight: effectiveEstimatedItemHeight,
    }),
    [itemCount, viewportStart, itemIds, effectiveEstimatedItemHeight, visibleChildren.length, layoutVersion],
  );

  const applyMeasuredHeightUpdates = useCallback((updates: Map<string, number>) => {
    let changed = false;
    for (const [itemId, nextHeight] of updates) {
      const prevHeight = heightMapRef.current.get(itemId);
      if (prevHeight == null || Math.abs(prevHeight - nextHeight) > 0.5) {
        if (prevHeight == null) {
          measuredHeightSumRef.current += nextHeight;
          measuredCountRef.current += 1;
        } else {
          measuredHeightSumRef.current += nextHeight - prevHeight;
        }
        heightMapRef.current.set(itemId, nextHeight);
        changed = true;
      }
    }
    return changed;
  }, []);

  const flushMeasuredHeights = useCallback(() => {
    measureRafRef.current = null;
    const updates = new Map<string, number>();
    for (const itemId of pendingMeasureIdsRef.current) {
      const element = itemElementsRef.current.get(itemId);
      if (!element) continue;
      const nextHeight = Math.max(1, element.getBoundingClientRect().height);
      updates.set(itemId, nextHeight);
    }
    pendingMeasureIdsRef.current.clear();

    if (updates.size === 0) return;

    if (userScrollingRef.current && followStateRef.current !== 'FOLLOWING') {
      for (const [itemId, nextHeight] of updates) {
        stagedHeightUpdatesRef.current.set(itemId, nextHeight);
      }
      pendingLayoutApplyRef.current = true;
      return;
    }

    for (const [itemId, nextHeight] of stagedHeightUpdatesRef.current) {
      updates.set(itemId, nextHeight);
    }
    stagedHeightUpdatesRef.current.clear();
    const changed = applyMeasuredHeightUpdates(updates);
    if (!changed) return;

    // 锚底由 useLayoutEffect 在 React 更新 spacer 后统一执行，
    // 此时 el.scrollHeight 已反映正确值，避免读旧 spacer 高度。
    setLayoutVersion((version) => version + 1);
  }, [applyMeasuredHeightUpdates]);

  const scheduleMeasuredHeightsFlush = useCallback(() => {
    if (measureRafRef.current != null) return;
    measureRafRef.current = requestAnimationFrame(flushMeasuredHeights);
  }, [flushMeasuredHeights]);

  const calculateViewport = useCallback(() => {
    const el = containerRef.current;
    if (!el || !onViewport) return;

    const estHeight = getEstimatedItemHeight(
      measuredHeightSumRef.current,
      measuredCountRef.current,
      estimatedItemHeight,
    );

    let nextRange: { start: number; end: number };

    if (stickToBottom && followStateRef.current === 'FOLLOWING') {
      // FOLLOWING 时已知在底部，不读 scrollTop，直接用 itemCount 算底部范围。
      // 避免 force-to-bottom → scroll 事件 → scrollTop 微变 → viewport 范围
      // 偏移 → item 创建/销毁 → ResizeObserver → 回路。
      const visibleCount = Math.ceil(el.clientHeight / Math.max(1, estHeight));
      nextRange = {
        start: Math.max(0, itemCount - visibleCount - overscan),
        end: itemCount,
      };
    } else {
      nextRange = calculateViewportRange({
        itemCount,
        scrollTop: el.scrollTop,
        clientHeight: el.clientHeight,
        overscan,
        viewportStart,
        visibleItemIds: itemIds,
        indexToId: indexToIdRef.current,
        heightMap: heightMapRef.current,
        estimatedItemHeight: estHeight,
      });
    }

    const prev = sentViewportRef.current;
    if (prev.start === nextRange.start && prev.end === nextRange.end) return;

    sentViewportRef.current = { start: nextRange.start, end: nextRange.end };
    onViewport({ start: nextRange.start, end: nextRange.end });
  }, [estimatedItemHeight, itemCount, itemIds, layoutVersion, onViewport, overscan, viewportStart, stickToBottom]);

  const scheduleUserScrollIdle = useCallback(() => {
    userScrollingRef.current = true;
    if (userScrollIdleTimerRef.current) {
      clearTimeout(userScrollIdleTimerRef.current);
    }
    userScrollIdleTimerRef.current = setTimeout(() => {
      userScrollingRef.current = false;
      userScrollIdleTimerRef.current = null;
      if (pendingLayoutApplyRef.current) {
        pendingLayoutApplyRef.current = false;
        const changed = applyMeasuredHeightUpdates(stagedHeightUpdatesRef.current);
        stagedHeightUpdatesRef.current.clear();
        if (changed) {
          setLayoutVersion((version) => version + 1);
        }
      }
    }, USER_SCROLL_IDLE_MS);
  }, [applyMeasuredHeightUpdates]);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    // 在 resolveScrollCause 之前启动 userScrolling 锁存,
    // 确保同一个用户手势的后续动量 scroll 事件也能判为 USER
    if (pendingUserScrollIntentRef.current || pointerDraggingRef.current) {
      scheduleUserScrollIdle();
    }

    const scrollCause = resolveScrollCause({
      isProgrammaticScroll: isProgrammaticScrollRef.current,
      hasPendingUserIntent: pendingUserScrollIntentRef.current,
      isPointerDragging: pointerDraggingRef.current,
      isUserScrolling: userScrollingRef.current,
    });

    if (stickToBottom) {
      followStateRef.current = resolveFollowStateOnScroll({
        cause: scrollCause,
        previousState: followStateRef.current,
        previousScrollTop: lastScrollTopRef.current,
        currentScrollTop: el.scrollTop,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
      });
    }
    lastScrollTopRef.current = el.scrollTop;

    const now = Date.now();
    const elapsed = now - lastFireRef.current;

    if (trailingRef.current) clearTimeout(trailingRef.current);

    if (elapsed >= VIEWPORT_THROTTLE_MS) {
      lastFireRef.current = now;
      calculateViewport();
    }
    trailingRef.current = setTimeout(() => {
      lastFireRef.current = Date.now();
      calculateViewport();
    }, VIEWPORT_THROTTLE_MS);

    if (onScrollHandler && !isProgrammaticScrollRef.current) {
      onScrollHandler({ scrollTop: el.scrollTop });
    }

    pendingUserScrollIntentRef.current = false;
    isProgrammaticScrollRef.current = false;
  }, [calculateViewport, onScrollHandler, scheduleUserScrollIdle, stickToBottom]);

  useEffect(() => {
    const rafId = requestAnimationFrame(() => calculateViewport());
    return () => cancelAnimationFrame(rafId);
  }, [calculateViewport]);

  useEffect(() => {
    if (!shouldAutoRefreshViewport({
      stickToBottom,
      followState: followStateRef.current,
    })) {
      return;
    }
    calculateViewport();
  }, [itemCount, itemIds, layoutVersion, calculateViewport, stickToBottom]);

  useEffect(() => {
    if (scrollTopProp == null) return;
    const el = containerRef.current;
    if (!el) return;
    if (Math.abs(el.scrollTop - scrollTopProp) < 1) return;
    isProgrammaticScrollRef.current = true;
    el.scrollTop = scrollTopProp;
    lastScrollTopRef.current = scrollTopProp;
  }, [scrollTopProp]);

  useEffect(() => {
    const indexToId = indexToIdRef.current;
    const idToIndex = idToIndexRef.current;

    for (const [index, itemId] of Array.from(indexToId.entries())) {
      if (index >= itemCount) {
        indexToId.delete(index);
        if (idToIndex.get(itemId) === index) {
          idToIndex.delete(itemId);
        }
      }
    }

    itemIds.forEach((itemId, offset) => {
      const index = viewportStart + offset;
      const previousId = indexToId.get(index);
      if (previousId && previousId !== itemId) {
        idToIndex.delete(previousId);
      }
      const previousIndex = idToIndex.get(itemId);
      if (previousIndex != null && previousIndex !== index) {
        indexToId.delete(previousIndex);
      }
      indexToId.set(index, itemId);
      idToIndex.set(itemId, index);
    });
  }, [itemCount, itemIds, viewportStart]);

  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const itemId = (entry.target as HTMLElement).dataset.itemId;
        if (itemId) {
          pendingMeasureIdsRef.current.add(itemId);
        }
      }
      scheduleMeasuredHeightsFlush();
    });
    resizeObserverRef.current = observer;
    return () => {
      observer.disconnect();
      resizeObserverRef.current = null;
      if (measureRafRef.current != null) {
        cancelAnimationFrame(measureRafRef.current);
        measureRafRef.current = null;
      }
    };
  }, [scheduleMeasuredHeightsFlush]);

  // F1：post-render 同步锚底。flush 内 setLayoutVersion 触发 React
  // 重渲染更新 spacer 高度，useLayoutEffect 在 DOM 提交后、paint 前
  // 同步执行，此时 el.scrollHeight 已反映正确的新内容下界。
  useLayoutEffect(() => {
    if (!stickToBottom || followStateRef.current !== 'FOLLOWING') return;
    const el = containerRef.current;
    if (!el) return;
    const target = Math.max(0, el.scrollHeight - el.clientHeight);
    if (Math.abs(el.scrollTop - target) < 1) return;
    isProgrammaticScrollRef.current = true;
    el.scrollTop = target;
    lastScrollTopRef.current = target;
  }, [layoutVersion, stickToBottom]);

  useEffect(() => {
    // F2：仅作为 ResizeObserver 不会触发的兜底路径（item 删除等）。
    // 流式高度变化的锚底已由 useLayoutEffect (F1) 在 post-render 阶段完成，
    // 此处不再依赖 layoutVersion，避免 "flush → layoutVersion++ → effect
    // 异步跨帧读不同 scrollHeight → 二次 force" 的振荡回路。
    if (!stickToBottom || followStateRef.current !== 'FOLLOWING') return;
    const el = containerRef.current;
    if (!el) return;
    const targetScrollTop = Math.max(0, el.scrollHeight - el.clientHeight);
    if (Math.abs(el.scrollTop - targetScrollTop) < 1) return;
    isProgrammaticScrollRef.current = true;
    el.scrollTop = targetScrollTop;
    lastScrollTopRef.current = targetScrollTop;
  }, [itemCount, itemIds, stickToBottom]);

  useEffect(() => {
    const handleWindowKeyDown = (event: KeyboardEvent) => {
      if (!USER_SCROLL_KEYS.has(event.key)) return;
      // 不检查 activeElement：VirtualList item 为非 focusable 的 div，
      // document.activeElement 始终为 body，el.contains(body) 永远为 false。
      // 误设 flag 的副作用轻微：flag 只在 handleScroll 触发时消费，
      // 且 isProgrammaticScroll 有更高优先级，不会干扰贴底逻辑。
      pendingUserScrollIntentRef.current = true;
    };
    const clearPointerDragging = () => {
      pointerDraggingRef.current = false;
    };

    window.addEventListener('keydown', handleWindowKeyDown, true);
    window.addEventListener('pointercancel', clearPointerDragging, true);
    window.addEventListener('pointerup', clearPointerDragging, true);

    return () => {
      window.removeEventListener('keydown', handleWindowKeyDown, true);
      window.removeEventListener('pointercancel', clearPointerDragging, true);
      window.removeEventListener('pointerup', clearPointerDragging, true);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (trailingRef.current) {
        clearTimeout(trailingRef.current);
      }
      if (userScrollIdleTimerRef.current) {
        clearTimeout(userScrollIdleTimerRef.current);
      }
    };
  }, []);

  const bindItemRef = useCallback((itemId: string) => {
    return (element: HTMLDivElement | null) => {
      const observer = resizeObserverRef.current;
      const previous = itemElementsRef.current.get(itemId);
      if (previous && observer) {
        observer.unobserve(previous);
      }
      if (!element) {
        itemElementsRef.current.delete(itemId);
        return;
      }
      itemElementsRef.current.set(itemId, element);
      observer?.observe(element);
      pendingMeasureIdsRef.current.add(itemId);
      scheduleMeasuredHeightsFlush();
    };
  }, [scheduleMeasuredHeightsFlush]);

  return (
    <div
      ref={containerRef}
      className="mutgui-virtual-list mutgui-scrollbar"
      onScroll={handleScroll}
      onPointerDownCapture={(event) => {
        if (event.pointerType !== 'mouse' || event.button !== 0) return;
        pendingUserScrollIntentRef.current = true;
        pointerDraggingRef.current = true;
      }}
      onTouchMoveCapture={() => {
        pendingUserScrollIntentRef.current = true;
      }}
      onWheelCapture={() => {
        pendingUserScrollIntentRef.current = true;
      }}
      style={style}
    >
      <div style={{ height: layout.totalHeight, pointerEvents: 'none' }} />
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          transform: `translateY(${layout.offsetTop}px)`,
        }}
      >
        {visibleChildren.map((child, index) => {
          const itemId = itemIds[index] ?? `__virtual-${viewportStart + index}`;
          return (
            <div
              key={itemId}
              ref={bindItemRef(itemId)}
              data-item-id={itemId}
            >
              {child}
            </div>
          );
        })}
      </div>
    </div>
  );
}
