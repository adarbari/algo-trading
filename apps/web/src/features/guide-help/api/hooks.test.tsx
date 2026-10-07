import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';

import { guidePath } from '../model/entry';
import { useGuideHelp } from './hooks';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);

function wrapper({ children }: { children: ReactNode }) {
  return <TestQueryProvider>{children}</TestQueryProvider>;
}

describe('useGuideHelp', () => {
  it("reads a field's guide entry by catalogue name over GraphQL", async () => {
    GQL.mockResolvedValue({ guideField: { info: { name: 'feature.market_cap', guide: null } } });
    const { result } = renderHook(() => useGuideHelp('feature.market_cap'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const [document, variables] = GQL.mock.calls[0] ?? [];
    expect(String(document)).toContain('query GuideHelpField');
    expect(String(document)).toContain('summary');
    expect(variables).toEqual({ name: 'feature.market_cap' });
    expect(result.current.data).toEqual({ name: 'feature.market_cap', guide: null });
  });

  it('reads null for a field the Guide does not know', async () => {
    GQL.mockResolvedValue({ guideField: null });
    const { result } = renderHook(() => useGuideHelp('feature.gone'), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBeNull();
  });
});

describe('guidePath', () => {
  it("is the field's full page under /guide/fields, encoded", () => {
    expect(guidePath({ kind: 'field', id: 'rollup.momentum@v1.rel_volume' })).toBe(
      '/guide/fields/rollup.momentum%40v1.rel_volume',
    );
  });
});
