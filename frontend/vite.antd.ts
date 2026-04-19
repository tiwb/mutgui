import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

/**
 * antd 组件库打包配置 — 输出 IIFE，React 标记为 external。
 *
 * 构建：npm run build:antd
 * 产物：../../src/mutgui/static/libs/antd.js
 *
 * 加载顺序：先加载 mutgui.js（暴露 React），再加载 antd.js。
 */
export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/libs/antd.ts'),
      formats: ['iife'],
      name: 'MutguiAntd',
      fileName: () => 'antd.js',
    },
    outDir: resolve(__dirname, '../src/mutgui/static/libs'),
    emptyOutDir: false,
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime'],
      output: {
        globals: {
          'react': 'MutguiApp.React',
          'react-dom': 'MutguiApp.ReactDOM',
          'react/jsx-runtime': 'MutguiApp.jsxRuntime',
        },
      },
    },
    cssCodeSplit: false,
  },
  define: {
    'process.env.NODE_ENV': '"production"',
  },
});
