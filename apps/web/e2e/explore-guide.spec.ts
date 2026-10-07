/**
 * Explore > Field guide end to end, against the production build with the API mocked
 * (explore-api.ts): open the tab, pick a theme and a field, read what it means, see its spread
 * across the universe with the names passing a criterion, its criteria by intent and its
 * caveats; the choice lives in the URL (a field can be linked to); accessible in dark and light.
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

for (const theme of ['dark', 'light'] as const) {
  test(`pick a theme and a field, read its meaning, spread and criteria (${theme})`, async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.goto('/explore?sel=AAPL');
    await page.getByRole('tab', { name: 'Field guide' }).click();
    await expect(page).toHaveURL(/tab=guide/);
    await expect(page.getByRole('tab', { name: 'Field guide' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    // The ticker table gives way to the guide's own layout.
    await expect(page.getByRole('grid', { name: 'Tickers' })).toHaveCount(0);

    const sidebar = page.getByRole('complementary', { name: 'Find a field' });
    await sidebar.getByRole('button', { name: /^Implied volatility \d+/ }).click();
    await sidebar.getByRole('button', { name: new RegExp(IV30.replace(/[.@]/g, '\\$&')) }).click();
    await expect(page).toHaveURL(/theme=Implied/);
    await expect(page).toHaveURL(/field=rollup\.iv30%40v1\.iv30|field=rollup\.iv30@v1\.iv30/);

    const hero = page.getByRole('region', { name: 'What this field means' });
    await expect(hero.getByText(IV30, { exact: true })).toBeVisible();
    await expect(hero).toContainText('30-day at-the-money implied volatility');
    await expect(hero).toContainText('names have a value today');

    const universe = page.getByRole('region', { name: 'Across the universe today' });
    await expect(universe.getByRole('img')).toBeVisible();
    await expect(universe).toContainText(/[\d,]+ names pass “Rich premium to sell” today/);

    const year = page.getByRole('region', { name: 'One name over the last year' });
    await expect(year.getByRole('textbox', { name: 'Symbol' })).toHaveValue('AAPL');
    await expect(
      year.getByRole('img', { name: /shaded value zone: Rich premium to sell/ }),
    ).toBeVisible();

    const criteria = page.getByRole('region', { name: 'Criteria by intent' });
    await expect(criteria).toContainText('Rich premium to sell');
    await expect(criteria).toContainText('gte 0.4 soft tolerance 0.05');
    await expect(criteria.getByRole('button', { name: 'Add to a screen' })).toHaveCount(2);
    await expect(page.getByText('When the number lies')).toBeVisible();
    await expect(page.getByRole('region', { name: 'How it is computed' })).toBeVisible();

    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}

test('a field is a link, and the criterion shown can be switched', async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto(`/explore?tab=guide&field=${IV30}&symbol=AAPL`);
  await expect(page.getByRole('heading', { level: 2, name: 'Iv30' })).toBeVisible();
  await expect(
    page.getByRole('button', { name: new RegExp(IV30.replace(/[.@]/g, '\\$&')) }),
  ).toHaveAttribute('aria-current', 'true');
  await expect(page.getByRole('textbox', { name: 'Symbol' })).toHaveValue('AAPL');
  await page.getByRole('combobox', { name: 'Criterion to highlight' }).selectOption({ index: 1 });
  await expect(page.getByText(/names pass “Cheap options to buy” today/)).toBeVisible();
  await page.getByRole('searchbox', { name: 'Search fields and what they mean' }).fill('zzzz');
  await expect(page.getByText(/^No field in .* matches “zzzz”\.$/)).toBeVisible();
  expect(errors).toEqual([]);
});
