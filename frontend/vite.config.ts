import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: resolve(__dirname, 'src/index.ts'),
      formats: ['es'],
      fileName: 'index',
    },
    rollupOptions: {
      external: ['react', 'react-dom/client', 'react/jsx-runtime', 'antd'],
      output: {
        // CSS 独立产出为 dist/styles.css（而非 index.css 默认名）
        assetFileNames: (asset) => {
          if (asset.name && asset.name.endsWith('.css')) return 'styles.css';
          return 'assets/[name].[hash][extname]';
        },
      },
    },
    cssCodeSplit: false,
    target: 'es2022',
  },
});
