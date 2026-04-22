// library 构建入口 —— import CSS 让 Vite 产出独立的 dist/styles.css
// 注意：组件 tsx 文件不得 import CSS（防止产物污染），仅此构建入口允许
import './styles/index.css';

export { registerComponents, resolve } from './registry';
export { MutguiView, renderTree } from './renderer';
export type { ComponentSchema } from './renderer';
export {
  ScopeProvider,
  ConnectionProvider,
  useScope,
  useConnection,
  arrayEquals,
} from './context';
export type { ViewPath, MutguiConnection, RenderCallback } from './context';
export { resolvePath } from './resolve-path';
export { VirtualList } from './virtual-list';
export { DockPanel, DockPanelSplit, DockPanelTabSet } from './dock-panel';
