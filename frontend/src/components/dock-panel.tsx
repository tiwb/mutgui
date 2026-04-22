/**
 * DockPanel — 响应式多面板布局组件。
 *
 * 三个子组件：DockPanel (root)、DockPanelSplit、DockPanelTabSet。
 * 后端通过 wire tree 驱动渲染，前端负责：
 * - ResizeObserver 上报尺寸
 * - Splitter 拖拽（pointer events）
 * - Tab 点击/拖拽重排/跨 TabSet 移动（HTML5 DnD）
 * - Tab 停靠分割（内容区边缘 + 页面边缘）
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

type DockPreview =
  | { type: 'panel-dock'; targetId: string; position: 'top' | 'bottom' | 'left' | 'right' }
  | { type: 'tab-move'; targetId: string }
  | { type: 'edge-dock'; edge: 'top' | 'bottom' | 'left' | 'right' };

// Module-level drag source — no re-render needed
let currentDragSource: { fromTabset: string; panelId: string } | null = null;

// ---------------------------------------------------------------------------
// Context — DockPanel root 向子组件传递事件回调和拖拽状态
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
  onTabDock?: (info: {
    fromTabset: string;
    panelId: string;
    targetTabset: string;
    position: string;
  }) => void;
  onEdgeDock?: (info: {
    fromTabset: string;
    panelId: string;
    edge: string;
  }) => void;
  dockPreview: DockPreview | null;
  setDockPreview: (p: DockPreview | null) => void;
  setIsDragging: (v: boolean) => void;
}

const DockPanelCtx = createContext<DockPanelContextType>({
  dockPreview: null,
  setDockPreview: () => {},
  setIsDragging: () => {},
});

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
  onTabDock?: (info: {
    fromTabset: string;
    panelId: string;
    targetTabset: string;
    position: string;
  }) => void;
  onEdgeDock?: (info: {
    fromTabset: string;
    panelId: string;
    edge: string;
  }) => void;
  children?: React.ReactNode;
}

export function DockPanel({
  onResize,
  onTabSwitch,
  onTabReorder,
  onTabMove,
  onSplitResize,
  onActionClick,
  onTabDock,
  onEdgeDock,
  children,
}: DockPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dockPreview, setDockPreview] = useState<DockPreview | null>(null);

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
    onTabDock,
    onEdgeDock,
    dockPreview,
    setDockPreview,
    setIsDragging,
  };

  const edges = ['top', 'bottom', 'left', 'right'] as const;

  return (
    <DockPanelCtx.Provider value={ctx}>
      <div
        ref={containerRef}
        className="mutgui-dock-panel"
      >
        {children}

        {/* Edge drop zones */}
        {isDragging && edges.map(edge => (
          <EdgeDropZone
            key={edge}
            edge={edge}
            onEdgeDock={onEdgeDock}
            setDockPreview={setDockPreview}
            dockPreview={dockPreview}
          />
        ))}

        {/* Edge dock overlay */}
        {dockPreview?.type === 'edge-dock' && (
          <div
            className="mutgui-dock-overlay"
            style={{
              background: 'rgba(24, 144, 255, 0.15)',
              zIndex: 99,
              ...edgeOverlayPosition(dockPreview.edge),
            }}
          />
        )}
      </div>
    </DockPanelCtx.Provider>
  );
}

function edgeOverlayPosition(edge: string): React.CSSProperties {
  switch (edge) {
    case 'top': return { top: 0, left: 0, right: 0, height: '50%' };
    case 'bottom': return { bottom: 0, left: 0, right: 0, height: '50%' };
    case 'left': return { top: 0, left: 0, bottom: 0, width: '50%' };
    case 'right': return { top: 0, right: 0, bottom: 0, width: '50%' };
    default: return {};
  }
}

// ---------------------------------------------------------------------------
// EdgeDropZone — 页面边缘停靠触发区
// ---------------------------------------------------------------------------

function EdgeDropZone({
  edge,
  onEdgeDock,
  setDockPreview,
  dockPreview,
}: {
  edge: 'top' | 'bottom' | 'left' | 'right';
  onEdgeDock?: DockPanelProps['onEdgeDock'];
  setDockPreview: (p: DockPreview | null) => void;
  dockPreview: DockPreview | null;
}) {
  const isActive = dockPreview?.type === 'edge-dock' && dockPreview.edge === edge;
  const isH = edge === 'left' || edge === 'right';
  const arrow = { top: '▼', bottom: '▲', left: '►', right: '◄' }[edge];

  const posStyle: React.CSSProperties = isH
    ? { [edge]: 0, top: '50%', transform: 'translateY(-50%)', width: 14, height: 100 }
    : { [edge]: 0, left: '50%', transform: 'translateX(-50%)', width: 100, height: 14 };

  return (
    <div
      style={{
        position: 'absolute',
        ...posStyle,
        background: isActive ? 'rgba(24, 144, 255, 0.5)' : 'rgba(24, 144, 255, 0.25)',
        borderRadius: 3,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 10,
        color: '#fff',
        transition: 'background 0.1s',
      }}
      onDragOver={e => {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'move';
        setDockPreview({ type: 'edge-dock', edge });
      }}
      onDragLeave={() => {
        if (dockPreview?.type === 'edge-dock' && dockPreview.edge === edge) {
          setDockPreview(null);
        }
      }}
      onDrop={e => {
        e.preventDefault();
        e.stopPropagation();
        if (currentDragSource) {
          onEdgeDock?.({
            fromTabset: currentDragSource.fromTabset,
            panelId: currentDragSource.panelId,
            edge,
          });
        }
        setDockPreview(null);
      }}
    >
      {arrow}
    </div>
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
    cursor: isH ? 'col-resize' : 'row-resize',
    ...(isH ? { width: 4 } : { height: 4 }),
  };

  return (
    <div className="mutgui-dock-split">
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
    <div className="mutgui-dock-merged-bar">
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
  onDragEnd,
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
  onDragEnd?: (e: React.DragEvent) => void;
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
    ? '2px solid var(--mutgui-accent)'
    : '2px solid transparent';

  return (
    <div
      className={`mutgui-dock-tab${active ? ' mutgui-dock-tab-active' : ''}`}
      style={{
        padding: vertical ? '8px 6px' : '4px 12px',
        lineHeight: vertical ? 'normal' : '26px',
        flexDirection: vertical ? 'column' : 'row',
        ...indicatorStyle,
      }}
      onClick={onClick}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
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
  const {
    onTabSwitch, onTabReorder, onTabMove, onActionClick,
    onTabDock, dockPreview, setDockPreview, setIsDragging,
  } = useContext(DockPanelCtx);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const isVert = barPosition === 'left' || barPosition === 'right';

  const handleDragStart = (e: React.DragEvent, panelId: string) => {
    const source = { fromTabset: nodeId, panelId };
    currentDragSource = source;
    e.dataTransfer.setData(
      'application/mutgui-tab',
      JSON.stringify({ ...source, collapsed }),
    );
    e.dataTransfer.effectAllowed = 'move';
    setIsDragging(true);
  };

  const handleDragEnd = () => {
    currentDragSource = null;
    setIsDragging(false);
    setDockPreview(null);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIdx(index);
    setDockPreview(null);
  };

  const handleDrop = (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    setDragOverIdx(null);
    setDockPreview(null);
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

  // -- Content area dock detection --

  const handleContentDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIdx(null);

    if (!currentDragSource) return;
    if (currentDragSource.fromTabset === nodeId && tabs.length <= 1) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;

    let position: 'top' | 'bottom' | 'left' | 'right' | 'center';
    if (y < 0.25) position = 'top';
    else if (y > 0.75) position = 'bottom';
    else if (x < 0.25) position = 'left';
    else if (x > 0.75) position = 'right';
    else position = 'center';

    if (position === 'center') {
      setDockPreview({ type: 'tab-move', targetId: nodeId });
    } else {
      setDockPreview({ type: 'panel-dock', targetId: nodeId, position });
    }
  };

  const handleContentDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (!currentDragSource) return;

    const { fromTabset, panelId } = currentDragSource;
    const preview = dockPreview;

    if (preview?.type === 'panel-dock' && preview.targetId === nodeId) {
      onTabDock?.({
        fromTabset, panelId,
        targetTabset: nodeId,
        position: preview.position,
      });
    } else if (preview?.type === 'tab-move' && preview.targetId === nodeId) {
      onTabMove?.({
        fromTabset,
        toTabset: nodeId,
        panelId,
        index: tabs.length,
      });
    }
    setDockPreview(null);
  };

  const handleContentDragLeave = (e: React.DragEvent) => {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    if (dockPreview && 'targetId' in dockPreview && dockPreview.targetId === nodeId) {
      setDockPreview(null);
    }
  };

  // -- Rendering helpers --

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
        flexDirection: isVert ? 'column' : 'row',
        ...(isVert
          ? {
              width: 36,
              ...(barPosition === 'left'
                ? { borderRight: '1px solid var(--mutgui-dock-border, var(--mutgui-border))' }
                : { borderLeft: '1px solid var(--mutgui-dock-border, var(--mutgui-border))' }),
            }
          : {
              height: 36,
              ...(barPosition === 'top'
                ? { borderBottom: '1px solid var(--mutgui-dock-border, var(--mutgui-border))' }
                : { borderTop: '1px solid var(--mutgui-dock-border, var(--mutgui-border))' }),
            }),
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOverIdx(tabs.length);
        setDockPreview(null);
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
            onDragEnd={handleDragEnd}
            onDragOver={(e) => handleDragOver(e, i)}
            onDrop={(e) => handleDrop(e, i)}
            onDragLeave={() => setDragOverIdx(null)}
          />
        ))}
      </div>
      {endActions.map(renderAction)}
    </div>
  );

  const panelPreview = dockPreview?.type === 'panel-dock' && dockPreview.targetId === nodeId
    ? dockPreview.position : null;
  const centerPreview = dockPreview?.type === 'tab-move' && dockPreview.targetId === nodeId;

  const contentArea = (
    <div
      className="mutgui-dock-content"
      onDragOver={handleContentDragOver}
      onDrop={handleContentDrop}
      onDragLeave={handleContentDragLeave}
    >
      {children}

      {/* Panel dock overlay */}
      {panelPreview && (
        <div
          className="mutgui-dock-overlay"
          style={{
            background: 'rgba(24, 144, 255, 0.15)',
            zIndex: 10,
            ...panelOverlayPosition(panelPreview),
          }}
        />
      )}

      {/* Center (tab-move) overlay */}
      {centerPreview && (
        <div
          className="mutgui-dock-overlay"
          style={{
            inset: 0,
            background: 'rgba(24, 144, 255, 0.1)',
            zIndex: 10,
          }}
        />
      )}
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
      style={{ flexDirection: flexDir }}
    >
      {tabBar}
      {contentArea}
    </div>
  );
}

function panelOverlayPosition(position: string): React.CSSProperties {
  switch (position) {
    case 'top': return { top: 0, left: 0, right: 0, height: '50%' };
    case 'bottom': return { bottom: 0, left: 0, right: 0, height: '50%' };
    case 'left': return { top: 0, left: 0, bottom: 0, width: '50%' };
    case 'right': return { top: 0, right: 0, bottom: 0, width: '50%' };
    default: return {};
  }
}
