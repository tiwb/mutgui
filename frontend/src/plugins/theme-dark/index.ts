/**
 * mutgui 内置暗色主题 plugin
 *
 * 这是一个 MutguiPlugin 的参考实现,用户自己写主题 plugin 可以直接参照此文件结构:
 *   1. 准备一份 CSS(覆盖 token + body 背景)
 *   2. 选一个 body class 作为激活标识
 *   3. 准备一份 antd ConfigProvider theme(算法 + token)
 *   4. plugin 函数调用 ctx 三方法
 *
 * 构建产物:mutgui-theme-dark.js (IIFE),挂 window.MutguiThemeDark
 * 加载后零副作用,消费者主动把 MutguiThemeDark 放进 mount 的 plugins 数组才生效。
 */
import darkCss from './dark.css?inline';
import { ConfigProvider, theme as antdTheme } from 'antd';

// antd ConfigProvider 的 theme 配置
// token.colorPrimary 用 accent 的大致对应值(antd token 是 JS,拿不到 CSS var)
const darkAntdTheme = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    colorPrimary: '#4a8ef0',
  },
};

type RootWrapper = (children: unknown) => unknown;
interface PluginContext {
  addCss(css: string): void;
  addBodyClass(className: string): void;
  wrapRoot(wrap: RootWrapper): void;
}

// MutguiApp 暴露的 React 实例(避免 plugin 自己 bundle React)
declare global {
  interface Window {
    MutguiApp: {
      React: {
        createElement: (type: unknown, props?: unknown, ...children: unknown[]) => unknown;
      };
    };
    MutguiThemeDark: (ctx: PluginContext) => void;
  }
}

const plugin = (ctx: PluginContext): void => {
  ctx.addCss(darkCss);
  ctx.addBodyClass('mutgui-dark');
  ctx.wrapRoot((children) =>
    window.MutguiApp.React.createElement(ConfigProvider, { theme: darkAntdTheme }, children as never),
  );
};

window.MutguiThemeDark = plugin;
