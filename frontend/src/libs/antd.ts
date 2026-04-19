/**
 * Ant Design 组件库 — 加载时自动注册到 mutgui。
 *
 * 构建为独立 IIFE（vite.antd.ts），React 标记为 external。
 * 浏览器加载此文件后，所有 antd 导出自动可用于后端 $component 引用。
 */
import * as antd from 'antd';

(window as any).MutguiApp.registerComponents({
  __name__: 'antd',
  ...antd,
});
