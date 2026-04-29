import { defineFrontendProject } from './build-preset.mjs';

export default defineFrontendProject({
  packageName: 'mutgui',
  projectFile: 'mutgui.build.mjs',
  staticDir: '../src/mutgui/static',
  runtimeDirName: 'libs',
  vendorDirName: 'vendor',
  vendors: [
    {
      importName: 'react',
      packageName: 'react',
      entry: 'vendor/react.ts',
      outFile: (version) => `react-${version}.js`,
    },
    {
      importName: 'react-dom/client',
      packageName: 'react-dom',
      entry: 'vendor/react-dom-client.ts',
      outFile: (version) => `react-dom-client-${version}.js`,
      peers: ['react'],
    },
    {
      importName: 'react/jsx-runtime',
      packageName: 'react',
      entry: 'vendor/react-jsx-runtime.ts',
      outFile: (version) => `react-jsx-runtime-${version}.js`,
    },
    {
      importName: 'antd',
      packageName: 'antd',
      entry: 'vendor/antd.ts',
      outFile: (version) => `antd-${version}.js`,
      peers: ['react', 'react/jsx-runtime'],
    },
  ],
  runtimes: [
    {
      importName: '@mutgui/core',
      entry: 'src/core.tsx',
      outFile: 'mutgui-core.js',
      cssFile: 'mutgui-core.css',
      peers: ['react', 'react-dom/client', 'react/jsx-runtime'],
    },
    {
      importName: '@mutgui/antd',
      entry: 'src/integrations/antd.ts',
      outFile: 'mutgui-antd.js',
      peers: ['react', 'react/jsx-runtime', 'antd', '@mutgui/core'],
      kind: 'lib',
    },
    {
      importName: '@mutgui/theme-dark',
      entry: 'src/plugins/theme-dark/index.ts',
      outFile: 'mutgui-theme-dark.js',
      peers: ['react', 'react/jsx-runtime', 'antd', '@mutgui/core'],
      kind: 'plugin',
    },
  ],
  boot: {
    entry: 'src/boot.ts',
    outFile: 'boot.js',
    globalName: 'MutguiBoot',
  },
  legacyFiles: ['mutgui.js', 'mutgui-antd.js', 'mutgui-theme-dark.js'],
});
