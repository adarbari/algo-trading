/**
 * Playwright "real app" smoke (real/): the Vite DEV server (so its error overlay is visible)
 * against the REAL API on a real store, never mocks. Two stores, each with its own API and dev
 * server: an EMPTY one (the first-run app, before anything has run) and the golden fixture
 * store (`make golden-store`). `make web-real` runs it; CI's `real-app` job too.
 * Python: $ALGOTRADE_PY (default: the repo's .venv). The API serves from the repo root.
 */
import { mkdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';

import { defineConfig, devices, type PlaywrightTestConfig } from '@playwright/test';

type WebServer = Extract<NonNullable<PlaywrightTestConfig['webServer']>, unknown[]>[number];

const root = resolve(import.meta.dirname, '../..');
const python = process.env['ALGOTRADE_PY'] ?? resolve(root, '.venv/bin/python');
const emptyStore = resolve(import.meta.dirname, 'test-results/real-empty-store');
rmSync(emptyStore, { recursive: true, force: true });
mkdirSync(emptyStore, { recursive: true });

const base =
  process.env['ALGOTRADE_PORT_BASE'] === undefined
    ? undefined
    : Number(process.env['ALGOTRADE_PORT_BASE']);
const at = (offset: number, fallback: number): number =>
  base === undefined ? fallback : base + offset;

const stores = [
  { name: 'empty', url: `file://${emptyStore}`, api: at(2, 8801), web: at(4, 5801) },
  {
    name: 'golden',
    url: `file://${resolve(root, 'datasets/golden/store')}`,
    api: at(3, 8802),
    web: at(5, 5802),
  },
] as const;

export default defineConfig({
  testDir: './real',
  forbidOnly: Boolean(process.env['CI']),
  retries: 0,
  workers: 1,
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: { trace: 'retain-on-failure' },
  projects: stores.map((s) => ({
    name: s.name,
    use: { ...devices['Desktop Chrome'], baseURL: `http://127.0.0.1:${String(s.web)}` },
  })),
  webServer: stores.flatMap((s): WebServer[] => [
    {
      command: `${python} -m uvicorn algotrade_api.app:app --host 127.0.0.1 --port ${String(s.api)}`,
      cwd: root,
      url: `http://127.0.0.1:${String(s.api)}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ALGOTRADE_DATA_URL: s.url,
        ALGOTRADE_CONFIG_DIR: resolve(root, 'config'),
        ALGOTRADE_USER: 'smoke',
        ALGOTRADE_AUTH: 'off', // no Supabase here: the API serves the smoke user on loopback
        ALGOTRADE_IBKR_PORT: '1', // no broker here: live quotes must degrade, not hang
      },
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${String(s.web)}`,
      url: `http://127.0.0.1:${String(s.web)}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { API_PROXY_TARGET: `http://127.0.0.1:${String(s.api)}` },
    },
  ]),
});
