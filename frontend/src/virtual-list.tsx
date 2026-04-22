/**
 * VirtualList — 虚拟滚动列表组件。
 *
 * 后端控制可见 item 列表（通过 onViewport 事件），
 * 前端负责滚动容器、高度估算、viewport 计算和防抖。
 * children 由框架从 $children 渲染为 MutguiView 列表。
 */
import { useRef, useState, useCallback, useEffect, Children } from 'react';

const DEFAULT_ITEM_HEIGHT = 32;
const DEFAULT_OVERSCAN = 5;
const VIEWPORT_THROTTLE_MS = 50;

interface VirtualListProps {
  itemCount: number;
  children?: React.ReactNode;
  onViewport?: (info: { start: number; end: number }) => void;
  onScroll?: (info: { scrollTop: number }) => void;
  scrollTop?: number;
  overscan?: number;
  style?: React.CSSProperties;
}

export function VirtualList({
  itemCount,
  children,
  onViewport,
  onScroll: onScrollHandler,
  scrollTop: scrollTopProp,
  overscan = DEFAULT_OVERSCAN,
  style,
}: VirtualListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // throttle 状态
  const lastFireRef = useRef(0);
  const trailingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 当前 viewport 范围（已发送给后端）
  const sentViewportRef = useRef<{ start: number; end: number }>({
    start: -1,
    end: -1,
  });

  // item 起始 index
  const [viewportStart, setViewportStart] = useState(0);

  // 防循环：programmatic scroll 时跳过 onScroll 回发
  const isProgrammaticScrollRef = useRef(false);

  const estimatedTotalHeight = itemCount * DEFAULT_ITEM_HEIGHT;

  const calculateViewport = useCallback(() => {
    const el = containerRef.current;
    if (!el || !onViewport) return;

    const scrollTop = el.scrollTop;
    const clientHeight = el.clientHeight;

    const start = Math.max(0, Math.floor(scrollTop / DEFAULT_ITEM_HEIGHT) - overscan);
    const visibleCount = Math.ceil(clientHeight / DEFAULT_ITEM_HEIGHT);
    const end = Math.min(itemCount, start + visibleCount + overscan * 2);

    // 只在范围真正变化时发送
    const prev = sentViewportRef.current;
    if (prev.start === start && prev.end === end) return;

    sentViewportRef.current = { start, end };
    setViewportStart(start);
    onViewport({ start, end });
  }, [itemCount, onViewport]);

  // leading + trailing throttle
  const handleScroll = useCallback(() => {
    const now = Date.now();
    const elapsed = now - lastFireRef.current;

    if (trailingRef.current) clearTimeout(trailingRef.current);

    if (elapsed >= VIEWPORT_THROTTLE_MS) {
      // leading: 距上次已超过间隔，立即触发
      lastFireRef.current = now;
      calculateViewport();
    }
    // trailing: 确保滚动结束后也触发一次
    trailingRef.current = setTimeout(() => {
      lastFireRef.current = Date.now();
      calculateViewport();
    }, VIEWPORT_THROTTLE_MS);

    // sync scroll: 回报滚动位置（仅用户主动滚动时）
    if (onScrollHandler && !isProgrammaticScrollRef.current) {
      const el = containerRef.current;
      if (el) {
        onScrollHandler({ scrollTop: el.scrollTop });
      }
    }
    isProgrammaticScrollRef.current = false;
  }, [calculateViewport, onScrollHandler]);

  // 初始 viewport 计算（组件挂载后）
  useEffect(() => {
    // 等一帧让容器有尺寸
    requestAnimationFrame(() => calculateViewport());
  }, [calculateViewport]);

  // itemCount 变化时重新计算（可能需要调整 viewport）
  useEffect(() => {
    calculateViewport();
  }, [itemCount, calculateViewport]);

  // sync scroll: 收到后端 scrollTop 时 programmatically 滚动
  useEffect(() => {
    if (scrollTopProp == null) return;
    const el = containerRef.current;
    if (!el) return;
    if (Math.abs(el.scrollTop - scrollTopProp) < 1) return;
    isProgrammaticScrollRef.current = true;
    el.scrollTop = scrollTopProp;
  }, [scrollTopProp]);

  const offsetTop = viewportStart * DEFAULT_ITEM_HEIGHT;

  return (
    <div
      ref={containerRef}
      className="mutgui-virtual-list"
      onScroll={handleScroll}
      style={style}
    >
      {/* 占位区域（撑起滚动条） */}
      <div style={{ height: estimatedTotalHeight, pointerEvents: 'none' }} />
      {/* 可见 item — children 由框架从 $children 渲染而来 */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          transform: `translateY(${offsetTop}px)`,
        }}
      >
        {Children.map(children, (child) => (
          <div style={{ minHeight: DEFAULT_ITEM_HEIGHT }}>{child}</div>
        ))}
      </div>
    </div>
  );
}
