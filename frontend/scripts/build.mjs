import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(__dirname, '..');
const staticDir = resolve(frontendDir, '../src/mutgui/static');
const vendorDir = resolve(staticDir, 'vendor');
const manifestPath = resolve(staticDir, 'manifest.json');
const npmCmd = process.platform === 'win32' ? 'npm' : 'npm';

mkdirSync(staticDir, { recursive: true });
mkdirSync(vendorDir, { recursive: true });

const lock = JSON.parse(readFileSync(resolve(frontendDir, 'package-lock.json'), 'utf-8'));
const versions = {
  react: lock.packages['node_modules/react'].version,
  reactDom: lock.packages['node_modules/react-dom'].version,
  antd: lock.packages['node_modules/antd'].version,
};

const vendorTargets = [
  {
    config: 'vendor-build/react.config.ts',
    source: 'vendor-build/entries/react.ts',
    outFile: `react-${versions.react}.js`,
    importName: 'react',
  },
  {
    config: 'vendor-build/react-dom-client.config.ts',
    source: 'vendor-build/entries/react-dom-client.ts',
    outFile: `react-dom-client-${versions.reactDom}.js`,
    importName: 'react-dom/client',
  },
  {
    config: 'vendor-build/react-jsx-runtime.config.ts',
    source: 'vendor-build/entries/react-jsx-runtime.ts',
    outFile: `react-jsx-runtime-${versions.react}.js`,
    importName: 'react/jsx-runtime',
  },
  {
    config: 'vendor-build/antd.config.ts',
    source: 'vendor-build/entries/antd.ts',
    outFile: `antd-${versions.antd}.js`,
    importName: 'antd',
  },
];

const sharedVendorInputs = [
  'package-lock.json',
  'build-preset/index.ts',
];

function isOutputStale(outputPath, inputs) {
  if (!existsSync(outputPath)) {
    return true;
  }
  const outputTime = statSync(outputPath).mtimeMs;
  return inputs.some((input) => statSync(resolve(frontendDir, input)).mtimeMs > outputTime);
}

function runVite(configPath, extraEnv = {}) {
  if (process.platform === 'win32') {
    execFileSync(
      process.env.ComSpec ?? 'cmd.exe',
      ['/d', '/s', '/c', `${npmCmd} exec -- vite build --config ${configPath}`],
      {
        cwd: frontendDir,
        stdio: 'inherit',
        env: { ...process.env, ...extraEnv },
      },
    );
    return;
  }

  execFileSync(
    npmCmd,
    ['exec', '--', 'vite', 'build', '--config', configPath],
    {
      cwd: frontendDir,
      stdio: 'inherit',
      env: { ...process.env, ...extraEnv },
    },
  );
}

for (const target of vendorTargets) {
  const outputPath = join(vendorDir, target.outFile);
  if (isOutputStale(outputPath, [...sharedVendorInputs, target.config, target.source])) {
    runVite(target.config, { MUTGUI_OUT_FILE: target.outFile });
  }
}

for (const configPath of [
  'vite.runtime.core.ts',
  'vite.runtime.antd.ts',
  'vite.runtime.theme-dark.ts',
  'vite.boot.ts',
]) {
  runVite(configPath);
}

for (const legacyFile of ['mutgui.js', 'mutgui-antd.js', 'mutgui-theme-dark.js']) {
  const legacyPath = join(staticDir, legacyFile);
  if (existsSync(legacyPath)) {
    rmSync(legacyPath, { force: true });
  }
}

const manifest = {
  name: 'mutgui',
  exports: {
    react: `vendor/react-${versions.react}.js`,
    'react-dom/client': `vendor/react-dom-client-${versions.reactDom}.js`,
    'react/jsx-runtime': `vendor/react-jsx-runtime-${versions.react}.js`,
    antd: `vendor/antd-${versions.antd}.js`,
    '@mutgui/core': 'libs/mutgui-core.js',
    '@mutgui/antd': 'libs/mutgui-antd.js',
    '@mutgui/theme-dark': 'libs/mutgui-theme-dark.js',
  },
  css: [
    'libs/mutgui-core.css',
  ],
  entries: [
    { name: '@mutgui/antd', kind: 'lib' },
    { name: '@mutgui/theme-dark', kind: 'plugin' },
  ],
};

writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf-8');

const expectedVendorFiles = new Set(vendorTargets.map((target) => target.outFile));
for (const name of readdirSync(vendorDir)) {
  if (!expectedVendorFiles.has(name)) {
    rmSync(join(vendorDir, name), { force: true, recursive: true });
  }
}
