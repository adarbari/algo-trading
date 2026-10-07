/**
 * The Guide end to end, against the production build with the API mocked (explore-api.ts): the
 * top bar's Guide link and the "?" key, the home with its theme groups, the field index, a
 * field's page (what it means, its spread, criteria, when it lies, related, a ticker), the rail's
 * search, and Explore's retired Field guide tab redirecting here; accessible in dark and light.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import { mockApi } from './mock-api';

const IV30 = 'rollup.iv30@v1.iv30';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test('the top bar links to the Guide, and "?" opens it', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/ideas');
  await page.getByRole('link', { name: /^Guide/ }).click();
  await expect(page).toHaveURL(/\/guide$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Guide' })).toBeVisible();
  await page.goto('/explore');
  await page.keyboard.press('?');
  await expect(page).toHaveURL(/\/guide$/);
  expect(errors).toEqual([]);
});

for (const theme of ['dark', 'light'] as const) {
  test(`home to a field page: its meaning, spread, criteria and caveats (${theme})`, async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.goto('/guide');
    await expect(page.getByRole('heading', { level: 2, name: 'Fields' })).toBeVisible();
    // Sections of later phases are not shown yet.
    await expect(page.getByRole('link', { name: 'Start here' })).toHaveCount(0);
    await page.getByRole('link', { name: /^Implied volatility · / }).click();
    await expect(page).toHaveURL(/\/guide\/fields\?theme=implied/);
    await page.getByRole('link', { name: IV30 }).first().click();
    await expect(page).toHaveURL(/\/guide\/fields\/rollup\.iv30(%40|@)v1\.iv30/);

    const hero = page.getByRole('region', { name: 'What this field means' });
    await expect(hero.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(hero).toContainText('30-day at-the-money implied volatility');
    await expect(hero).toContainText('names have a value today');

    const universe = page.getByRole('region', { name: 'Across the universe today' });
    await expect(universe.getByRole('img')).toBeVisible();
    await expect(universe).toContainText(/[\d,]+ names pass “Rich premium to sell” today/);

    const use = page.getByRole('region', { name: 'Use it for' });
    await expect(use).toContainText('gte 0.4 soft tolerance 0.05');
    await expect(use.getByRole('button', { name: 'Add to Builder' })).toHaveCount(2);

    await expect(page.locator('#lies').getByText('When it lies')).toBeVisible();
    await expect(page.getByText('Earnings gap inside the window')).toBeVisible();
    const related = page.getByRole('region', { name: 'Related fields and playbooks' });
    await expect(related.getByRole('link', { name: 'feature.iv_hv_ratio' })).toBeVisible();
    await expect(related).toContainText('VRP scanner');

    await page
      .getByRole('navigation', { name: 'On this page' })
      .getByRole('link', { name: 'Use it for' })
      .click();
    await expect(page).toHaveURL(/#use$/);

    const ticker = page.getByRole('region', { name: 'See it on a ticker' });
    await ticker.getByRole('textbox', { name: 'Symbol' }).fill('aapl');
    await ticker.getByRole('textbox', { name: 'Symbol' }).press('Enter');
    await expect(
      ticker.getByRole('img', { name: /shaded value zone: Rich premium to sell/ }),
    ).toBeVisible();

    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expectAccessible(page);

    await ticker.getByRole('link', { name: 'Open in Explore with its history' }).click();
    await expect(page).toHaveURL(/\/explore\?.*tab=features/);
    expect(errors).toEqual([]);
  });
}

test('the rail searches the fields and the index has three views', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/guide/fields');
  await page.getByRole('searchbox', { name: 'Search the guide' }).fill('realised');
  const results = page.getByRole('navigation', { name: 'Search results' });
  await expect(results.getByRole('link', { name: 'rollup.price_stats@v2.hv30' })).toBeVisible();
  await expect(results.getByRole('link', { name: IV30 })).toHaveCount(0);
  await page.getByRole('searchbox', { name: 'Search the guide' }).fill('zzzz');
  await expect(page.getByText('No field matches “zzzz”.')).toBeVisible();
  await page.getByRole('radio', { name: 'By intent' }).click();
  await expect(page).toHaveURL(/view=intent/);
  await page.getByRole('link', { name: /^Cheap options to buy/ }).click();
  await expect(page.getByRole('link', { name: IV30 })).toBeVisible();
  await page.goto('/guide/fields?view=az');
  await expect(page.getByRole('link', { name: IV30 })).toBeVisible();
  expect(errors).toEqual([]);
});

test('an unknown field says so instead of loading for good', async ({ page }) => {
  await page.goto('/guide/fields/feature.nope');
  await expect(page.getByText('No such field')).toBeVisible();
});

test('the Explore Field guide tab redirects to the Guide, keeping the field', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto('/explore?sel=AAPL');
  await page.getByRole('tab', { name: 'Field guide' }).click();
  await expect(page).toHaveURL(/\/guide\/fields$/);
  await page.goto(`/explore?tab=guide&field=${IV30}&symbol=AAPL`);
  await expect(page).toHaveURL(/\/guide\/fields\/rollup\.iv30(%40|@)v1\.iv30$/);
  await page.goto('/explore?tab=guide&theme=volatility');
  await expect(page).toHaveURL(/\/guide\/fields\?theme=volatility$/);
  expect(errors).toEqual([]);
});
