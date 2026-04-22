import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

/**
 * mutgui 暗色主题 plugin 构建配置 — 输出 IIFE。
 * React / antd 标记为 external,从 MutguiApp 全局获取。
 *
 * 构建:npm run build:theme-dark
 * 产物:../src/mutgui/static/mutgui-theme-dark.js
 *
 * 加载顺序:先 mutgui.js(暴露 React),再 mutgui-antd.js(注册 antd 组件),
 *        最后 mutgui-theme-dark.js。
 */
export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/plugins/theme-dark/index.ts'),
      formats: ['iife'],
      name: 'MutguiThemeDarkBundle',
      fileName: () => 'mutgui-theme-dark.js',
    },
    outDir: resolve(__dirname, '../src/mutgui/static'),
    emptyOutDir: false,
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime', 'antd'],
      output: {
        globals: {
          'react': 'MutguiApp.React',
          'react-dom': 'MutguiApp.ReactDOM',
          'react/jsx-runtime': 'MutguiApp.jsxRuntime',
          'antd': 'MutguiApp.antd',
        },
      },
    },
    cssCodeSplit: false,
  },
  define: {
    'process.env.NODE_ENV': '"production"',
  },
});
