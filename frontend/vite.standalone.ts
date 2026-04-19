import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

/**
 * 核心打包配置 — 输出 IIFE，包含 React + mutgui 渲染器，不含组件库。
 *
 * 构建：npm run build:standalone
 * 产物：../../src/mutgui/static/mutgui.js
 */
export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/standalone.tsx'),
      formats: ['iife'],
      name: 'MutguiApp',
      fileName: () => 'mutgui.js',
    },
    outDir: resolve(__dirname, '../src/mutgui/static'),
    emptyOutDir: false,
    rollupOptions: {
      external: ['antd'],
    },
    cssCodeSplit: false,
  },
  define: {
    'process.env.NODE_ENV': '"production"',
  },
});
