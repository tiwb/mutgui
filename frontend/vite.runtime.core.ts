import { resolve } from 'node:path';

import { defineLib } from './build-preset';

export default defineLib({
  entry: resolve(__dirname, 'src/core.tsx'),
  outDir: resolve(__dirname, '../src/mutgui/static/libs'),
  outFile: 'mutgui-core.js',
  cssFile: 'mutgui-core.css',
  peers: ['react', 'react-dom/client', 'react/jsx-runtime'],
});
