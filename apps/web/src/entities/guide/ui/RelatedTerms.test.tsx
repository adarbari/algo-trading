import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';
import { servedEntries } from '@/shared/lib/testing';

import { RelatedTerms } from './RelatedTerms';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue(
    servedEntries({ guideTerm: { entry: { id: 'base_rate', term: 'Base rate', short: 's' } } }),
  );
});

describe('RelatedTerms', () => {
  it('links each glossary term, named by the term itself, and leaves out one the Guide lacks', async () => {
    render(
      <TestQueryProvider>
        <RelatedTerms ids={['base_rate', 'no_such_term']} />
      </TestQueryProvider>,
    );
    expect(await screen.findByRole('link', { name: 'Base rate' })).toHaveAttribute(
      'href',
      '/guide/glossary/base_rate',
    );
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });
});
