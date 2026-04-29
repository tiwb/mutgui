import { resolve } from 'node:path';

import { defineVendor } from '../build-preset';

const outFile = process.env.MUTGUI_OUT_FILE;
if (!outFile) {
  throw new Error('MUTGUI_OUT_FILE is required');
}

export default defineVendor({
  entry: resolve(__dirname, 'entries/react-jsx-runtime.ts'),
  outDir: resolve(__dirname, '../../src/mutgui/static/vendor'),
  outFile,
});
