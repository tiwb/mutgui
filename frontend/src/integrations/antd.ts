/**
 * Ant Design 组件库 — 加载时自动注册到 mutgui。
 *
 * 构建为独立 IIFE（vite.antd.ts），React 标记为 external。
 * 浏览器加载此文件后:
 *   - 所有 antd 组件注册到 mutgui,可通过 $component 引用
 *   - antd 完整命名空间挂到 window.MutguiApp.antd,供其他 plugin
 *     (如 mutgui-theme-dark)引用 antd 的 theme / ConfigProvider 等
 */
import * as antd from 'antd';

const app = (window as unknown as Record<string, unknown>).MutguiApp as Record<string, unknown>;
app.antd = antd;
app.registerComponents = app.registerComponents ?? (() => undefined);
(app.registerComponents as (obj: unknown) => void)({
  __name__: 'antd',
  ...antd,
});
