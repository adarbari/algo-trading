/**
 * Playwright screenshot + accessibility suite over every design-system story (visual/), served
 * from the static Storybook build. Baselines are Linux-only (the Playwright Docker image, as
 * in CI): run `npm run visual:docker`, or `npm run visual:update` to accept changes.
 * Screenshots live next to their component: <component>/__screenshots__/<story>.<theme>.png.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './visual',
  snapshotPathTemplate: '{arg}{ext}',
  updateSnapshots: process.env['CI'] ? 'none' : 'missing',
  forbidOnly: Boolean(process.env['CI']),
  retries: process.env['CI'] ? 1 : 0, // a story that redraws after its play function; the rule in docs/ci.md
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0, animations: 'disabled', caret: 'hide' } },
  use: { baseURL: 'http://127.0.0.1:6007', viewport: { width: 640, height: 360 } },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 640, height: 360 } },
    },
  ],
  webServer: {
    command: 'npx vite preview --outDir storybook-static --host 127.0.0.1 --port 6007 --strictPort',
    url: 'http://127.0.0.1:6007/index.json',
    reuseExistingServer: !process.env['CI'],
  },
});
