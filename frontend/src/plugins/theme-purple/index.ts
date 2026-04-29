import React from 'react';
import { ConfigProvider, theme as antdTheme } from 'antd';
import type { MutguiPlugin } from '@mutgui/core';

const purpleCss = `
body.mutgui-purple,
body.mutgui-purple .mutgui-root {
  color-scheme: dark;
  --mutgui-accent: oklch(0.65 0.22 310);
  --mutgui-bg: oklch(0.20 0.04 300);
  --mutgui-surface: oklch(0.26 0.05 300);
  --mutgui-text: oklch(0.92 0.02 310);
  --mutgui-text-dim: oklch(0.70 0.04 310);
  --mutgui-border: oklch(0.40 0.06 300);
}

body.mutgui-purple {
  background: var(--mutgui-bg);
  color: var(--mutgui-text);
}
`;

const purpleAntdTheme = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    colorPrimary: '#b07cff',
  },
};

const plugin: MutguiPlugin = (ctx): void => {
  ctx.addCss(purpleCss);
  ctx.addBodyClass('mutgui-purple');
  ctx.wrapRoot((children) =>
    React.createElement(ConfigProvider, { theme: purpleAntdTheme }, children as never),
  );
};

export default plugin;
