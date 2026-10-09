/**
 * Playwright performance budgets (e2e/perf.spec.ts): the production build served by
 * `vite preview`, the API mocked as in the e2e suite, on the phone device with the CPU throttled.
 * `make web-perf` runs it after the build and the bundle check; CI's `web-perf` job too.
 * One worker: the report is one table and the throttled runs must not compete for a core.
 */
import { defineConfig, devices } from '@playwright/test';

const previewPort =
  process.env['ALGOTRADE_PORT_BASE'] === undefined
    ? 4173
    : Number(process.env['ALGOTRADE_PORT_BASE']) + 7; // vite.config.ts

export default defineConfig({
  testDir: './e2e',
  testMatch: /perf\.spec\.ts/,
  workers: 1,
  forbidOnly: Boolean(process.env['CI']),
  retries: 0, // a count over budget is not a flake
  reporter: 'list',
  expect: { timeout: 15_000 }, // the CPU is throttled 4x
  use: {
    ...devices['iPhone 13'],
    defaultBrowserType: 'chromium',
    baseURL: `http://127.0.0.1:${String(previewPort)}`,
  },
  webServer: {
    // The build is `make web-perf`'s (it needs the Supabase keys; e2e/auth-api.ts mocks that host).
    command: 'npx vite preview --host 127.0.0.1',
    url: `http://127.0.0.1:${String(previewPort)}`,
    reuseExistingServer: !process.env['CI'],
    timeout: 60_000,
  },
});
