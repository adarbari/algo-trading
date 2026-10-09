import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import * as responsive from '../../responsive';
import { MasterDetail, type MasterDetailProps } from './MasterDetail';

function Example({ onClose, ...props }: Partial<MasterDetailProps> & { onClose?: () => void }) {
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <MasterDetail
      detailKey={chosen}
      detailTitle={chosen ?? 'AAPL'}
      onDetailClose={() => {
        onClose?.();
        setChosen(null);
      }}
      master={
        <ul aria-label="Tickers">
          {['AAPL', 'NVDA'].map((ticker) => (
            <li key={ticker}>
              <button
                type="button"
                onClick={() => {
                  setChosen(ticker);
                }}
              >
                {ticker}
              </button>
            </li>
          ))}
        </ul>
      }
      detail={<p>{`Detail of ${chosen ?? 'AAPL'}`}</p>}
      {...props}
    />
  );
}

describe('MasterDetail', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the master beside the detail when wide', async () => {
    vi.stubGlobal('innerWidth', 1400);
    const { container } = render(<Example summary={<p>Compare bar</p>} />);
    expect(screen.getByRole('list', { name: 'Tickers' })).toBeInTheDocument();
    expect(screen.getByText('Detail of AAPL')).toBeInTheDocument();
    expect(screen.getByText('Compare bar')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'NVDA' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByText('Detail of NVDA')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('opens the detail in a sheet on narrow and reports its dismissal', async () => {
    vi.stubGlobal('innerWidth', 375);
    const onClose = vi.fn();
    render(<Example onClose={onClose} summary={<p>Compare bar</p>} />);
    expect(screen.getByText('Compare bar')).toBeInTheDocument();
    expect(screen.queryByText('Detail of AAPL')).toBeNull();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'NVDA' }));
    const sheet = screen.getByRole('dialog', { name: 'NVDA' });
    expect(sheet).toHaveTextContent('Detail of NVDA');
    await expectNoA11yViolations(document.body);
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'NVDA' }));
    expect(screen.getByRole('dialog', { name: 'NVDA' })).toBeInTheDocument();
  });

  it('opens a full-height sheet with back, previous / next and a pinned footer on narrow', async () => {
    vi.stubGlobal('innerWidth', 375);
    const onClose = vi.fn();
    const onNext = vi.fn();
    const onPrevious = vi.fn();
    render(
      <Example
        onClose={onClose}
        step={{ onNext, onPrevious, hasNext: true, hasPrevious: false }}
        detailFooter={<button type="button">Open in Explore</button>}
      />,
    );
    const user = userEvent.setup();
    const opener = screen.getByRole('button', { name: 'NVDA' });
    await user.click(opener);
    const sheet = screen.getByRole('dialog', { name: 'NVDA' });
    expect(sheet).toHaveAttribute('data-size', 'full');
    expect(sheet).toContainElement(screen.getByRole('button', { name: 'Open in Explore' }));
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onNext).toHaveBeenCalledOnce();
    await expectNoA11yViolations(document.body);
    await user.click(screen.getByRole('button', { name: 'Back to list' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });

  it('does not reopen a dismissed key the caller kept', async () => {
    vi.stubGlobal('innerWidth', 375);
    const props = {
      master: <p>List</p>,
      detail: <p>Detail</p>,
      detailTitle: 'KO',
      onDetailClose: vi.fn(),
    };
    const { rerender } = render(<MasterDetail {...props} detailKey="KO" />);
    expect(screen.getByRole('dialog', { name: 'KO' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(props.onDetailClose).toHaveBeenCalledTimes(1);
    rerender(<MasterDetail {...props} detailKey="KO" />);
    expect(screen.queryByRole('dialog')).toBeNull();
    act(() => {
      rerender(<MasterDetail {...props} detailKey="MSFT" detailTitle="MSFT" />);
    });
    expect(screen.getByRole('dialog', { name: 'MSFT' })).toBeInTheDocument();
  });

  it('keeps the master mounted and does not pop the sheet when the width turns narrow', async () => {
    let narrow = false;
    const ref = { current: null };
    const spy = vi
      .spyOn(responsive, 'useNarrow')
      .mockImplementation(() => [ref, narrow] as ReturnType<typeof responsive.useNarrow>);
    try {
      const props = {
        master: <input aria-label="Filter" defaultValue="" />,
        detail: <p>Detail</p>,
        detailTitle: 'KO',
        onDetailClose: vi.fn(),
      };
      const { rerender } = render(<MasterDetail {...props} detailKey="KO" />);
      await userEvent.type(screen.getByRole('textbox', { name: 'Filter' }), 'abc');
      narrow = true;
      act(() => {
        rerender(<MasterDetail {...props} detailKey="KO" />);
      });
      // The same input instance (its typed value survives) and no modal over it.
      expect(screen.getByRole('textbox', { name: 'Filter' })).toHaveValue('abc');
      expect(screen.queryByRole('dialog')).toBeNull();
      act(() => {
        rerender(<MasterDetail {...props} detailKey="MSFT" detailTitle="MSFT" />);
      });
      expect(screen.getByRole('dialog', { name: 'MSFT' })).toBeInTheDocument();
    } finally {
      spy.mockRestore();
    }
  });
});
