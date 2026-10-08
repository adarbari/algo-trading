/** Vite: dev server, production build and the Vitest runner (ADR 0025). */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { configDefaults, defineConfig } from 'vitest/config';

// Unit test files listed as `skipped` in quarantine.json do not run (docs/ci.md "Flaky specs").
const quarantine = JSON.parse(
  readFileSync(new URL('./quarantine.json', import.meta.url), 'utf8'),
) as { skipped: { kind: string; file: string }[] };
const quarantinedUnitFiles = quarantine.skipped.filter((q) => q.kind === 'unit').map((q) => q.file);

const UNIT_INCLUDE = ['src/**/*.test.{ts,tsx}', 'design-system/**/*.test.{ts,tsx}'];
const INTEGRATION_INCLUDE = [
  'src/{pages,widgets,features}/**/*.test.{ts,tsx}',
  'scripts/**/*.test.ts',
];
const INTEGRATION_TEST_TIMEOUT_MS = 20_000;

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
    include: [
      'src/**/*.test.{ts,tsx}',
      'design-system/**/*.test.{ts,tsx}',
      'scripts/**/*.test.ts',
      'lint-rules/**/*.test.js',
    ],
    exclude: [...configDefaults.exclude, ...quarantinedUnitFiles],
    css: { modules: { classNameStrategy: 'non-scoped' } },
    restoreMocks: true,
    // Integration-style files (a page, widget or feature rendered with its Query hooks; the
    // script tests that run ESLint in-process) take 5 to 15 s under `make check WORKERS=2`:
    // the 5 s default read as flakes (docs/ci.md "Flaky specs"). Vitest fixes a test's timeout
    // at collection, so the split is a project, not a setup-file hook.
    projects: [
      {
        extends: true,
        test: {
          name: 'unit',
          include: UNIT_INCLUDE,
          exclude: [...configDefaults.exclude, ...INTEGRATION_INCLUDE],
        },
      },
      {
        extends: true,
        test: {
          name: 'integration',
          include: INTEGRATION_INCLUDE,
          testTimeout: INTEGRATION_TEST_TIMEOUT_MS,
        },
      },
    ],
  },
});
