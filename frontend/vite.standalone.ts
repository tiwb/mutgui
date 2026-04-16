import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

/**
 * 全量打包配置 — 输出单文件 IIFE，包含 React + Ant Design + mutgui renderer。
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
    // 不 external 任何依赖，全量打包
    rollupOptions: {
      external: [],
    },
    cssCodeSplit: false,
  },
  define: {
    'process.env.NODE_ENV': '"production"',
  },
});
