/** Vite: dev server, production build and the Vitest runner (ADR 0025). */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Unit test files listed as `skipped` in quarantine.json do not run (docs/ci.md "Flaky specs").
const quarantine = JSON.parse(
  readFileSync(new URL('./quarantine.json', import.meta.url), 'utf8'),
) as { skipped: { kind: string; file: string }[] };
const quarantinedUnitFiles = quarantine.skipped.filter((q) => q.kind === 'unit').map((q) => q.file);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  css: {
    // CSS Modules exist only inside design-system/ (ADR 0025 rule 3); class names stay readable.
    modules: {
      localsConvention: 'camelCaseOnly',
      generateScopedName: '[name]__[local]__[hash:base64:5]',
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    // The API (apps/api, `algotrade-api`) serves its routes at the root (/health, /graphql, ...);
    // the web app calls them under /api, which the dev server strips and proxies.
    proxy: {
      '/api': {
        target: process.env['API_PROXY_TARGET'] ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: { port: 4173, strictPort: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'design-system/**/*.test.{ts,tsx}', 'scripts/**/*.test.ts'],
    exclude: ['**/node_modules/**', ...quarantinedUnitFiles],
    css: { modules: { classNameStrategy: 'non-scoped' } },
    restoreMocks: true,
  },
});
