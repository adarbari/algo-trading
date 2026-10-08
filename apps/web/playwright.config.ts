/**
 * Playwright end-to-end tests (e2e/): the production build served by `vite preview`.
 * Specs listed as `skipped` in quarantine.json do not run (docs/ci.md "Flaky specs");
 * `QUARANTINE=only` runs exactly those, to see whether a fix holds.
 */
import { readFileSync } from 'node:fs';

import { defineConfig, devices } from '@playwright/test';

interface Quarantine {
  skipped: { kind: string; title: string }[];
}

const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const quarantine = JSON.parse(
  readFileSync(new URL('./quarantine.json', import.meta.url), 'utf8'),
) as Quarantine;
const quarantined = quarantine.skipped.filter((q) => q.kind === 'e2e').map((q) => escape(q.title));
const quarantinePattern = quarantined.length > 0 ? new RegExp(quarantined.join('|')) : undefined;

export default defineConfig({
  testDir: './e2e',
  forbidOnly: Boolean(process.env['CI']),
  retries: process.env['CI'] ? 1 : 0,
  ...(process.env['QUARANTINE'] === 'only'
    ? { grep: quarantinePattern ?? /$^/ }
    : quarantinePattern && { grepInvert: quarantinePattern }),
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'retain-on-failure' },
  projects: [
    // Desktop: every spec but the phone one.
    { name: 'chromium', use: { ...devices['Desktop Chrome'] }, testIgnore: /phone\.spec\.ts/ },
    // A phone (touch, mobile viewport; Chromium, the one browser CI installs): e2e/phone.spec.ts only (ADR 0025 rule 10).
    {
      name: 'phone',
      use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' },
      testMatch: /phone\.spec\.ts/,
    },
  ],
  webServer: {
    command: 'npx vite build && npx vite preview --host 127.0.0.1',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env['CI'],
    timeout: 120_000,
    // The build needs the Supabase keys (login.spec.ts mocks that host); e2e/auth-api.ts.
    env: {
      VITE_SUPABASE_URL: 'http://127.0.0.1:54321',
      VITE_SUPABASE_ANON_KEY: 'e2e-anon-key',
    },
  },
});
