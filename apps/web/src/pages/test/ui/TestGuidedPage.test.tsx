import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TestGuidedPage } from './TestGuidedPage';

vi.mock('@/features/guide-help', () => ({ termHelp: () => null }));
vi.mock('@/entities/screen', () => ({
  useScreeners: () => ({
    isPending: false,
    isError: false,
    data: [
      { configId: 'vrp_scanner', scope: 'site' },
      { configId: 'my-vrp', scope: 'user' },
    ],
  }),
  useScreenerRuns: () => ({
    data: { byId: new Map([['vrp_scanner', { description: 'Rich premium in calm names' }]]) },
  }),
}));

describe('TestGuidedPage', () => {
  it('offers only the site templates as cards and opens the one picked', async () => {
    const onPick = vi.fn();
    render(<TestGuidedPage onPick={onPick} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Guided' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /my-vrp/ })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /vrp_scanner/ }));
    expect(onPick).toHaveBeenCalledWith('vrp_scanner');
  });
});
