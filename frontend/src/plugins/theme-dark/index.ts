import React from 'react';
import darkCss from './dark.css?inline';
import { ConfigProvider, theme as antdTheme } from 'antd';
import type { MutguiPlugin } from '@mutgui/core';

const darkAntdTheme = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    colorPrimary: '#007acc',
  },
};

const plugin: MutguiPlugin = (ctx): void => {
  ctx.addCss(darkCss);
  ctx.addBodyClass('mutgui-dark');
  ctx.wrapRoot((children) =>
    React.createElement(ConfigProvider, { theme: darkAntdTheme }, children as never),
  );
};

export default plugin;
