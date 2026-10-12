import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AdminFeatureRequestsPage } from './AdminFeatureRequestsPage';

vi.mock('@/widgets/feature-request-list', () => ({
  FeatureRequestList: ({ status }: { status: string | null }) => `[list ${status ?? 'all'}]`,
}));

vi.mock('@/widgets/accepted-formula-list', () => ({
  AcceptedFormulaList: () => '[formulas]',
}));

describe('AdminFeatureRequestsPage', () => {
  it('lays out the list and passes the chosen status down', async () => {
    render(<AdminFeatureRequestsPage status="OPEN" onStatusChange={vi.fn()} />);
    await waitFor(() => {
      expect(document.body).toHaveTextContent('[formulas]'); // the lazy section
    });
    expect(screen.getByRole('heading', { level: 1, name: 'Feature requests' })).toBeInTheDocument();
    expect(document.body).toHaveTextContent('[list OPEN]');
  });

  it('shows every status when none is chosen', () => {
    render(<AdminFeatureRequestsPage onStatusChange={vi.fn()} />);
    expect(document.body).toHaveTextContent('[list all]');
  });
});
