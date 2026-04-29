import { resolve } from 'node:path';

import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, 'src/boot.ts'),
      formats: ['iife'],
      name: 'MutguiBoot',
      fileName: () => 'boot.js',
    },
    outDir: resolve(__dirname, '../src/mutgui/static'),
    emptyOutDir: false,
    rollupOptions: {
      external: ['@mutgui/core', '@mutgui/antd', '@mutgui/theme-dark', 'react', 'react-dom/client', 'react/jsx-runtime', 'antd'],
    },
    target: 'es2022',
  },
});
