import { Button, Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SiteFooter } from './SiteFooter';

vi.mock('./DataStatusPill', () => ({ DataStatusPill: () => <Text>Data: complete</Text> }));
vi.mock('@/features/guide-help', () => ({
  termHelp: (id: string) => <Button>{`Help ${id}`}</Button>,
}));

describe('SiteFooter', () => {
  it('shows the data status and the risk line with the risk statement’s help button', async () => {
    render(<SiteFooter admin={false} />);
    expect(screen.getByText('Data: complete')).toBeInTheDocument();
    expect(await screen.findByText(/Backtested results are hypothetical/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help risk_statement' })).toBeInTheDocument();
  });
});
