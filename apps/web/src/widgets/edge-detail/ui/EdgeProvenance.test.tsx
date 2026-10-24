import { cleanup, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { EdgeProvenance } from './EdgeProvenance';

vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return { termHelp: (id: string) => <Text>{`help ${id}`}</Text> };
});

const STATES = [
  [
    'CURRENT',
    'Current',
    "Evaluated on the 22 Oct session, today's data. Run 20261022T235000Z, 2 variants tried.",
    'provenance_current',
  ],
  [
    'STALE',
    'Stale',
    'Evaluated 12 Oct, 8 sessions ago. The screener changed since: this verdict is for the earlier version.',
    'provenance_stale',
  ],
  [
    'RE_EVALUATING',
    'Re-evaluating',
    'A new evaluation started 22 Oct 23:50. Showing the 15 Oct verdict until it finishes.',
    'provenance_re_evaluating',
  ],
] as const;

describe('EdgeProvenance', () => {
  it.each(STATES)(
    '%s: the server’s sentence with its badge and each its Guide entry',
    async (state, label, line, term) => {
      const { container } = render(<EdgeProvenance provenance={{ state, line, runId: null }} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(screen.getByText(line)).toBeInTheDocument();
      expect(screen.getByText(`help ${term}`)).toBeInTheDocument();
      expect(screen.getByText('help edge_provenance')).toBeInTheDocument();
      expect(screen.queryByRole('link')).toBeNull();
      await expectNoA11yViolations(container);
      cleanup();
    },
  );

  it('links the full run id to the Edge runs page when the server sent it (an admin)', () => {
    render(
      <EdgeProvenance
        provenance={{ state: 'CURRENT', line: 'Evaluated.', runId: 'edge-eval:drift:site-1' }}
      />,
    );
    expect(screen.getByRole('link', { name: 'edge-eval:drift:site-1' })).toHaveAttribute(
      'href',
      '/admin/harness-runs?run=edge-eval%3Adrift%3Asite-1',
    );
  });
});
