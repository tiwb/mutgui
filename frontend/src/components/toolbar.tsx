/**
 * mutgui Toolbar 系统 — 前端组件实现。
 *
 * 组件：
 *   - Toolbar          — 整体容器（start/spacer/end 三栏布局）
 *   - ToolbarButton    — 按钮（图标+文字+tooltip+checked+disabled+交互态）
 *   - ToolbarSplitButton — 分离按钮（主动作 + 下拉箭头）
 *   - ToolbarDropdown  — 纯下拉按钮
 *   - ToolbarDivider   — 分组分隔线
 */

import { type ReactNode } from 'react';
import './toolbar.css';

// ---------------------------------------------------------------------------
// Toolbar — 容器
// ---------------------------------------------------------------------------

interface ToolbarProps {
  children?: ReactNode;
}

export function Toolbar({ children }: ToolbarProps) {
  const childArray = Array.isArray(children) ? children : [children];

  return (
    <div
      className="mutgui-toolbar"
      role="toolbar"
    >
      {childArray}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolbarSection / ToolbarSpacer — 内部布局原语
// ---------------------------------------------------------------------------

interface ToolbarSectionProps {
  children?: ReactNode;
}

export function ToolbarSection({ children }: ToolbarSectionProps) {
  return (
    <div className="mutgui-toolbar-section">
      {children}
    </div>
  );
}

export function ToolbarSpacer() {
  return <div className="mutgui-toolbar-spacer" />;
}

// ---------------------------------------------------------------------------
// ToolbarButton — 核心按钮
// ---------------------------------------------------------------------------

interface ToolbarButtonProps {
  label: string;
  icon?: string | null;
  tooltip?: string | null;
  shortcut?: string | null;
  disabled?: boolean;
  checked?: boolean;
  labelMode?: 'always' | 'icon-only' | 'auto';
  showArrow?: boolean;
  arrow?: string;
  leftRounded?: boolean;
  rightRounded?: boolean;
  onClick?: (...args: unknown[]) => void;
  children?: ReactNode;
}

export function ToolbarButton({
  label,
  icon,
  tooltip,
  shortcut,
  disabled = false,
  checked = false,
  labelMode = 'always',
  showArrow = false,
  arrow = '\u25BE',   // ▾
  leftRounded = true,
  rightRounded = true,
  onClick,
  children,
}: ToolbarButtonProps) {
  const title = buildTitle(tooltip, shortcut);

  // label 显示策略
  const effectiveMode = labelMode === 'auto' ? 'always' : labelMode;
  const showIcon = icon && (effectiveMode === 'always' || (effectiveMode === 'icon-only'));
  const showLabel = effectiveMode === 'always' || (effectiveMode === 'icon-only' && !icon);

  const classNames = [
    'mutgui-toolbar-button',
    checked && 'checked',
    !leftRounded && 'no-left-radius',
    !rightRounded && 'no-right-radius',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      type="button"
      className={classNames}
      title={title || undefined}
      disabled={disabled}
      onClick={onClick}
    >
      {showIcon && icon}
      {showLabel && <span className="mutgui-toolbar-button-label">{label}</span>}
      {showArrow && <span className="mutgui-toolbar-button-arrow">{arrow}</span>}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// ToolbarSplitButton — 分离按钮
// ---------------------------------------------------------------------------

interface ToolbarSplitButtonProps {
  label: string;
  icon?: string | null;
  tooltip?: string | null;
  shortcut?: string | null;
  disabled?: boolean;
  checked?: boolean;
  labelMode?: 'always' | 'icon-only' | 'auto';
  arrow?: string;
  mainOnClick?: (...args: unknown[]) => void;
  menuOnClick?: (...args: unknown[]) => void;
  mainTooltip?: string | null;   // 主按钮覆写 tooltip（可选）
  menuTooltip?: string | null;   // 箭头按钮 tooltip（可选）
}

export function ToolbarSplitButton({
  label,
  icon,
  tooltip,
  shortcut,
  disabled = false,
  checked = false,
  labelMode = 'always',
  arrow = '\u25BE',
  mainOnClick,
  menuOnClick,
}: ToolbarSplitButtonProps) {
  return (
    <div className="mutgui-toolbar-split">
      <ToolbarButton
        label={label}
        icon={icon}
        tooltip={tooltip}
        shortcut={shortcut}
        disabled={disabled}
        checked={checked}
        labelMode={labelMode}
        leftRounded={true}
        rightRounded={false}
        onClick={mainOnClick}
      />
      <ToolbarButton
        label={arrow}
        icon={null}
        tooltip={null}
        shortcut={null}
        disabled={false}           // 箭头始终可用
        checked={false}
        labelMode="always"
        leftRounded={false}
        rightRounded={true}
        onClick={menuOnClick}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolbarDropdown — 纯下拉按钮
// ---------------------------------------------------------------------------

interface ToolbarDropdownProps {
  label: string;
  icon?: string | null;
  tooltip?: string | null;
  shortcut?: string | null;
  disabled?: boolean;
  checked?: boolean;
  labelMode?: 'always' | 'icon-only' | 'auto';
  arrow?: string;
  onClick?: (...args: unknown[]) => void;
}

export function ToolbarDropdown({
  label,
  icon,
  tooltip,
  shortcut,
  disabled = false,
  checked = false,
  labelMode = 'always',
  arrow = '\u25BE',
  onClick,
}: ToolbarDropdownProps) {
  return (
    <ToolbarButton
      label={label}
      icon={icon}
      tooltip={tooltip}
      shortcut={shortcut}
      disabled={disabled}
      checked={checked}
      labelMode={labelMode}
      showArrow={true}
      arrow={arrow}
      onClick={onClick}
    />
  );
}

// ---------------------------------------------------------------------------
// ToolbarDivider — 分组分隔线
// ---------------------------------------------------------------------------

export function ToolbarDivider() {
  return <div className="mutgui-toolbar-divider" role="separator" aria-hidden={true} />;
}

// ---------------------------------------------------------------------------
// 内部工具
// ---------------------------------------------------------------------------

function buildTitle(
  tooltip: string | null | undefined,
  shortcut: string | null | undefined,
): string | null {
  if (tooltip && shortcut) return `${tooltip} (${shortcut})`;
  if (tooltip) return tooltip;
  if (shortcut) return shortcut;
  return null;
}
