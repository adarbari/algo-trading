import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SiteFooter } from './SiteFooter';

vi.mock('./DataStatusPill', () => ({ DataStatusPill: () => <span>Data: complete</span> }));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <button type="button">{`Help ${id}`}</button>,
}));

describe('SiteFooter', () => {
  it('shows the data status and the risk line with the risk statement’s help button', () => {
    render(<SiteFooter admin={false} />);
    expect(screen.getByText('Data: complete')).toBeInTheDocument();
    expect(screen.getByText(/Backtested results are hypothetical/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help risk_statement' })).toBeInTheDocument();
  });
});
