import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

import { emptyUsage, usageFixture } from '@/entities/llm-usage';
import { gql, TestQueryProvider } from '@/shared/api';

import { UsageBreakdownPanel } from './UsageBreakdownPanel';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get: () => 400,
  });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true,
    get: () => 1000,
  });
});
afterAll(() => {
  Reflect.deleteProperty(HTMLElement.prototype, 'offsetHeight');
  Reflect.deleteProperty(HTMLElement.prototype, 'offsetWidth');
});

const view = (data: unknown) => {
  vi.mocked(gql).mockResolvedValue({ llmUsage: data });
  return render(
    <TestQueryProvider>
      <UsageBreakdownPanel />
    </TestQueryProvider>,
  );
};

describe('UsageBreakdownPanel', () => {
  it('breaks the spend down by model first, then by the other keys', async () => {
    view(usageFixture());
    const models = await screen.findByRole('grid', { name: 'Usage by Model' });
    expect(models).toHaveTextContent('claude-haiku-4-5 · claude');
    expect(models).toHaveTextContent('60.0%');
    await userEvent.click(screen.getByRole('radio', { name: 'User' }));
    expect(await screen.findByRole('grid', { name: 'Usage by User' })).toHaveTextContent('—');
  });

  it('draws the cost-basis split with the notional cost as its own segment', async () => {
    view(usageFixture());
    await userEvent.click(await screen.findByRole('radio', { name: 'Cost basis' }));
    const table = await screen.findByRole('grid', { name: 'Usage by Cost basis' });
    expect(table).toHaveTextContent('Reported (notional)');
    expect(
      screen.getByRole('img', { name: /Spend by cost basis.*Reported \(notional\)/ }),
    ).toBeInTheDocument();
  });

  it('says when nothing is recorded', async () => {
    view(emptyUsage());
    expect(await screen.findByText('No text-model calls recorded yet')).toBeInTheDocument();
  });
});
