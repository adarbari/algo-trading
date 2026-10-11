/** Vite: dev server, production build and the Vitest runner (ADR 0025). */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';
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

// One machine, several worktrees: scripts/worktree.sh gives each a port block (ALGOTRADE_PORT_BASE)
// so their servers never collide. Unset (CI, the main checkout): today's numbers.
const base = process.env['ALGOTRADE_PORT_BASE'];
const port = (offset: number, fallback: number): number =>
  base === undefined ? fallback : Number(base) + offset;

const DOCUMENT_CLASS = fileURLToPath(
  new URL('./src/shared/api/generated/graphql/graphql.ts', import.meta.url),
);
const GRAPHQL_CALL = /\bgraphql\(\s*(`(?:[^`$]|\$(?!\{))*`)\s*\)/g;

/**
 * Each operation ships with the module that writes it. The client preset's `graphql()` looks a
 * document up in a map of every operation (gql.ts), which puts all of them in whichever chunk
 * imports it (the entry). The official Babel / SWC plugins that remove the map do not run under
 * Vite 8's oxc transform, so this does the same rewrite: `graphql(`...`)` becomes a pure
 * `new TypedDocumentString(`...`)` of the same text. The generated typings still type the call.
 */
function perModuleDocuments(): Plugin {
  return {
    name: 'algotrade:graphql-per-module-documents',
    enforce: 'pre',
    transform(code, id) {
      if (!/\.tsx?$/.test(id) || id.includes('/generated/') || id.includes('node_modules')) {
        return null;
      }
      if (!code.includes('graphql(')) return null;
      const out = code.replace(GRAPHQL_CALL, (_m, literal: string) => {
        return `/*#__PURE__*/ new __TypedDocumentString(${literal})`;
      });
      if (out === code) return null;
      return {
        code: `import { TypedDocumentString as __TypedDocumentString } from ${JSON.stringify(DOCUMENT_CLASS)};\n${out}`,
        map: null,
      };
    },
  };
}

export default defineConfig({
  plugins: [perModuleDocuments(), react()],
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
  build: {
    // dist/.vite/manifest.json: the bundle budgets (scripts/check-bundle-budgets.ts) read it.
    manifest: true,
    rolldownOptions: {
      // The generated document constants (graphql.ts) are unused once perModuleDocuments inlines
      // them: a pure constructor lets the bundler drop them.
      treeshake: { manualPureFunctions: ['TypedDocumentString'] },
      output: {
        // Vendor code in its own long-lived chunks: it changes far less than the app, so a deploy
        // leaves the browser's cached copy valid (the phone downloads only the app chunks again).
        codeSplitting: {
          groups: [
            {
              name: 'react',
              test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/,
              priority: 30,
            },
            {
              name: 'tanstack',
              test: /node_modules[\\/]@tanstack[\\/](react-router|router-core|history|react-query|query-core|store|react-store)[\\/]/,
              priority: 20,
            },
            {
              // Small modules shared by lazy chunks (the guide paths, the table paging): a chunk of
              // their own, so a lazy chunk shared by pages never pulls them into the entry.
              name: 'links',
              test: /(entities[\\/]guide[\\/]model[\\/]paths|components[\\/]TextLink[\\/]|feature-table[\\/]model[\\/]paging|entities[\\/]feature[\\/]model[\\/]catalogue)/,
              priority: 10,
            },
            {
              name: 'tables',
              test: /(feature-table[\\/]model[\\/]rows|features[\\/]guide-help[\\/]ui[\\/]helped)/,
              priority: 10,
            },
          ],
        },
      },
    },
  },
  server: {
    port: port(1, 5173),
    strictPort: true,
    // The API (apps/api, `algotrade-api`) serves its routes at the root (/health, /graphql, ...);
    // the web app calls them under /api, which the dev server strips and proxies.
    proxy: {
      '/api': {
        target: process.env['API_PROXY_TARGET'] ?? `http://127.0.0.1:${String(port(0, 8000))}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: { port: port(7, 4173), strictPort: true },
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
    pool: 'vmThreads',
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
