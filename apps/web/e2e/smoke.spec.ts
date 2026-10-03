/**
 * Smoke test: the production build boots, `/` opens the TRADER workspace home (Ideas), the
 * ADMIN workspace is reachable, and both are accessible in light and dark.
 */
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

async function expectAccessible(page: Page): Promise<void> {
  const axe = await new AxeBuilder({ page }).analyze();
  expect(axe.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}

for (const colorScheme of ['light', 'dark'] as const) {
  test(`/ opens the trader workspace on Ideas (${colorScheme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.emulateMedia({ colorScheme });
    await page.goto('/');
    await expect(page).toHaveURL(/\/ideas$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Ideas' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Trader sections' })).toContainText(
      'Explore',
    );
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });

  test(`the admin workspace is reachable (${colorScheme})`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.emulateMedia({ colorScheme });
    await page.goto('/admin/ingestion');
    await expect(page.getByRole('heading', { level: 1, name: 'Ingestion' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Admin sections' })).toContainText(
      'Users & configs',
    );
    await expectAccessible(page);
    expect(errors).toEqual([]);
  });
}
