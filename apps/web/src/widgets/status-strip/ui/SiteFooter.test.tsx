import { Text } from '@algotrade/ui';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SiteFooter } from './SiteFooterLazy';

vi.mock('./DataStatusPill', () => ({ DataStatusPill: () => <Text>Data: complete</Text> }));

describe('SiteFooter', () => {
  it('shows the risk line at once and the data status and help button after the first interaction, with links to the Guide', async () => {
    render(<SiteFooter admin={false} />);
    expect(screen.getByText(/Backtested results are hypothetical/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Risk statement' })).toHaveAttribute(
      'href',
      '/guide/glossary/risk_statement',
    );
    expect(screen.getByRole('link', { name: 'Methodology and conflicts' })).toHaveAttribute(
      'href',
      '/guide/start/methodology_and_conflicts',
    );
    expect(screen.queryByText('Data: complete')).toBeNull();
    await userEvent.keyboard('a');
    expect(await screen.findByText('Data: complete')).toBeInTheDocument();
  });
});
