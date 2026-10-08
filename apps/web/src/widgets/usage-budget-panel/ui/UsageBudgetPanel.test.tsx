import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { emptyUsage, overBudget, usageFixture } from '@/entities/llm-usage';
import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { UsageBudgetPanel } from './UsageBudgetPanel';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

function serve(data: unknown) {
  vi.mocked(gql).mockImplementation((document: unknown) =>
    String(document).includes('query LlmUsage')
      ? data instanceof Error
        ? Promise.reject(data)
        : Promise.resolve({ llmUsage: data })
      : Promise.resolve({}),
  );
}

const view = () =>
  render(
    <TestQueryProvider>
      <UsageBudgetPanel />
    </TestQueryProvider>,
  );

describe('UsageBudgetPanel', () => {
  it('shows each window with its spend, the notional part apart and the cap used', async () => {
    serve(usageFixture());
    const { container } = view();
    const strip = await screen.findByRole('region', { name: 'Spend by window' });
    expect(strip).toHaveTextContent('Today');
    expect(strip).toHaveTextContent('$0.7527');
    expect(strip).toHaveTextContent('of which $0.5000 notional (reported)');
    expect(strip).toHaveTextContent('2,400 in · 600 out');
    expect(strip).toHaveTextContent('1 calls reported no tokens');
    const daily = screen.getByRole('meter', { name: /Today against the daily cap/ });
    expect(daily).toHaveAttribute('aria-valuetext', '75 %, near the cap');
    expect(
      screen.getByRole('meter', { name: /Month to date against the monthly cap/ }),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('says a cap is not set instead of showing zero used, and marks a spend past the cap', async () => {
    serve(overBudget());
    view();
    const strip = await screen.findByRole('region', { name: 'Spend by window' });
    expect(strip).toHaveTextContent('$1.3500');
    const meter = screen.getByRole('meter', { name: /Today against the daily cap/ });
    expect(meter).toHaveAttribute('aria-valuetext', '135 %, at the cap, above range');
    expect(
      screen.getByRole('img', {
        name: 'Month to date against the monthly cap: unknown. No monthly cap set',
      }),
    ).toBeInTheDocument();
  });

  it('still shows the windows and the caps when nothing has been recorded', async () => {
    serve(emptyUsage());
    view();
    expect(await screen.findByRole('region', { name: 'Spend by window' })).toHaveTextContent(
      '$0.0000',
    );
    expect(screen.queryByText('No text-model calls recorded yet')).not.toBeInTheDocument();
  });

  it('says so when the usage cannot be read', async () => {
    serve(new Error('boom'));
    view();
    expect(await screen.findByText('Text-model usage could not load.')).toBeInTheDocument();
  });
});
