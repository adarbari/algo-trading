/**
 * Describe it's formula flow end to end, against the production build with the API mocked
 * (builder-api.ts): a sentence is drafted, the review panel offers a formula
 * whose criterion waits as a pending row and holds Finalize back; Review and add opens the
 * formula dialog filled in, saving adds the criterion as an active row and releases Finalize;
 * Skip drops the pending row and releases Finalize too; the choices travel with the save.
 */
import { expect, test, type Page } from '@playwright/test';

import { expectAccessible } from './a11y';
import {
  FORMULA_EXPR,
  FORMULA_NAME,
  RETYPED_WORDS,
  SUGGESTION_FIELD,
  mockBuilderApi,
  mockDescribeApi,
} from './builder-api';
import { mockApi } from './mock-api';

async function describeIt(page: Page) {
  await page.goto('/screeners/my-vrp/edit');
  await page
    .getByRole('textbox', { name: 'Describe the screen' })
    .fill('IV above HV and above 50%');
  await page.getByRole('button', { name: 'Draft it' }).click();
  await expect(page.getByRole('article', { name: 'IV above HV' })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test('a proposed formula waits as a pending row and Finalize waits with it', async ({ page }) => {
  await mockBuilderApi(page);
  await mockDescribeApi(page);
  await describeIt(page);
  const pending = page.getByRole('group', { name: `Waiting on formula: feature.${FORMULA_NAME}` });
  await expect(pending).toBeVisible();
  await expect(page.getByText('Formula pending')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finalize v2' })).toBeDisabled();
  // The pending criterion is not in the screen yet: Save draft still works.
  await expect(page.getByRole('button', { name: 'Save draft' })).toBeEnabled();
  await expectAccessible(page);
});

test('Review and add saves the formula, turns the pending row into an active one and releases Finalize', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await mockDescribeApi(page);
  await describeIt(page);
  const rows = page.getByRole('radiogroup', { name: /Mode of/ });
  const before = await rows.count();
  await page.getByRole('button', { name: 'Review and add' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Add formula feature' });
  await expect(dialog.getByLabel('Name')).toHaveValue(FORMULA_NAME);
  await expect(dialog.getByRole('textbox', { name: 'Formula' })).toHaveValue(FORMULA_EXPR);
  await expect(dialog.getByLabel('What it is')).toHaveValue('IV30 minus HV30');
  await expect(dialog.getByText('num (float32)')).toBeVisible();
  await dialog.getByRole('button', { name: 'Save feature' }).click();
  await expect.poll(() => mock.features.length).toBe(1);
  expect(mock.features[0]).toMatchObject({ name: FORMULA_NAME, unit: 'ratio' });
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('group', { name: /Waiting on formula/ })).toHaveCount(0);
  await expect(rows).toHaveCount(before + 1);
  await expect(page.getByText('Accepted')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finalize v2' })).toBeEnabled();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  expect(mock.drafts[0]?.document['criteria']).toHaveProperty(FORMULA_NAME);
});

test('Skip drops the pending row, adds no criterion and releases Finalize', async ({ page }) => {
  const mock = await mockBuilderApi(page);
  await mockDescribeApi(page);
  await describeIt(page);
  const rows = page.getByRole('radiogroup', { name: /Mode of/ });
  const before = await rows.count();
  await page
    .getByRole('group', { name: /Waiting on formula/ })
    .getByRole('button', { name: 'Skip' })
    .click();
  await expect(page.getByRole('group', { name: /Waiting on formula/ })).toHaveCount(0);
  await expect(rows).toHaveCount(before);
  await expect(page.getByText('Skipped')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finalize v2' })).toBeEnabled();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  expect(mock.drafts[0]?.document['criteria']).not.toHaveProperty(FORMULA_NAME);
});

test('closing the review leaves the formula pending', async ({ page }) => {
  await mockBuilderApi(page);
  await mockDescribeApi(page);
  await describeIt(page);
  await page.getByRole('button', { name: 'Review and add' }).first().click();
  await page
    .getByRole('dialog', { name: 'Add formula feature' })
    .getByRole('button', { name: 'Cancel' })
    .click();
  await expect(page.getByRole('group', { name: /Waiting on formula/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finalize v2' })).toBeDisabled();
});

test('the review is one card per part of the sentence, in order, with the formula inside its own card', async ({
  page,
}) => {
  await mockBuilderApi(page);
  await mockDescribeApi(page);
  await describeIt(page);
  const list = page.getByRole('list', { name: 'Parts of your sentence' });
  await expect(list.getByRole('article')).toHaveCount(2);
  const formula = page.getByRole('article', { name: 'IV above HV' });
  await expect(formula.getByText('Formula to review')).toBeVisible();
  await expect(formula.getByRole('button', { name: 'Review and add' })).toBeVisible();
  const applied = page.getByRole('article', { name: 'and above 50%' });
  await expect(applied.getByText(/We read this as/)).toBeVisible();
  await expectAccessible(page);
});

test('Add on a suggestion puts a soft row in the screen and the save carries it', async ({
  page,
}) => {
  const mock = await mockBuilderApi(page);
  await mockDescribeApi(page);
  await describeIt(page);
  const rows = page.getByRole('radiogroup', { name: /Mode of/ });
  const before = await rows.count();
  await page.getByRole('button', { name: `Add ${SUGGESTION_FIELD}` }).click();
  await expect(rows).toHaveCount(before + 1);
  await expect(page.getByText('Added', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save draft' }).click();
  await expect.poll(() => mock.drafts.length).toBe(1);
  expect(JSON.stringify(mock.drafts[0]?.document['criteria'])).toContain(SUGGESTION_FIELD);
});

test('Skip on a suggestion adds no row', async ({ page }) => {
  await mockBuilderApi(page);
  await mockDescribeApi(page);
  await describeIt(page);
  const rows = page.getByRole('radiogroup', { name: /Mode of/ });
  const before = await rows.count();
  await page.getByRole('button', { name: `Skip ${SUGGESTION_FIELD}` }).click();
  await expect(page.getByText('Skipped', { exact: true })).toBeVisible();
  await expect(rows).toHaveCount(before);
});

test('Retype this part sends the draft it holds, then shows the merged draft with the other part untouched', async ({
  page,
}) => {
  await mockBuilderApi(page);
  const mock = await mockDescribeApi(page);
  await describeIt(page);
  const part = page.getByRole('article', { name: 'and above 50%' });
  await part.getByRole('button', { name: 'Retype this part' }).click();
  const input = part.getByRole('textbox', { name: 'Retype this part' });
  await expect(input).toBeFocused();
  await input.fill(RETYPED_WORDS);
  await part.getByRole('button', { name: 'Redraft' }).click();
  await expect(page.getByRole('article', { name: RETYPED_WORDS })).toBeVisible();
  expect(mock.redrafts).toHaveLength(1);
  expect(mock.redrafts[0]).toMatchObject({
    part_id: 'p2',
    new_words: RETYPED_WORDS,
    draft_session_id: 'sess-e2e',
  });
  // the other part and its pending formula are as they were
  await expect(page.getByRole('article', { name: 'IV above HV' })).toBeVisible();
  await expect(
    page.getByRole('group', { name: `Waiting on formula: feature.${FORMULA_NAME}` }),
  ).toBeVisible();
  await expectAccessible(page);
});
