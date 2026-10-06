import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Button, Text } from '@algotrade/ui';

import { expectNoA11yViolations } from '@/shared/lib/testing';

import { useRegimeRange } from '../model/range';
import { RegimeRangeControl } from './RegimeRangeControl';
import { RegimeRangeProvider } from './RegimeRangeProvider';

function Window() {
  const range = useRegimeRange('2026-10-02');
  return (
    <>
      <Text>{`window ${range.window.start} to ${range.window.end}`}</Text>
      <Button
        onClick={() => {
          range.setWindow('Covid crash, early 2020', { start: '2019-02-19', end: '2021-02-18' });
        }}
      >
        pick an episode
      </Button>
    </>
  );
}

describe('RegimeRangeControl', () => {
  it('offers All, 20y, 10y, 5y and 2y, All first, and moves the window the charts share', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <RegimeRangeProvider>
        <RegimeRangeControl session="2026-10-02" />
        <Window />
      </RegimeRangeProvider>,
    );
    const group = screen.getByRole('radiogroup', { name: 'Chart range' });
    expect(screen.getAllByRole('radio').map((radio) => radio.textContent)).toEqual([
      'All',
      '20y',
      '10y',
      '5y',
      '2y',
    ]);
    expect(screen.getByRole('radio', { name: 'All' })).toBeChecked();
    expect(screen.getByText('window 1971-01-01 to 2026-10-02')).toBeVisible();
    await user.click(screen.getByRole('radio', { name: '5y' }));
    expect(screen.getByRole('radio', { name: '5y' })).toBeChecked();
    expect(screen.getByText('window 2021-10-02 to 2026-10-02')).toBeVisible();
    expect(group).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('shows the name of an episode window and selects no preset while it is shown', async () => {
    const user = userEvent.setup();
    render(
      <RegimeRangeProvider>
        <RegimeRangeControl session="2026-10-02" />
        <Window />
      </RegimeRangeProvider>,
    );
    await user.click(screen.getByRole('button', { name: 'pick an episode' }));
    expect(screen.getByText('Showing Covid crash, early 2020')).toBeVisible();
    expect(screen.getByText('window 2019-02-19 to 2021-02-18')).toBeVisible();
    expect(screen.queryByRole('radio', { checked: true })).toBeNull();
    await user.click(screen.getByRole('radio', { name: '10y' }));
    expect(screen.queryByText(/^Showing /)).toBeNull();
    expect(screen.getByText('window 2016-10-02 to 2026-10-02')).toBeVisible();
  });

  it('keeps its own window when there is no provider', async () => {
    const user = userEvent.setup();
    render(
      <>
        <RegimeRangeControl session="2026-10-02" />
        <Window />
      </>,
    );
    await user.click(screen.getByRole('radio', { name: '2y' }));
    expect(screen.getByRole('radio', { name: '2y' })).toBeChecked();
  });
});
