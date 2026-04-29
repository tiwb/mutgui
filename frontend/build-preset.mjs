import react from '@vitejs/plugin-react';
import { build as viteBuild } from 'vite';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { join, resolve } from 'node:path';

export function defineFrontendProject(spec) {
  return spec;
}

function isOutputStale(outputPath, inputs) {
  if (!existsSync(outputPath)) {
    return true;
  }
  const outputTime = statSync(outputPath).mtimeMs;
  return inputs.some((input) => statSync(resolve(input)).mtimeMs > outputTime);
}

function sharedBuildOptions() {
  return {
    configFile: false,
    define: {
      'process.env.NODE_ENV': JSON.stringify('production'),
    },
  };
}

function runtimeConfig(frontendDir, target, outDir) {
  return {
    ...sharedBuildOptions(),
    plugins: target.reactPlugin === false ? [] : [react()],
    build: {
      lib: {
        entry: resolve(frontendDir, target.entry),
        formats: ['es'],
        fileName: () => target.outFile,
      },
      outDir,
      emptyOutDir: false,
      rollupOptions: {
        external: target.peers ?? [],
        output: {
          assetFileNames: (asset) => {
            if (target.cssFile && asset.name?.endsWith('.css')) {
              return target.cssFile;
            }
            return '[name][extname]';
          },
        },
      },
      cssCodeSplit: false,
      target: 'es2022',
    },
  };
}

function vendorConfig(frontendDir, target, outDir, outFile) {
  return {
    ...sharedBuildOptions(),
    build: {
      lib: {
        entry: resolve(frontendDir, target.entry),
        formats: ['es'],
        fileName: () => outFile,
      },
      outDir,
      emptyOutDir: false,
      rollupOptions: {
        external: target.peers ?? [],
        output: {
          assetFileNames: '[name][extname]',
        },
      },
      cssCodeSplit: false,
      target: 'es2022',
    },
  };
}

function bootConfig(frontendDir, outDir, target, externalImports) {
  return {
    configFile: false,
    build: {
      lib: {
        entry: resolve(frontendDir, target.entry),
        formats: ['iife'],
        name: target.globalName ?? 'MutguiBoot',
        fileName: () => target.outFile,
      },
      outDir,
      emptyOutDir: false,
      rollupOptions: {
        external: externalImports,
      },
      target: 'es2022',
    },
  };
}

function readVendorVersions(frontendDir, vendors) {
  if (vendors.length === 0) {
    return {};
  }
  const lockPath = resolve(frontendDir, 'package-lock.json');
  const lock = JSON.parse(readFileSync(lockPath, 'utf-8'));
  const versions = {};
  for (const target of vendors) {
    const packageName = target.packageName;
    const key = `node_modules/${packageName}`;
    const version = lock.packages?.[key]?.version;
    if (!version) {
      throw new Error(`package-lock.json missing version for ${packageName}`);
    }
    versions[target.importName] = version;
  }
  return versions;
}

function vendorOutputFile(target, version) {
  return typeof target.outFile === 'function' ? target.outFile(version) : target.outFile;
}

function manifestForProject(project, vendorOutputs, runtimeDirName) {
  const exportsMap = {};
  const css = [];
  const entries = [];

  for (const vendor of vendorOutputs) {
    exportsMap[vendor.importName] = `${project.vendorDirName}/${vendor.outFile}`;
  }
  for (const runtime of project.runtimes) {
    exportsMap[runtime.importName] = `${runtimeDirName}/${runtime.outFile}`;
    if (runtime.cssFile) {
      css.push(`${runtimeDirName}/${runtime.cssFile}`);
    }
    if (runtime.kind) {
      entries.push({ name: runtime.importName, kind: runtime.kind });
    }
  }

  return {
    name: project.packageName,
    exports: exportsMap,
    css,
    entries,
  };
}

export async function buildProject(frontendDir, project) {
  const staticDir = resolve(frontendDir, project.staticDir);
  const runtimeDir = resolve(staticDir, project.runtimeDirName);
  const vendorDir = resolve(staticDir, project.vendorDirName);
  const manifestPath = resolve(staticDir, 'manifest.json');

  mkdirSync(staticDir, { recursive: true });
  mkdirSync(runtimeDir, { recursive: true });
  if (project.vendors.length > 0) {
    mkdirSync(vendorDir, { recursive: true });
  }

  const vendorVersions = readVendorVersions(frontendDir, project.vendors);
  const vendorOutputs = [];
  const sharedVendorInputs = [
    resolve(frontendDir, project.projectFile),
    resolve(frontendDir, 'build-preset.mjs'),
    resolve(frontendDir, 'package-lock.json'),
  ];

  for (const target of project.vendors) {
    const version = vendorVersions[target.importName];
    const outFile = vendorOutputFile(target, version);
    vendorOutputs.push({ importName: target.importName, outFile });
    const outputPath = join(vendorDir, outFile);
    const inputs = [...sharedVendorInputs, resolve(frontendDir, target.entry)];
    if (isOutputStale(outputPath, inputs)) {
      await viteBuild(vendorConfig(frontendDir, target, vendorDir, outFile));
    }
  }

  for (const target of project.runtimes) {
    await viteBuild(runtimeConfig(frontendDir, target, runtimeDir));
  }

  if (project.boot) {
    const externalImports = [
      ...vendorOutputs.map((target) => target.importName),
      ...project.runtimes.map((target) => target.importName),
    ];
    await viteBuild(bootConfig(frontendDir, staticDir, project.boot, externalImports));
  }

  for (const legacyFile of project.legacyFiles ?? []) {
    const legacyPath = join(staticDir, legacyFile);
    if (existsSync(legacyPath)) {
      rmSync(legacyPath, { force: true });
    }
  }

  const manifest = manifestForProject(project, vendorOutputs, project.runtimeDirName);
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf-8');

  if (project.vendors.length > 0) {
    const expectedVendorFiles = new Set(vendorOutputs.map((target) => target.outFile));
    for (const name of readdirSync(vendorDir)) {
      if (!expectedVendorFiles.has(name)) {
        rmSync(join(vendorDir, name), { force: true, recursive: true });
      }
    }
  }
}
