import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { REQUESTS_FIXTURE } from '@/entities/feature-request';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import { FeatureRequestList } from './FeatureRequestList';

const hooks = vi.hoisted(() => ({ useFeatureRequests: vi.fn() }));
vi.mock('@/entities/feature-request', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useFeatureRequests: hooks.useFeatureRequests,
}));
vi.mock('@/features/guide-help', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    GuideHelp: ({ entry }: { entry: { id: string } }) => <Text>{`help ${entry.id}`}</Text>,
    termHelp: (id: string) => <Text>{`help ${id}`}</Text>,
  };
});

stubElementSize();

beforeEach(() => {
  hooks.useFeatureRequests.mockReturnValue(fakeQuery(REQUESTS_FIXTURE));
});

describe('FeatureRequestList', () => {
  it('lists each request in the served order with its counts, status and Guide buttons', async () => {
    const { container } = render(<FeatureRequestList />);
    const table = screen.getByRole('grid', { name: 'Feature requests' });
    const first = within(table).getByRole('row', { name: /realised_vol_20d/ });
    expect(within(first).getByText('Open')).toBeInTheDocument();
    expect(within(first).getByText('2.31')).toBeInTheDocument();
    const promoted = within(table).getByRole('row', { name: /rsi_14/ });
    expect(
      within(promoted).getByRole('link', { name: 'rollup.momentum@v1.rsi_14' }),
    ).toHaveAttribute('href', '/guide/fields/rollup.momentum%40v1.rsi_14');
    const unmapped = within(table).getByRole('row', { name: /vibes/ });
    expect(within(unmapped).getByText('UNMAPPED')).toBeInTheDocument();
    expect(screen.getByText('help feature_request_score')).toBeInTheDocument();
    expect(screen.getByText('help read_feature_requests')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows only the chosen status, and every one again on All', async () => {
    render(<FeatureRequestList />);
    const table = screen.getByRole('grid', { name: 'Feature requests' });
    await userEvent.click(screen.getByRole('radio', { name: 'Promoted' }));
    expect(within(table).getByRole('row', { name: /rsi_14/ })).toBeInTheDocument();
    expect(within(table).queryByRole('row', { name: /moon_phase/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    expect(within(table).getByRole('row', { name: /moon_phase/ })).toBeInTheDocument();
  });

  it('shows the loading, error and empty states', () => {
    hooks.useFeatureRequests.mockReturnValue(fakeQuery(undefined));
    const { rerender } = render(<FeatureRequestList />);
    expect(screen.getByText('Loading feature requests…')).toBeInTheDocument();
    hooks.useFeatureRequests.mockReturnValue(fakeQuery(undefined, { isError: true }));
    rerender(<FeatureRequestList />);
    expect(screen.getByText('The feature requests failed to load.')).toBeInTheDocument();
    hooks.useFeatureRequests.mockReturnValue(fakeQuery({ ...REQUESTS_FIXTURE, rows: [] }));
    rerender(<FeatureRequestList />);
    expect(screen.getByText('No feature has been requested.')).toBeInTheDocument();
  });
});
