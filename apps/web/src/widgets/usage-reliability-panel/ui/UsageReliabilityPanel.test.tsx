import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { emptyUsage, usageFixture } from '@/entities/llm-usage';
import { gql, TestQueryProvider } from '@/shared/api';

import { UsageReliabilityPanel } from './UsageReliabilityPanel';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const view = (data: unknown) => {
  vi.mocked(gql).mockResolvedValue({ llmUsage: data });
  return render(
    <TestQueryProvider>
      <UsageReliabilityPanel />
    </TestQueryProvider>,
  );
};

describe('UsageReliabilityPanel', () => {
  it('shows how attempts ended with the fallback and failure rates', async () => {
    view(usageFixture());
    const strip = await screen.findByRole('region', { name: 'How attempts ended' });
    expect(strip).toHaveTextContent('Fell back');
    expect(strip).toHaveTextContent('rate 10.0%');
    expect(strip).toHaveTextContent('rate 5.0%');
    expect(strip).toHaveTextContent('Skipped for budget');
  });

  it('says when nothing is recorded', async () => {
    view(emptyUsage());
    expect(await screen.findByText('No text-model calls recorded yet')).toBeInTheDocument();
  });
});
