export type Side = 'top' | 'bottom' | 'left' | 'right';
export type Align = 'start' | 'center' | 'end';
export type Placement =
  | 'cursor'
  | 'top-start'
  | 'top-center'
  | 'top-end'
  | 'bottom-start'
  | 'bottom-center'
  | 'bottom-end'
  | 'left-start'
  | 'left-end'
  | 'right-start'
  | 'right-end';

export interface Anchor {
  point: { x: number; y: number };
  menuAlign: { x: Align; y: Align };
  flipAxis?: 'x' | 'y';
  flipPoint?: { x?: number; y?: number };
}

export interface LayoutResult {
  left: number;
  top: number;
  effectiveAnchor: Anchor;
  maxHeight?: number;
  maxWidth?: number;
}

interface MenuSize {
  width: number;
  height: number;
}

interface Viewport {
  width: number;
  height: number;
}

interface Position {
  left: number;
  top: number;
}

interface RectLike {
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
}

const DEFAULT_MARGIN = 4;

function resolveRect(triggerRect?: DOMRect): RectLike {
  return triggerRect ?? { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 };
}

function getAlignOffset(size: number, align: Align): number {
  if (align === 'center') return size / 2;
  if (align === 'end') return size;
  return 0;
}

function computeRawPosition(anchor: Anchor, menuSize: MenuSize): Position {
  return {
    left: anchor.point.x - getAlignOffset(menuSize.width, anchor.menuAlign.x),
    top: anchor.point.y - getAlignOffset(menuSize.height, anchor.menuAlign.y),
  };
}

function clampPositionValue(
  value: number,
  size: number,
  viewportSize: number,
  margin: number,
): number {
  const min = margin;
  const max = viewportSize - size - margin;
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

function clampPosition(
  position: Position,
  menuSize: MenuSize,
  viewport: Viewport,
  margin: number,
  axis?: 'x' | 'y',
): Position {
  return {
    left:
      axis === undefined || axis === 'x'
        ? clampPositionValue(position.left, menuSize.width, viewport.width, margin)
        : position.left,
    top:
      axis === undefined || axis === 'y'
        ? clampPositionValue(position.top, menuSize.height, viewport.height, margin)
        : position.top,
  };
}

function getAxisOverflow(
  position: Position,
  menuSize: MenuSize,
  viewport: Viewport,
  axis: 'x' | 'y',
  margin: number,
): number {
  const start = axis === 'x' ? position.left : position.top;
  const size = axis === 'x' ? menuSize.width : menuSize.height;
  const viewportSize = axis === 'x' ? viewport.width : viewport.height;
  const underflow = Math.max(margin - start, 0);
  const overflow = Math.max(start + size - (viewportSize - margin), 0);
  return underflow + overflow;
}

function getAxisSpace(
  point: number,
  align: Align,
  viewportSize: number,
  margin: number,
): number {
  if (align === 'start') return viewportSize - point - margin;
  if (align === 'end') return point - margin;
  return Math.min(point - margin, viewportSize - point - margin);
}

function flipAlign(align: Align): Align {
  if (align === 'center') return 'center';
  return align === 'start' ? 'end' : 'start';
}

function flipAnchor(anchor: Anchor, axis: 'x' | 'y'): Anchor {
  return {
    ...anchor,
    point: {
      x: axis === 'x' ? anchor.flipPoint?.x ?? anchor.point.x : anchor.point.x,
      y: axis === 'y' ? anchor.flipPoint?.y ?? anchor.point.y : anchor.point.y,
    },
    menuAlign: {
      x: axis === 'x' ? flipAlign(anchor.menuAlign.x) : anchor.menuAlign.x,
      y: axis === 'y' ? flipAlign(anchor.menuAlign.y) : anchor.menuAlign.y,
    },
  };
}

function anchorFromPosition(anchor: Anchor, menuSize: MenuSize, position: Position): Anchor {
  return {
    ...anchor,
    point: {
      x: position.left + getAlignOffset(menuSize.width, anchor.menuAlign.x),
      y: position.top + getAlignOffset(menuSize.height, anchor.menuAlign.y),
    },
  };
}

function getRenderedMenuSize(menuSize: MenuSize, viewport: Viewport, margin: number): {
  renderedSize: MenuSize;
  maxWidth?: number;
  maxHeight?: number;
} {
  const availableWidth = Math.max(viewport.width - margin * 2, 0);
  const availableHeight = Math.max(viewport.height - margin * 2, 0);
  return {
    renderedSize: {
      width: Math.min(menuSize.width, availableWidth),
      height: Math.min(menuSize.height, availableHeight),
    },
    maxWidth: menuSize.width > availableWidth ? availableWidth : undefined,
    maxHeight: menuSize.height > availableHeight ? availableHeight : undefined,
  };
}

function resolveCursorFlip(anchor: Anchor, menuSize: MenuSize, viewport: Viewport, margin: number): Anchor {
  let next = anchor;
  const rightSpace = viewport.width - anchor.point.x - margin;
  const leftSpace = anchor.point.x - margin;
  const bottomSpace = viewport.height - anchor.point.y - margin;
  const topSpace = anchor.point.y - margin;

  if (
    next.menuAlign.x === 'start' &&
    rightSpace < menuSize.width &&
    leftSpace > rightSpace
  ) {
    next = {
      ...next,
      menuAlign: { ...next.menuAlign, x: 'end' },
    };
  }

  if (
    next.menuAlign.y === 'start' &&
    bottomSpace < menuSize.height &&
    topSpace > bottomSpace
  ) {
    next = {
      ...next,
      menuAlign: { ...next.menuAlign, y: 'end' },
    };
  }

  return next;
}

export function resolveAnchor(
  placement: Placement,
  triggerRect: DOMRect | undefined,
  cursorPoint: { x: number; y: number } | undefined,
): Anchor {
  if (placement === 'cursor') {
    return {
      point: { x: cursorPoint?.x ?? 0, y: cursorPoint?.y ?? 0 },
      menuAlign: { x: 'start', y: 'start' },
    };
  }

  const rect = resolveRect(triggerRect);
  const centerX = rect.left + rect.width / 2;

  switch (placement) {
    case 'bottom-start':
      return {
        point: { x: rect.left, y: rect.bottom },
        menuAlign: { x: 'start', y: 'start' },
        flipAxis: 'y',
        flipPoint: { y: rect.top },
      };
    case 'bottom-center':
      return {
        point: { x: centerX, y: rect.bottom },
        menuAlign: { x: 'center', y: 'start' },
        flipAxis: 'y',
        flipPoint: { y: rect.top },
      };
    case 'bottom-end':
      return {
        point: { x: rect.right, y: rect.bottom },
        menuAlign: { x: 'end', y: 'start' },
        flipAxis: 'y',
        flipPoint: { y: rect.top },
      };
    case 'top-start':
      return {
        point: { x: rect.left, y: rect.top },
        menuAlign: { x: 'start', y: 'end' },
        flipAxis: 'y',
        flipPoint: { y: rect.bottom },
      };
    case 'top-center':
      return {
        point: { x: centerX, y: rect.top },
        menuAlign: { x: 'center', y: 'end' },
        flipAxis: 'y',
        flipPoint: { y: rect.bottom },
      };
    case 'top-end':
      return {
        point: { x: rect.right, y: rect.top },
        menuAlign: { x: 'end', y: 'end' },
        flipAxis: 'y',
        flipPoint: { y: rect.bottom },
      };
    case 'right-start':
      return {
        point: { x: rect.right, y: rect.top },
        menuAlign: { x: 'start', y: 'start' },
        flipAxis: 'x',
        flipPoint: { x: rect.left },
      };
    case 'right-end':
      return {
        point: { x: rect.right, y: rect.bottom },
        menuAlign: { x: 'start', y: 'end' },
        flipAxis: 'x',
        flipPoint: { x: rect.left },
      };
    case 'left-start':
      return {
        point: { x: rect.left, y: rect.top },
        menuAlign: { x: 'end', y: 'start' },
        flipAxis: 'x',
        flipPoint: { x: rect.right },
      };
    case 'left-end':
      return {
        point: { x: rect.left, y: rect.bottom },
        menuAlign: { x: 'end', y: 'end' },
        flipAxis: 'x',
        flipPoint: { x: rect.right },
      };
  }
}

export function computeMenuLayout(input: {
  anchor: Anchor;
  menuSize: MenuSize;
  viewport: Viewport;
  margin?: number;
}): LayoutResult {
  const margin = input.margin ?? DEFAULT_MARGIN;
  const { renderedSize, maxHeight, maxWidth } = getRenderedMenuSize(
    input.menuSize,
    input.viewport,
    margin,
  );

  let anchor = { ...input.anchor, point: { ...input.anchor.point }, menuAlign: { ...input.anchor.menuAlign } };

  if (anchor.flipAxis) {
    const currentPosition = computeRawPosition(anchor, renderedSize);
    const currentOverflow = getAxisOverflow(
      currentPosition,
      renderedSize,
      input.viewport,
      anchor.flipAxis,
      margin,
    );

    if (currentOverflow > 0) {
      const flippedAnchor = flipAnchor(anchor, anchor.flipAxis);
      const currentSpace = getAxisSpace(
        anchor.flipAxis === 'x' ? anchor.point.x : anchor.point.y,
        anchor.flipAxis === 'x' ? anchor.menuAlign.x : anchor.menuAlign.y,
        anchor.flipAxis === 'x' ? input.viewport.width : input.viewport.height,
        margin,
      );
      const flippedSpace = getAxisSpace(
        anchor.flipAxis === 'x' ? flippedAnchor.point.x : flippedAnchor.point.y,
        anchor.flipAxis === 'x' ? flippedAnchor.menuAlign.x : flippedAnchor.menuAlign.y,
        anchor.flipAxis === 'x' ? input.viewport.width : input.viewport.height,
        margin,
      );
      const flippedOverflow = getAxisOverflow(
        computeRawPosition(flippedAnchor, renderedSize),
        renderedSize,
        input.viewport,
        anchor.flipAxis,
        margin,
      );

      if (flippedSpace > currentSpace && flippedOverflow <= currentOverflow) {
        anchor = flippedAnchor;
      }
    }
  } else {
    anchor = resolveCursorFlip(anchor, renderedSize, input.viewport, margin);
  }

  let position = computeRawPosition(anchor, renderedSize);
  if (anchor.flipAxis) {
    const crossAxis = anchor.flipAxis === 'x' ? 'y' : 'x';
    position = clampPosition(position, renderedSize, input.viewport, margin, crossAxis);
  } else {
    position = clampPosition(position, renderedSize, input.viewport, margin);
  }

  position = clampPosition(position, renderedSize, input.viewport, margin);

  return {
    left: position.left,
    top: position.top,
    effectiveAnchor: anchorFromPosition(anchor, renderedSize, position),
    maxHeight,
    maxWidth,
  };
}

export function recomputePosition(
  anchor: Anchor,
  menuSize: MenuSize,
  viewport: Viewport,
  margin = DEFAULT_MARGIN,
): { left: number; top: number } {
  const { renderedSize } = getRenderedMenuSize(menuSize, viewport, margin);
  const position = computeRawPosition(anchor, renderedSize);
  return clampPosition(position, renderedSize, viewport, margin);
}
