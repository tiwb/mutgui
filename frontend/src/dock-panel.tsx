/**
 * DockPanel — 响应式多面板布局组件。
 *
 * 三个子组件：DockPanel (root)、DockPanelSplit、DockPanelTabSet。
 * 后端通过 wire tree 驱动渲染，前端负责：
 * - ResizeObserver 上报尺寸
 * - Splitter 拖拽（pointer events）
 * - Tab 点击/拖拽重排/跨 TabSet 移动（HTML5 DnD）
 * - merge_bars 融合 tab 栏渲染
 */
import {
  createContext,
  useContext,
  useRef,
  useEffect,
  useCallback,
  useState,
  Children,
} from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TabDef {
  id: string;
  title: string;
  icon?: string;
}

interface ActionDef {
  id: string;
  icon: string;
  tooltip?: string;
  position?: 'start' | 'end';
}

interface MergedTabsData {
  left: TabDef[];
  right: TabDef[];
  leftTabsetId: string;
  rightTabsetId: string;
  leftActiveId: string | null;
  rightActiveId: string | null;
}

// ---------------------------------------------------------------------------
// Context — DockPanel root 向子组件传递事件回调
// ---------------------------------------------------------------------------

interface DockPanelContextType {
  onTabSwitch?: (info: { tabsetId: string; panelId: string }) => void;
  onTabReorder?: (info: { tabsetId: string; panelIds: string[] }) => void;
  onTabMove?: (info: {
    fromTabset: string;
    toTabset: string;
    panelId: string;
    index: number;
  }) => void;
  onSplitResize?: (info: { splitId: string; ratio: number }) => void;
  onActionClick?: (info: { tabsetId: string; actionId: string }) => void;
}

const DockPanelCtx = createContext<DockPanelContextType>({});

// ---------------------------------------------------------------------------
// DockPanel (root)
// ---------------------------------------------------------------------------

interface DockPanelProps {
  panels?: Record<string, { title: string; icon?: string }>;
  onResize?: (info: { width: number; height: number }) => void;
  onTabSwitch?: (info: { tabsetId: string; panelId: string }) => void;
  onTabReorder?: (info: { tabsetId: string; panelIds: string[] }) => void;
  onTabMove?: (info: {
    fromTabset: string;
    toTabset: string;
    panelId: string;
    index: number;
  }) => void;
  onSplitResize?: (info: { splitId: string; ratio: number }) => void;
  onActionClick?: (info: { tabsetId: string; actionId: string }) => void;
  children?: React.ReactNode;
}

export function DockPanel({
  onResize,
  onTabSwitch,
  onTabReorder,
  onTabMove,
  onSplitResize,
  onActionClick,
  children,
}: DockPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !onResize) return;

    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        onResize({ width: Math.round(width), height: Math.round(height) });
      }, 150);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [onResize]);

  const ctx: DockPanelContextType = {
    onTabSwitch,
    onTabReorder,
    onTabMove,
    onSplitResize,
    onActionClick,
  };

  return (
    <DockPanelCtx.Provider value={ctx}>
      <div
        ref={containerRef}
        className="mutgui-dock-panel"
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {children}
      </div>
    </DockPanelCtx.Provider>
  );
}

// ---------------------------------------------------------------------------
// DockPanelSplit
// ---------------------------------------------------------------------------

interface DockPanelSplitProps {
  nodeId: string;
  direction: 'horizontal' | 'vertical';
  ratio: number;
  mergeBars?: boolean;
  mergedTabs?: MergedTabsData;
  children?: React.ReactNode;
}

export function DockPanelSplit({
  nodeId,
  direction,
  ratio,
  mergeBars = false,
  mergedTabs,
  children,
}: DockPanelSplitProps) {
  const { onSplitResize, onTabSwitch } = useContext(DockPanelCtx);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const childArray = Children.toArray(children);
  const child0 = childArray[0] || null;
  const child1 = childArray[1] || null;

  const isH = direction === 'horizontal';

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    dragging.current = true;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current || !containerRef.current || !onSplitResize) return;
      const rect = containerRef.current.getBoundingClientRect();
      const newRatio = isH
        ? (e.clientX - rect.left) / rect.width
        : (e.clientY - rect.top) / rect.height;
      onSplitResize({
        splitId: nodeId,
        ratio: Math.max(0, Math.min(1, newRatio)),
      });
    },
    [isH, nodeId, onSplitResize],
  );

  const onPointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  const showMergedBar = mergeBars && mergedTabs;

  const pct0 = `calc(${ratio * 100}% - 2px)`;

  const splitterStyle: React.CSSProperties = {
    flexShrink: 0,
    background: '#e0e0e0',
    cursor: isH ? 'col-resize' : 'row-resize',
    touchAction: 'none',
    ...(isH ? { width: 4 } : { height: 4 }),
    zIndex: 1,
  };

  return (
    <div
      className="mutgui-dock-split"
      style={{
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        overflow: 'hidden',
      }}
    >
      {showMergedBar && mergedTabs && (
        <MergedTabBar tabs={mergedTabs} onTabSwitch={onTabSwitch} />
      )}
      <div
        ref={containerRef}
        style={{
          display: 'flex',
          flexDirection: isH ? 'row' : 'column',
          flex: 1,
          minWidth: 0,
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            ...(isH ? { width: pct0 } : { height: pct0 }),
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          {child0}
        </div>
        <div
          className="mutgui-dock-splitter"
          style={splitterStyle}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        />
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          {child1}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MergedTabBar — merge_bars 模式下的融合 tab 栏
// ---------------------------------------------------------------------------

function MergedTabBar({
  tabs,
  onTabSwitch,
}: {
  tabs: MergedTabsData;
  onTabSwitch?: (info: { tabsetId: string; panelId: string }) => void;
}) {
  return (
    <div
      className="mutgui-dock-merged-bar"
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        background: '#fafafa',
        borderBottom: '1px solid #e0e0e0',
        padding: '0 4px',
        flexShrink: 0,
        height: 36,
        alignItems: 'center',
      }}
    >
      <div style={{ display: 'flex', gap: 2 }}>
        {tabs.left.map((tab) => (
          <TabButton
            key={tab.id}
            tab={tab}
            active={tab.id === tabs.leftActiveId}
            onClick={() =>
              onTabSwitch?.({
                tabsetId: tabs.leftTabsetId,
                panelId: tab.id,
              })
            }
          />
        ))}
      </div>
      <div style={{ display: 'flex', gap: 2 }}>
        {tabs.right.map((tab) => (
          <TabButton
            key={tab.id}
            tab={tab}
            active={tab.id === tabs.rightActiveId}
            onClick={() =>
              onTabSwitch?.({
                tabsetId: tabs.rightTabsetId,
                panelId: tab.id,
              })
            }
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TabButton — 单个 tab 按钮
// ---------------------------------------------------------------------------

function TabButton({
  tab,
  active,
  onClick,
  draggable,
  onDragStart,
  onDragOver,
  onDrop,
  onDragLeave,
  showText = true,
  vertical = false,
  indicator = 'bottom',
}: {
  tab: TabDef;
  active: boolean;
  onClick: () => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent) => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: (e: React.DragEvent) => void;
  onDragLeave?: () => void;
  showText?: boolean;
  vertical?: boolean;
  indicator?: 'top' | 'bottom' | 'left' | 'right';
}) {
  const indicatorStyle: React.CSSProperties = {};
  const key = `border${indicator.charAt(0).toUpperCase()}${indicator.slice(1)}` as
    | 'borderTop'
    | 'borderBottom'
    | 'borderLeft'
    | 'borderRight';
  indicatorStyle[key] = active
    ? '2px solid #1890ff'
    : '2px solid transparent';

  return (
    <div
      className={`mutgui-dock-tab${active ? ' mutgui-dock-tab-active' : ''}`}
      style={{
        padding: vertical ? '8px 6px' : '4px 12px',
        cursor: 'pointer',
        userSelect: 'none',
        background: active ? '#fff' : 'transparent',
        fontSize: 13,
        lineHeight: vertical ? 'normal' : '26px',
        whiteSpace: 'nowrap',
        display: 'flex',
        alignItems: 'center',
        flexDirection: vertical ? 'column' : 'row',
        gap: 4,
        ...indicatorStyle,
      }}
      onClick={onClick}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragLeave={onDragLeave}
    >
      {tab.icon && <span style={{ fontSize: 16 }}>{tab.icon}</span>}
      {showText && <span>{tab.title}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DockPanelTabSet
// ---------------------------------------------------------------------------

interface DockPanelTabSetProps {
  nodeId: string;
  tabs: TabDef[];
  activeId: string | null;
  barPosition?: 'top' | 'bottom' | 'left' | 'right';
  displayMode?: 'icon-text' | 'icon' | 'icon-active-text';
  actions?: ActionDef[];
  collapsed?: boolean;
  hideBar?: boolean;
  children?: React.ReactNode;
}

export function DockPanelTabSet({
  nodeId,
  tabs,
  activeId,
  barPosition = 'top',
  displayMode = 'icon-text',
  actions,
  collapsed = false,
  hideBar = false,
  children,
}: DockPanelTabSetProps) {
  const { onTabSwitch, onTabReorder, onTabMove, onActionClick } =
    useContext(DockPanelCtx);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const isVert = barPosition === 'left' || barPosition === 'right';

  const handleDragStart = (e: React.DragEvent, panelId: string) => {
    e.dataTransfer.setData(
      'application/mutgui-tab',
      JSON.stringify({ fromTabset: nodeId, panelId, collapsed }),
    );
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIdx(index);
  };

  const handleDrop = (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    setDragOverIdx(null);
    try {
      const raw = e.dataTransfer.getData('application/mutgui-tab');
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data.fromTabset === nodeId) {
        const curIdx = tabs.findIndex((t) => t.id === data.panelId);
        if (curIdx === -1 || curIdx === dropIndex) return;
        const newIds = tabs.map((t) => t.id);
        newIds.splice(curIdx, 1);
        newIds.splice(
          dropIndex > curIdx ? dropIndex - 1 : dropIndex,
          0,
          data.panelId,
        );
        onTabReorder?.({ tabsetId: nodeId, panelIds: newIds });
      } else {
        if (data.collapsed) return;
        onTabMove?.({
          fromTabset: data.fromTabset,
          toTabset: nodeId,
          panelId: data.panelId,
          index: dropIndex,
        });
      }
    } catch {
      /* ignore */
    }
  };

  const shouldShowText = (tabId: string) => {
    if (displayMode === 'icon-text') return true;
    if (displayMode === 'icon') return false;
    return tabId === activeId;
  };

  const indicator = (() => {
    if (isVert) return barPosition as 'left' | 'right';
    return barPosition === 'bottom' ? 'top' : 'bottom';
  })();

  const startActions = actions?.filter((a) => a.position === 'start') || [];
  const endActions =
    actions?.filter((a) => (a.position || 'end') === 'end') || [];

  const renderAction = (action: ActionDef) => (
    <div
      key={action.id}
      className="mutgui-dock-action"
      style={{
        padding: isVert ? '8px 6px' : '4px 8px',
        cursor: 'pointer',
        opacity: 0.6,
        fontSize: 14,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      title={action.tooltip || undefined}
      onClick={() => onActionClick?.({ tabsetId: nodeId, actionId: action.id })}
    >
      {action.icon}
    </div>
  );

  const tabBar = !hideBar && (
    <div
      className="mutgui-dock-tabbar"
      style={{
        display: 'flex',
        flexDirection: isVert ? 'column' : 'row',
        background: '#fafafa',
        flexShrink: 0,
        alignItems: 'stretch',
        ...(isVert
          ? {
              width: 36,
              ...(barPosition === 'left'
                ? { borderRight: '1px solid #e0e0e0' }
                : { borderLeft: '1px solid #e0e0e0' }),
            }
          : {
              height: 36,
              ...(barPosition === 'top'
                ? { borderBottom: '1px solid #e0e0e0' }
                : { borderTop: '1px solid #e0e0e0' }),
            }),
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOverIdx(tabs.length);
      }}
      onDrop={(e) => handleDrop(e, tabs.length)}
      onDragLeave={() => setDragOverIdx(null)}
    >
      {startActions.map(renderAction)}
      <div
        style={{
          display: 'flex',
          flexDirection: isVert ? 'column' : 'row',
          flex: 1,
          overflow: 'hidden',
          alignItems: 'stretch',
        }}
      >
        {tabs.map((tab, i) => (
          <TabButton
            key={tab.id}
            tab={tab}
            active={tab.id === activeId}
            showText={shouldShowText(tab.id)}
            vertical={isVert}
            indicator={
              dragOverIdx === i
                ? isVert
                  ? 'top'
                  : 'left'
                : indicator
            }
            onClick={() => onTabSwitch?.({ tabsetId: nodeId, panelId: tab.id })}
            draggable
            onDragStart={(e) => handleDragStart(e, tab.id)}
            onDragOver={(e) => handleDragOver(e, i)}
            onDrop={(e) => handleDrop(e, i)}
            onDragLeave={() => setDragOverIdx(null)}
          />
        ))}
      </div>
      {endActions.map(renderAction)}
    </div>
  );

  const contentArea = (
    <div
      className="mutgui-dock-content"
      style={{
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        overflow: 'auto',
        position: 'relative',
      }}
    >
      {children}
    </div>
  );

  const flexDir = (
    {
      top: 'column',
      bottom: 'column-reverse',
      left: 'row',
      right: 'row-reverse',
    } as const
  )[barPosition];

  return (
    <div
      className={`mutgui-dock-tabset${collapsed ? ' mutgui-dock-tabset-collapsed' : ''}`}
      style={{
        display: 'flex',
        flexDirection: flexDir,
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        overflow: 'hidden',
        border: '1px solid #f0f0f0',
      }}
    >
      {tabBar}
      {contentArea}
    </div>
  );
}
