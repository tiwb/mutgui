import { resolve } from 'node:path';

import { defineLib } from './build-preset';

export default defineLib({
  entry: resolve(__dirname, 'src/integrations/antd.ts'),
  outDir: resolve(__dirname, '../src/mutgui/static/libs'),
  outFile: 'mutgui-antd.js',
  peers: ['react', 'react/jsx-runtime', 'antd', '@mutgui/core'],
});
