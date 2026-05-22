/**
 * mutgui 菜单系统 — 前端实现。
 *
 * 数据流：
 *   - 用户触发事件 → createMenuTriggerHandler：
 *       1. 阻止默认行为
 *       2. 记录触发位置 + placement → pendingTriggers[menuKey]
 *       3. 发事件给后端
 *   - 后端创建 MenuView → push wire_tree（viewId 含 "$menu:..." 前缀）
 *   - MutguiView 检测到 $menu: 前缀 → 用 Menu 容器包装内容
 *   - Menu mount 时从 pendingTriggers 取出位置信息
 *   - Menu unmount（后端 close 后 push 不含 $view 引用的 tree → React 卸载）
 *
 * 关闭：
 *   - document pointerdown / ESC 监听
 *   - 关闭时直接发 $close 事件给后端（不修改前端状态）
 *   - 后端 push 新 tree → React 自动卸载 Menu
 */
import { createPortal } from 'react-dom';
import { useEffect, useState, useRef, useLayoutEffect } from 'react';
import { resolvePath } from '../core/resolve-path';
import type { ViewPath, MutguiConnection } from '../core/context';
import {
  computeMenuLayout,
  recomputePosition,
  resolveAnchor,
  type Anchor,
  type Placement,
} from './menu-layout';

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

export interface TriggerInfo {
  placement: Placement;
  x: number;
  y: number;
  triggerRect?: DOMRect;
  parentMenuId?: string;
}

// ---------------------------------------------------------------------------
// 触发信息暂存 — 模块级
// ---------------------------------------------------------------------------

/**
 * 触发信息暂存。Trigger 时写入"待打开"，Menu mount 时取出。
 * 由于触发到 Menu mount 之间只有一次 push 来回，且同时刻只有一棵菜单树，
 * 用单变量足够。如果 Menu mount 时没有 pending（如服务端主动 push 一个菜单），
 * 用默认位置（视口中心）。
 */
let pendingTrigger: TriggerInfo | null = null;

/**
 * 取走当前 pendingTrigger 并清空。供 MutguiView 在看到菜单 viewId 那一刻
 * 同步消费，避免 Menu mount 延后导致 trigger 被后续触发覆盖。
 */
export function takePendingMenuTrigger(): TriggerInfo | null {
  const t = pendingTrigger;
  pendingTrigger = null;
  return t;
}

const MENU_JUST_OPENED_ATTR = 'data-menu-just-opened';
let menuJustOpenedToken = 0;

function markMenuJustOpened(): () => void {
  if (typeof document === 'undefined' || !document.body) {
    return () => {};
  }

  menuJustOpenedToken += 1;
  const token = menuJustOpenedToken;
  const clear = () => {
    if (menuJustOpenedToken !== token) return;
    document.body.removeAttribute(MENU_JUST_OPENED_ATTR);
  };
  const handlePointerMove = () => {
    clear();
  };

  document.body.setAttribute(MENU_JUST_OPENED_ATTR, '');
  window.addEventListener('pointermove', handlePointerMove, {
    capture: true,
    once: true,
  });

  return () => {
    if (menuJustOpenedToken !== token) return;
    window.removeEventListener('pointermove', handlePointerMove, true);
    clear();
  };
}

/** 菜单 ID → 实际触发信息（Menu mount 时记录，关闭时清理）。 */
const activeTriggers = new Map<string, TriggerInfo>();

// ---------------------------------------------------------------------------
// 关闭逻辑
// ---------------------------------------------------------------------------

/** 通知后端关闭某个菜单（仅发事件，不改前端状态）。 */
function sendCloseEvent(
  conn: MutguiConnection,
  menuPath: ViewPath,
) {
  conn.send(
    JSON.stringify({
      source: [...menuPath, ''],
      event: '$close',
      data: {},
    }),
  );
}

/** 关闭所有活跃菜单（DOM 上能看到的）。 */
function closeAllVisibleMenus() {
  const els = document.querySelectorAll('.mutgui-menu');
  els.forEach((el) => {
    const closeFn = (el as HTMLElement & { __close?: () => void }).__close;
    if (closeFn) closeFn();
  });
}

/** 关闭最深的菜单（ESC 用）。 */
function closeDeepestMenu() {
  const els = document.querySelectorAll('.mutgui-menu');
  if (els.length === 0) return;
  const last = els[els.length - 1] as HTMLElement & { __close?: () => void };
  if (last.__close) last.__close();
}

/** 检查 DOM 节点是否在任何活跃菜单内。 */
export function isInsideAnyMenu(node: Node): boolean {
  const menus = document.querySelectorAll('.mutgui-menu');
  for (const el of menus) {
    if (el.contains(node)) return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// 全局关闭监听 — pointerdown / ESC
// ---------------------------------------------------------------------------

let listenersInstalled = false;

function ensureGlobalListeners() {
  if (listenersInstalled) return;
  listenersInstalled = true;

  document.addEventListener('pointerdown', (e) => {
    if (document.querySelectorAll('.mutgui-menu').length === 0) return;
    const target = e.target as Node | null;
    if (target && !isInsideAnyMenu(target)) {
      closeAllVisibleMenus();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (document.querySelectorAll('.mutgui-menu').length === 0) return;
    if (e.key === 'Escape') {
      closeDeepestMenu();
    }
  });
}

// ---------------------------------------------------------------------------
// 触发处理 — 由 renderer.tsx 调用
// ---------------------------------------------------------------------------

/**
 * 创建 menu trigger 事件处理函数。
 *
 * 区别于普通 createHandler：不立即作为 React 事件返回值消费，而是：
 * 1. 阻止默认行为（如 contextmenu 弹出浏览器原生菜单）
 * 2. 提取 context（resolvePath 同普通 handler）
 * 3. 记录触发位置 + placement → pendingTrigger
 * 4. 发事件到后端，后端创建 MenuView
 */
export function createMenuTriggerHandler(
  spec: Record<string, unknown>,
  scope: ViewPath,
  componentId: string | number,
  eventName: string,
  conn: MutguiConnection,
) {
  const handlerId = spec.$handler as number;
  const placement = (spec.placement as Placement) ?? 'cursor';

  const argPaths = (spec.args || []) as string[];
  const kwargPaths = (spec.kwargs || {}) as Record<string, string>;
  const source = [...scope, componentId];

  return (...args: unknown[]) => {
    const evt = args[0] as Event | undefined;
    evt?.preventDefault?.();

    let trigger: TriggerInfo;
    if (placement === 'cursor') {
      const me = evt as MouseEvent | undefined;
      trigger = {
        placement,
        x: me?.clientX ?? 0,
        y: me?.clientY ?? 0,
      };
    } else {
      const target = evt?.currentTarget as Element | undefined;
      const rect = target?.getBoundingClientRect?.();
      trigger = rect
        ? {
            placement,
            x: rect.left,
            y: rect.top,
            triggerRect: rect,
          }
        : { placement, x: 0, y: 0 };
    }

    // 检测父菜单
    const targetEl = evt?.target as Node | null;
    if (targetEl) {
      const menus = document.querySelectorAll('.mutgui-menu');
      for (const el of menus) {
        if (el.contains(targetEl)) {
          trigger.parentMenuId = (el as HTMLElement).dataset.menuId;
          break;
        }
      }
    }

    pendingTrigger = trigger;

    // 触发新菜单时关闭非父链上的所有现有菜单
    const els = document.querySelectorAll('.mutgui-menu');
    els.forEach((el) => {
      const id = (el as HTMLElement).dataset.menuId;
      if (!id) return;
      // 父链上的菜单不关
      let cur: string | undefined = trigger.parentMenuId;
      while (cur) {
        if (cur === id) return;
        cur = activeTriggers.get(cur)?.parentMenuId;
      }
      const closeFn = (el as HTMLElement & { __close?: () => void }).__close;
      if (closeFn) closeFn();
    });

    const extractedArgs = argPaths.map((p) => resolvePath(args, p));
    const extractedKwargs: Record<string, unknown> = {};
    for (const [k, path] of Object.entries(kwargPaths)) {
      extractedKwargs[k] = resolvePath(args, path);
    }
    const data: Record<string, unknown> = { ...extractedKwargs };
    if (extractedArgs.length > 0) {
      data.$args = extractedArgs;
    }

    conn.send(JSON.stringify({ source, event: eventName, handlerId, data }));
  };
}

// ---------------------------------------------------------------------------
// Menu 容器组件 — portal + 定位
// ---------------------------------------------------------------------------

interface MenuProps {
  menuId: string;
  conn: MutguiConnection;
  viewPath: ViewPath;
  /**
   * MutguiView 在创建菜单分支时同步取走的 trigger。
   * Menu 内部优先使用，没有则 fallback 到全局 pendingTrigger / DEFAULT_TRIGGER
   * 兼容意外路径（如直接 mount Menu 而非走 MutguiView）。
   */
  initialTrigger?: TriggerInfo | null;
  children?: React.ReactNode;
}

const HIDDEN_POSITION = -100000;

const DEFAULT_TRIGGER: TriggerInfo = {
  placement: 'cursor',
  x: window.innerWidth / 2,
  y: window.innerHeight / 2,
};

export function Menu({ menuId, conn, viewPath, initialTrigger, children }: MenuProps) {
  ensureGlobalListeners();

  const menuRef = useRef<HTMLDivElement | null>(null);
  const [layoutReady, setLayoutReady] = useState(false);

  // 取出触发信息（mount 时一次性）
  // 优先用 MutguiView 同步 take 来的 initialTrigger；fallback 到全局
  // pendingTrigger / DEFAULT_TRIGGER 兼容意外路径。
  const triggerRef = useRef<TriggerInfo | null>(null);
  if (triggerRef.current === null) {
    triggerRef.current = initialTrigger ?? pendingTrigger ?? DEFAULT_TRIGGER;
    pendingTrigger = null;
    activeTriggers.set(menuId, triggerRef.current);
  }
  const trigger = triggerRef.current;

  const [pos, setPos] = useState<{ left: number; top: number }>({
    left: HIDDEN_POSITION,
    top: HIDDEN_POSITION,
  });
  const [sizeLimit, setSizeLimit] = useState<{ maxHeight?: number; maxWidth?: number }>({});
  const effectiveAnchorRef = useRef<Anchor | null>(null);

  // 关闭函数：发 $close 给后端，后端 push 新 tree 自动卸载
  const closeRef = useRef<() => void>(() => {
    sendCloseEvent(conn, viewPath);
  });
  closeRef.current = () => {
    sendCloseEvent(conn, viewPath);
  };

  // 暴露关闭函数到 DOM 节点（供全局 listener 调用）
  useEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    (el as HTMLElement & { __close?: () => void }).__close = () => closeRef.current();
    return () => {
      (el as HTMLElement & { __close?: () => void }).__close = undefined;
    };
  }, []);

  // 卸载时清理 activeTriggers
  useEffect(() => {
    return () => {
      activeTriggers.delete(menuId);
    };
  }, [menuId]);

  useEffect(() => {
    return markMenuJustOpened();
  }, [menuId]);

  // mount 时锁定 anchor + 视口约束
  useLayoutEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const anchor = resolveAnchor(
      trigger.placement,
      trigger.triggerRect,
      trigger.placement === 'cursor' ? { x: trigger.x, y: trigger.y } : undefined,
    );
    const naturalRect = el.getBoundingClientRect();
    const layout = computeMenuLayout({
      anchor,
      menuSize: { width: naturalRect.width, height: naturalRect.height },
      viewport,
    });
    effectiveAnchorRef.current = layout.effectiveAnchor;

    if (layout.maxHeight === undefined) {
      el.style.removeProperty('max-height');
    } else {
      el.style.maxHeight = `${layout.maxHeight}px`;
    }
    if (layout.maxWidth === undefined) {
      el.style.removeProperty('max-width');
    } else {
      el.style.maxWidth = `${layout.maxWidth}px`;
    }
    el.style.overflow = 'auto';

    const constrainedRect = el.getBoundingClientRect();
    const finalPos = recomputePosition(
      layout.effectiveAnchor,
      { width: constrainedRect.width, height: constrainedRect.height },
      viewport,
    );
    el.style.left = `${finalPos.left}px`;
    el.style.top = `${finalPos.top}px`;
    el.style.visibility = 'visible';

    setPos((prev) =>
      prev.left === finalPos.left && prev.top === finalPos.top
        ? prev
        : { left: finalPos.left, top: finalPos.top },
    );
    setSizeLimit((prev) =>
      prev.maxHeight === layout.maxHeight && prev.maxWidth === layout.maxWidth
        ? prev
        : { maxHeight: layout.maxHeight, maxWidth: layout.maxWidth },
    );
    setLayoutReady(true);
  }, [trigger]);

  // 尺寸变化时只按锁定 anchor 重算位置，不重新 flip
  useEffect(() => {
    const el = menuRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver(() => {
      const anchor = effectiveAnchorRef.current;
      if (!anchor) return;
      const rect = el.getBoundingClientRect();
      const next = recomputePosition(
        anchor,
        { width: rect.width, height: rect.height },
        { width: window.innerWidth, height: window.innerHeight },
      );
      el.style.left = `${next.left}px`;
      el.style.top = `${next.top}px`;
      setPos((prev) =>
        prev.left === next.left && prev.top === next.top ? prev : next,
      );
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return createPortal(
    <div
      ref={menuRef}
      className="mutgui-menu mutgui-scrollbar"
      data-menu-id={menuId}
      onPointerDownCapture={(e) => {
        e.stopPropagation();
      }}
      style={{
        left: pos.left,
        top: pos.top,
        maxHeight: sizeLimit.maxHeight,
        maxWidth: sizeLimit.maxWidth,
        overflow: 'auto',
        visibility: layoutReady ? 'visible' : 'hidden',
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Menu.Item — 菜单项
// ---------------------------------------------------------------------------

interface MenuItemProps {
  label?: React.ReactNode;
  icon?: React.ReactNode;
  shortcut?: string;
  disabled?: boolean;
  checked?: boolean;
  hasSubmenu?: boolean;
  closeOnClick?: boolean;
  onClick?: (...args: unknown[]) => void;
  onMouseEnter?: (...args: unknown[]) => void;
  children?: React.ReactNode;
}

export function MenuItem({
  label,
  icon,
  shortcut,
  disabled,
  checked,
  hasSubmenu,
  closeOnClick = true,
  onClick,
  onMouseEnter,
  children,
}: MenuItemProps) {
  const handleClick = (e: React.MouseEvent) => {
    if (disabled) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    onClick?.(e);
    if (closeOnClick && !hasSubmenu) {
      closeAllVisibleMenus();
    }
  };

  return (
    <div
      className={`mutgui-menu-item${disabled ? ' disabled' : ''}${
        checked ? ' checked' : ''
      }`}
      onClick={handleClick}
      onMouseEnter={onMouseEnter}
      role="menuitem"
      aria-disabled={disabled || undefined}
    >
      <span className="mutgui-menu-icon">{checked ? '✓' : icon ?? null}</span>
      <span className="mutgui-menu-label">{label ?? children}</span>
      {shortcut && <span className="mutgui-menu-shortcut">{shortcut}</span>}
      {hasSubmenu && <span className="mutgui-menu-submenu-arrow">▶</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Menu.Divider
// ---------------------------------------------------------------------------

export function MenuDivider() {
  return <div className="mutgui-menu-divider" role="separator" />;
}

// ---------------------------------------------------------------------------
// 工具：判断 viewId 是否为菜单
// ---------------------------------------------------------------------------

export function isMenuViewId(viewId: string | number | undefined): boolean {
  return typeof viewId === 'string' && viewId.startsWith('$menu:');
}
