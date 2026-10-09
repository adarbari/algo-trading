import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { TabStrip, type TabStripItem } from './TabStrip';

const ITEMS: TabStripItem[] = [
  { id: 'a', label: 'NVDA', closeLabel: 'Close NVDA', mono: true },
  { id: 'b', label: 'AAPL', closeLabel: 'Close AAPL', mono: true },
  { id: 'c', label: 'SPY', closeLabel: 'Close SPY', mono: true },
];

function Harness({ onClose }: { onClose?: (id: string) => void }) {
  const [items, setItems] = useState(ITEMS);
  const [value, setValue] = useState<string | null>('a');
  return (
    <TabStrip
      items={items}
      value={value}
      label="Open"
      onChange={setValue}
      onClose={(id) => {
        onClose?.(id);
        setItems((all) => all.filter((i) => i.id !== id));
        if (id === value) setValue(items.find((i) => i.id !== id)?.id ?? null);
      }}
    >
      Panel {value}
    </TabStrip>
  );
}

describe('TabStrip', () => {
  it('selects with arrows, Home and End, and only the selected tab is in the tab order', async () => {
    render(<Harness />);
    const tabs = screen.getAllByRole('tab');
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[1]).toHaveAttribute('tabindex', '-1');
    tabs[0]?.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'AAPL' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Panel b');
    await userEvent.keyboard('{End}');
    expect(screen.getByRole('tab', { name: 'SPY' })).toHaveFocus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'NVDA' })).toHaveFocus();
  });

  it('closes with the close button and with Delete, moving the choice to a neighbour', async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await userEvent.click(screen.getByRole('button', { name: 'Close AAPL', hidden: true }));
    expect(onClose).toHaveBeenCalledWith('b');
    expect(screen.queryByRole('tab', { name: 'AAPL' })).toBeNull();
    screen.getByRole('tab', { name: 'NVDA' }).focus();
    await userEvent.keyboard('{Delete}');
    expect(screen.getByRole('tab', { name: 'SPY' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'SPY' })).toHaveFocus();
  });

  it('has no close buttons without onClose and no panel when nothing is selected', () => {
    render(
      <TabStrip items={ITEMS} value={null} label="Open" onChange={() => undefined}>
        x
      </TabStrip>,
    );
    expect(screen.queryByRole('button', { name: /Close/, hidden: true })).toBeNull();
    expect(screen.queryByRole('tabpanel')).toBeNull();
    expect(screen.getAllByRole('tab')[0]).toHaveAttribute('tabindex', '0');
  });

  it('reveals the selected tab again once the fonts resolve (their widths move the tabs)', async () => {
    let resolveFonts: () => void = () => undefined;
    const ready = new Promise<void>((resolve) => {
      resolveFonts = resolve;
    });
    Object.defineProperty(document, 'fonts', { configurable: true, value: { ready } });
    const reveal = vi.spyOn(Element.prototype, 'scrollIntoView');
    try {
      render(<Harness />);
      expect(reveal).toHaveBeenCalledTimes(1);
      resolveFonts();
      await act(async () => {
        await ready;
      });
      expect(reveal).toHaveBeenCalledTimes(2);
    } finally {
      reveal.mockRestore();
      Reflect.deleteProperty(document, 'fonts');
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<Harness />);
    await expectNoA11yViolations(container);
  });
});
