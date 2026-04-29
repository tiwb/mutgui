import react from '@vitejs/plugin-react';
import { defineConfig, type PluginOption, type UserConfig } from 'vite';

export interface LibOptions {
  entry: string;
  outDir: string;
  outFile: string;
  peers?: string[];
  reactPlugin?: boolean;
  cssFile?: string;
  extraPlugins?: PluginOption[];
}

export function defineLib(opts: LibOptions): UserConfig {
  return defineConfig({
    define: {
      'process.env.NODE_ENV': JSON.stringify('production'),
    },
    plugins: [
      ...(opts.reactPlugin === false ? [] : [react()]),
      ...(opts.extraPlugins ?? []),
    ],
    build: {
      lib: {
        entry: opts.entry,
        formats: ['es'],
        fileName: () => opts.outFile,
      },
      outDir: opts.outDir,
      emptyOutDir: false,
      rollupOptions: {
        external: opts.peers ?? [],
        output: {
          assetFileNames: (asset) => {
            if (opts.cssFile && asset.name?.endsWith('.css')) {
              return opts.cssFile;
            }
            return '[name][extname]';
          },
        },
      },
      cssCodeSplit: false,
      target: 'es2022',
    },
  });
}

export interface VendorOptions {
  entry: string;
  outDir: string;
  outFile: string;
  peers?: string[];
}

export function defineVendor(opts: VendorOptions): UserConfig {
  return defineConfig({
    define: {
      'process.env.NODE_ENV': JSON.stringify('production'),
    },
    build: {
      lib: {
        entry: opts.entry,
        formats: ['es'],
        fileName: () => opts.outFile,
      },
      outDir: opts.outDir,
      emptyOutDir: false,
      rollupOptions: {
        external: opts.peers ?? [],
        output: {
          assetFileNames: '[name][extname]',
        },
      },
      cssCodeSplit: false,
      target: 'es2022',
    },
  });
}
