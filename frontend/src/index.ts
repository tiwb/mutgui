// library 构建入口 —— import CSS 让 Vite 产出独立的 dist/styles.css
// 注意：组件 tsx 文件不得 import CSS（防止产物污染），仅此构建入口允许
import './index.css';

export { registerComponents, resolve } from './core/registry';
export { registerCommands, resolveCommand } from './core/commands';
export type { CommandContext, MutguiCommand, CommandSource } from './core/commands';
export { MutguiView, renderTree } from './core/renderer';
export type { ComponentSchema } from './core/renderer';
export {
  ScopeProvider,
  ConnectionProvider,
  useScope,
  useConnection,
  arrayEquals,
} from './core/context';
export type { ViewPath, MutguiConnection, RenderCallback } from './core/context';
export { resolvePath } from './core/resolve-path';
export { VirtualList } from './components/virtual-list';
export { DockPanel, DockPanelSplit, DockPanelTabSet } from './components/dock-panel';
