/**
 * VirtualList - 内容流虚拟滚动列表组件。
 *
 * 所有 item 保持在正常文档流中，利用浏览器原生 overflow-anchor
 * 维持视觉稳定。后端 onViewport 上报 report 范围，返回对应 item，
 * 前端全量渲染 report 范围内的 item 为完整 React 组件。
 * report 范围外的远端 item 用 spacer div 估算高度占位。
 */
import { useRef, useState, useCallback, useEffect, useLayoutEffect, Children } from 'react';

const USER_SCROLL_IDLE_MS = 100;
// 保底缓冲：视口极小时的绝对下限 item 数
const MIN_PADDING = 5;
const MIN_DEADZONE = 2;
const VL_DEBUG = false;

const USER_SCROLL_KEYS = new Set([
  'ArrowDown', 'ArrowUp', 'End', 'Home', 'PageDown', 'PageUp', 'Space', ' ',
]);

export const FOLLOW_THRESHOLD_PX = 32;
export type FollowState = 'FOLLOWING' | 'DETACHED';

interface VirtualListProps {
  itemCount: number;
  children?: React.ReactNode;
  onViewport?: (info: { start: number; end: number; seq: number }) => void;
  onScroll?: (info: { scrollTop: number }) => void;
  scrollTop?: number;
  style?: React.CSSProperties;
  stickToBottom?: boolean;
  estimatedItemHeight?: number;
  bufferScreens?: number;
  deadzoneScreens?: number;
  itemIds?: string[];
  viewportStart?: number;
  viewportSeq?: number;
}

export function VirtualList({
  itemCount,
  children,
  onViewport,
  onScroll: onScrollHandler,
  scrollTop: scrollTopProp,
  style,
  stickToBottom = false,
  estimatedItemHeight = 32,
  bufferScreens = 1.0,
  deadzoneScreens = 0.5,
  itemIds = [],
  viewportStart = 0,
  viewportSeq = 0,
}: VirtualListProps) {
  // ── Refs ──
  const containerRef = useRef<HTMLDivElement>(null);
  const heightCacheRef = useRef(new Map<string, number>());
  const itemElementsRef = useRef(new Map<string, HTMLDivElement>());
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const followStateRef = useRef<FollowState>(
    stickToBottom ? 'FOLLOWING' : 'DETACHED',
  );
  const lastScrollTopRef = useRef(0);
  const pendingUserScrollIntentRef = useRef(false);
  const userScrollingRef = useRef(false);
  const userScrollIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pointerDraggingRef = useRef(false);
  const forceRafRef = useRef<number | null>(null);
  const lastScrollHeightRef = useRef(0);

  // ── Viewport reporter refs ──
  const dirtyRef = useRef(false);
  const reportInFlightRef = useRef(false);
  const pendingReportRef = useRef<{ start: number; end: number } | null>(null);
  const pendingReportSeqRef = useRef(0);
  const rafIdRef = useRef<number | null>(null);
  const lastReportedRef = useRef<{ start: number; end: number } | null>(null);
  const reportSeqRef = useRef(0);
  const initialScrollDoneRef = useRef(false);

  // ── State ──
  // displayedRange 在 viewport 上报时立即同步，驱动 spacer 渲染。
  // 与 viewportStart（后端异步返回）解耦，避免数据到达时 spacer 突变引发 layout shift → 级联。
  const [displayedRange, setDisplayedRange] = useState<{ start: number; end: number } | null>(null);

  // ── Derived ──
  const visibleChildren = Children.toArray(children);

  // ── Height recording ──
  const recordHeight = useCallback((itemId: string, height: number) => {
    const prev = heightCacheRef.current.get(itemId);
    if (prev == null || Math.abs(prev - height) > 0.5) {
      heightCacheRef.current.set(itemId, height);
    }
  }, []);

  // ── 用户滚动锁存：让同一个用户手势的后续动量 scroll 事件也判为 USER ──
  const scheduleUserScrollIdle = useCallback(() => {
    userScrollingRef.current = true;
    if (userScrollIdleTimerRef.current) clearTimeout(userScrollIdleTimerRef.current);
    userScrollIdleTimerRef.current = setTimeout(() => {
      userScrollingRef.current = false;
      userScrollIdleTimerRef.current = null;
    }, USER_SCROLL_IDLE_MS);
  }, []);

  // ── Force-to-bottom (streaming FOLLOWING 场景：ResizeObserver 触发) ──
  const scheduleForceToBottom = useCallback(() => {
    if (forceRafRef.current != null) return;
    forceRafRef.current = requestAnimationFrame(() => {
      forceRafRef.current = null;
      if (followStateRef.current !== 'FOLLOWING') return;
      const el = containerRef.current;
      if (!el) return;
      const sh = el.scrollHeight;
      const ch = el.clientHeight;
      const target = Math.max(0, sh - ch);
      const oldST = el.scrollTop;
      if (Math.abs(oldST - target) < 1) {
        if (VL_DEBUG) console.debug(
          `[VL force] skip scrollHeight=${sh} target=${target} scrollTop=${oldST.toFixed(0)}`,
        );
        return;
      }
      el.scrollTop = target;
      lastScrollTopRef.current = el.scrollTop;
      if (VL_DEBUG) console.debug(
        `[VL force] scrollHeight=${sh} target=${target} scrollTop ${oldST.toFixed(0)}→${el.scrollTop.toFixed(0)}`,
      );
    });
  }, []);

  // ── 初始化路径：基于 scrollTop 估算 anchor，整窗计算范围。
  const computeFreshRange = useCallback(
    (scrollTop: number, clientHeight: number) => {
      if (itemCount <= 0 || clientHeight <= 0) {
        return { start: 0, end: 0 };
      }
      const visibleCount = Math.ceil(clientHeight / Math.max(1, estimatedItemHeight));
      const padding = Math.max(MIN_PADDING, Math.ceil(visibleCount * bufferScreens));
      const anchor = Math.min(
        itemCount - 1,
        Math.max(0, Math.floor(scrollTop / estimatedItemHeight)),
      );
      return {
        start: Math.max(0, anchor - padding),
        end: Math.min(itemCount, anchor + visibleCount + padding),
      };
    },
    [estimatedItemHeight, itemCount, bufferScreens],
  );

  // ── 展路径：基于已持有 item 的像素位置，视口接近边缘时单边扩展。
  // 返回 null 表示在死区内，无需上报。
  const computeNextReport = useCallback((): { start: number; end: number } | null => {
    const el = containerRef.current;
    if (!el || itemCount <= 0 || el.clientHeight <= 0) return null;

    const clientHeight = el.clientHeight;

    // stickToBottom 首屏锚底：scrollTop 还是 0，用估算底部位置上报
    if (stickToBottom && !initialScrollDoneRef.current) {
      const fakeST = Math.max(0, itemCount * estimatedItemHeight - clientHeight);
      return computeFreshRange(fakeST, clientHeight);
    }

    const scrollTop = el.scrollTop;
    const last = lastReportedRef.current;

    // 首次 / itemIds 还没到 → 走 fresh 路径
    if (last == null || itemIds.length === 0) {
      const fresh = computeFreshRange(scrollTop, clientHeight);
      if (last != null && fresh.start === last.start && fresh.end === last.end) {
        return null;
      }
      return fresh;
    }

    // 数据匹配检查
    const dataMatches = viewportSeq === reportSeqRef.current;

    // 健壮性：last 与 itemCount 失配
    if (last.start >= itemCount || last.end > itemCount) {
      return computeFreshRange(scrollTop, clientHeight);
    }

    // 阈值派生：缓冲量 = 视口可容纳的 item 数 × 屏数系数
    const visibleItems = clientHeight / Math.max(1, estimatedItemHeight);
    const padding = Math.max(MIN_PADDING, Math.ceil(visibleItems * bufferScreens));
    const deadzone = Math.max(MIN_DEADZONE, Math.ceil(visibleItems * deadzoneScreens));
    const paddingPx = padding * estimatedItemHeight;
    const deadzonePx = deadzone * estimatedItemHeight;
    const triggerThreshold = paddingPx - deadzonePx;
    const targetBuffer = paddingPx + deadzonePx;

    const headSpacer = last.start * estimatedItemHeight;
    let heldHeight: number;
    if (dataMatches) {
      heldHeight = 0;
      for (const id of itemIds) {
        heldHeight += heightCacheRef.current.get(id) ?? estimatedItemHeight;
      }
    } else {
      heldHeight = (last.end - last.start) * estimatedItemHeight;
    }
    const firstItemTop = headSpacer;
    const lastItemBottom = headSpacer + heldHeight;
    const headBuffer = scrollTop - firstItemTop;
    const tailBuffer = lastItemBottom - (scrollTop + clientHeight);

    // 大跳检测
    if (
      scrollTop > lastItemBottom + clientHeight ||
      scrollTop + clientHeight < firstItemTop - clientHeight
    ) {
      return computeFreshRange(scrollTop, clientHeight);
    }

    let newStart = last.start;
    let newEnd = last.end;

    // 头部扩张 + 尾部协同修剪
    if (headBuffer < triggerThreshold && last.start > 0) {
      const expandItems = Math.ceil((targetBuffer - headBuffer) / estimatedItemHeight);
      newStart = Math.max(0, last.start - expandItems);
      if (tailBuffer > targetBuffer) {
        const trimItems = Math.floor((tailBuffer - targetBuffer) / estimatedItemHeight);
        const trimmedEnd = Math.min(itemCount, newEnd - trimItems);
        if (trimmedEnd > newStart + padding * 2) {
          newEnd = trimmedEnd;
        }
      }
    }

    // 尾部扩张 + 头部协同修剪
    if (tailBuffer < triggerThreshold && last.end < itemCount) {
      const expandItems = Math.ceil((targetBuffer - tailBuffer) / estimatedItemHeight);
      newEnd = Math.min(itemCount, last.end + expandItems);
      if (headBuffer > targetBuffer) {
        const trimItems = Math.floor((headBuffer - targetBuffer) / estimatedItemHeight);
        const trimmedStart = Math.max(0, newStart + trimItems);
        if (trimmedStart < newEnd - padding * 2) {
          newStart = trimmedStart;
        }
      }
    }

    if (newStart === last.start && newEnd === last.end) return null;
    if (VL_DEBUG) {
      const st2 = containerRef.current?.scrollTop ?? 0;
      const ch2 = containerRef.current?.clientHeight ?? 0;
      console.debug(
        `[VL debug] last=[${last.start},${last.end}) dataMatch=${viewportSeq === reportSeqRef.current}`,
        `heldH=${heldHeight.toFixed(0)} headBuf=${headBuffer.toFixed(0)} tailBuf=${tailBuffer.toFixed(0)}`,
        `thresh=${triggerThreshold.toFixed(0)} tgtBuf=${targetBuffer.toFixed(0)}`,
        `scrollTop=${st2.toFixed(0)} clientH=${ch2}`,
        `→ [${newStart},${newEnd})`,
      );
    }
    return { start: newStart, end: newEnd };
  }, [itemCount, itemIds, estimatedItemHeight, bufferScreens, deadzoneScreens, stickToBottom, computeFreshRange, viewportStart, viewportSeq]);

  // ── rAF 轮询：读 scrollTop，计算，上报 ──
  const poll = useCallback(() => {
    rafIdRef.current = null;

    if (!dirtyRef.current) return;

    if (reportInFlightRef.current) {
      // 上次上报未返回，不重复请求。dirtyRef 保持 true。
      return;
    }

    const next = computeNextReport();
    if (next == null) {
      dirtyRef.current = false;
      return;
    }

    // 与已发送未返回的上报相同 → 跳过
    if (
      pendingReportRef.current != null &&
      next.start === pendingReportRef.current.start &&
      next.end === pendingReportRef.current.end
    ) {
      dirtyRef.current = false;
      return;
    }

    const seq = ++reportSeqRef.current;
    lastReportedRef.current = next;
    pendingReportRef.current = next;
    pendingReportSeqRef.current = seq;
    reportInFlightRef.current = true;
    dirtyRef.current = false;

    setDisplayedRange(next);
    if (VL_DEBUG) {
      const st3 = containerRef.current?.scrollTop ?? 0;
      console.debug(
        `[VL viewport] seq=${seq} report=[${next.start},${next.end})`,
        `scrollTop=${st3.toFixed(0)}`,
      );
    }
    onViewport?.({ ...next, seq });
  }, [computeNextReport, onViewport]);

  // ── 调度视口重检（唯一入口，幂等）──
  const scheduleViewportRecheck = useCallback(() => {
    dirtyRef.current = true;
    if (rafIdRef.current != null) return;
    rafIdRef.current = requestAnimationFrame(poll);
  }, [poll]);

  // ResizeObserver 回调中使用 ref 模式访问最新 scheduleViewportRecheck，
  // 避免 observer effect 不随 poll 重建导致的闭包过期问题。
  const scheduleViewportRecheckRef = useRef(scheduleViewportRecheck);
  scheduleViewportRecheckRef.current = scheduleViewportRecheck;

  // ── Scroll handler ──
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    // 更新 follow 状态
    if (stickToBottom) {
      if (pendingUserScrollIntentRef.current || pointerDraggingRef.current) {
        scheduleUserScrollIdle();
      }

      const isUserScroll =
        pendingUserScrollIntentRef.current ||
        pointerDraggingRef.current ||
        userScrollingRef.current;

      const distanceFromBottom = Math.max(
        0,
        el.scrollHeight - el.clientHeight - el.scrollTop,
      );

      if (isUserScroll) {
        const scrollingUp = el.scrollTop < lastScrollTopRef.current - 1;
        if (scrollingUp || distanceFromBottom > FOLLOW_THRESHOLD_PX) {
          followStateRef.current = 'DETACHED';
        } else if (distanceFromBottom <= FOLLOW_THRESHOLD_PX) {
          followStateRef.current = 'FOLLOWING';
        }
      } else {
        if (distanceFromBottom <= FOLLOW_THRESHOLD_PX) {
          followStateRef.current = 'FOLLOWING';
        }
      }
    }
    lastScrollTopRef.current = el.scrollTop;
    pendingUserScrollIntentRef.current = false;

    if (onScrollHandler) {
      onScrollHandler({ scrollTop: el.scrollTop });
    }

    scheduleViewportRecheck();
  }, [stickToBottom, onScrollHandler, scheduleViewportRecheck, scheduleUserScrollIdle]);

  // ── 用户交互检测 ──
  useEffect(() => {
    const el = containerRef.current;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!USER_SCROLL_KEYS.has(event.key)) return;
      // 不检查 activeElement：VirtualList item 为非 focusable 的 div，
      // document.activeElement 始终为 body，el.contains(body) 永远为 false。
      // 误设 flag 的副作用轻微：flag 只在 handleScroll 触发时消费。
      pendingUserScrollIntentRef.current = true;
    };

    const handlePointerDown = () => {
      pointerDraggingRef.current = true;
    };
    const clearPointerDragging = () => {
      pointerDraggingRef.current = false;
    };

    window.addEventListener('keydown', handleKeyDown, true);
    if (el) {
      el.addEventListener('pointerdown', handlePointerDown);
    }
    window.addEventListener('pointercancel', clearPointerDragging, true);
    window.addEventListener('pointerup', clearPointerDragging, true);

    return () => {
      window.removeEventListener('keydown', handleKeyDown, true);
      if (el) {
        el.removeEventListener('pointerdown', handlePointerDown);
      }
      window.removeEventListener('pointercancel', clearPointerDragging, true);
      window.removeEventListener('pointerup', clearPointerDragging, true);
      if (userScrollIdleTimerRef.current) {
        clearTimeout(userScrollIdleTimerRef.current);
      }
    };
  }, []);

  // ── ResizeObserver：测量 item 高度 + 流式锚底 + 触发视口重检 ──
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver((entries) => {
      let anyChange = false;
      let measured = 0;
      for (const entry of entries) {
        const target = entry.target as HTMLElement;
        const itemId = target.dataset.itemId;
        if (itemId) {
          const height = Math.max(1, entry.contentRect.height);
          recordHeight(itemId, height);
          anyChange = true;
          measured++;
        }
      }
      if (measured > 0) {
        const el = containerRef.current;
        const sh = el?.scrollHeight ?? 0;
        const prevSH = lastScrollHeightRef.current;
        lastScrollHeightRef.current = sh;
        if (sh !== prevSH) {
          if (VL_DEBUG) console.debug(
            `[VL observer] measured=${measured} scrollHeight ${prevSH}→${sh}`,
          );
        }
      }
      if (anyChange && stickToBottom) {
        scheduleForceToBottom();
      }
      // 高度变化 → 可能需要扩展/修剪缓冲区
      if (anyChange) {
        scheduleViewportRecheckRef.current();
      }
    });
    resizeObserverRef.current = observer;

    for (const el of itemElementsRef.current.values()) {
      observer.observe(el);
    }

    return () => {
      observer.disconnect();
      resizeObserverRef.current = null;
    };
  }, [recordHeight, scheduleForceToBottom, stickToBottom, estimatedItemHeight]);

  // ── 初始上报 ──
  useEffect(() => {
    scheduleViewportRecheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── 后端返回时解除 reportInFlight ──
  useEffect(() => {
    if (reportInFlightRef.current && viewportSeq === pendingReportSeqRef.current) {
      reportInFlightRef.current = false;
      pendingReportRef.current = null;
      pendingReportSeqRef.current = 0;
      scheduleViewportRecheck();
    }
  }, [viewportSeq, scheduleViewportRecheck]);

  // ── 数据变化日志 ──
  useEffect(() => {
    if (VL_DEBUG) console.debug(
      `[VL received] itemCount=${itemCount} itemIds=${itemIds.length}`,
      `viewportStart=${viewportStart} viewportSeq=${viewportSeq}`,
    );
  }, [itemCount, itemIds, viewportSeq]);

  // ── sync_scroll prop 同步 ──
  useEffect(() => {
    if (scrollTopProp == null) return;
    const el = containerRef.current;
    if (!el) return;
    if (Math.abs(el.scrollTop - scrollTopProp) < 1) return;
    el.scrollTop = scrollTopProp;
    lastScrollTopRef.current = scrollTopProp;
  }, [scrollTopProp]);

  // ── FOLLOWING itemCount / itemIds 变化时锚底 ──
  useLayoutEffect(() => {
    if (!stickToBottom) return;
    const el = containerRef.current;
    if (!el) return;

    const distanceFromBottom = Math.max(
      0,
      el.scrollHeight - el.clientHeight - el.scrollTop,
    );

    // 初始有 item 后无条件锚底一次
    if (!initialScrollDoneRef.current && itemIds.length > 0) {
      initialScrollDoneRef.current = true;
      const target = Math.max(0, el.scrollHeight - el.clientHeight);
      el.scrollTop = target;
      lastScrollTopRef.current = el.scrollTop;
      followStateRef.current = 'FOLLOWING';
      return;
    }

    if (distanceFromBottom > FOLLOW_THRESHOLD_PX) return;

    const target = Math.max(0, el.scrollHeight - el.clientHeight);
    if (Math.abs(el.scrollTop - target) < 1) return;
    el.scrollTop = target;
    lastScrollTopRef.current = el.scrollTop;
    followStateRef.current = 'FOLLOWING';
  }, [itemCount, stickToBottom, itemIds.length]);

  // ── 清理 ──
  useEffect(() => {
    return () => {
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      if (forceRafRef.current) cancelAnimationFrame(forceRafRef.current);
    };
  }, []);

  // ── bindItemRef：绑定 ResizeObserver ──
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
    };
  }, []);

  // spacer 用 displayedRange（上报时同步设置），不与 viewportStart（后端异步）耦合
  const headSpacerHeight =
    displayedRange && displayedRange.start > 0 ? displayedRange.start * estimatedItemHeight : 0;

  const heldEnd = displayedRange ? displayedRange.end : 0;
  const tailSpacerHeight =
    heldEnd < itemCount && heldEnd > 0
      ? (itemCount - heldEnd) * estimatedItemHeight
      : 0;

  // 从后端 children 构建渲染数组
  const renderItems: Array<{
    key: string;
    globalIndex: number;
    itemId: string;
    child: React.ReactNode;
  }> = [];

  itemIds.forEach((itemId, offset) => {
    const globalIndex = viewportStart + offset;
    const child = visibleChildren[offset];
    if (!child) return;

    renderItems.push({
      key: itemId,
      globalIndex,
      itemId,
      child,
    });
  });

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
      {headSpacerHeight > 0 && <div style={{ height: headSpacerHeight }} />}
      {renderItems.map((item) => (
        <div
          key={item.key}
          ref={bindItemRef(item.itemId)}
          data-item-id={item.itemId}
        >
          {item.child}
        </div>
      ))}
      {tailSpacerHeight > 0 && <div style={{ height: tailSpacerHeight }} />}
    </div>
  );
}
