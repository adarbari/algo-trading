import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fakeQuery, expectNoA11yViolations, stubElementSize } from '@/shared/lib/testing';

import { blankDraft, type EdgeDraft } from '../model/draft';
import { CompareStep } from './CompareStep';
import { IdeaStep } from './IdeaStep';
import { PicksStep } from './PicksStep';
import { ScreensStep } from './ScreensStep';
import { TestStep } from './TestStep';
import { TradeStep } from './TradeStep';

const hooks = vi.hoisted(() => ({ useScreeners: vi.fn() }));
vi.mock('@/entities/screen', () => ({ useScreeners: hooks.useScreeners }));
vi.mock('@/entities/edge', async () => {
  const { Text } = await import('@algotrade/ui');
  return {
    ScreenerRecord: ({ screenerId }: { screenerId: string }) => (
      <Text>{`record ${screenerId}`}</Text>
    ),
  };
});

stubElementSize();

beforeEach(() => {
  hooks.useScreeners.mockReturnValue(
    fakeQuery([
      { configId: 'momo', scope: 'site', selection: 'liquid' },
      { configId: 'size_small', scope: 'site', selection: 'small' },
      { configId: 'momo', scope: 'user', selection: 'liquid' },
    ]),
  );
});

/** A step bound to a real draft, so the typing shows. */
function Harness({
  step,
  start = blankDraft(),
  seen,
}: {
  step: (props: { draft: EdgeDraft; onChange: (p: Partial<EdgeDraft>) => void }) => React.ReactNode;
  start?: EdgeDraft;
  seen?: (d: EdgeDraft) => void;
}) {
  const [draft, setDraft] = useState(start);
  seen?.(draft);
  return step({
    draft,
    onChange: (p) => {
      setDraft((d) => ({ ...d, ...p }));
    },
  });
}

describe('Step 1, Idea', () => {
  it('edits the prose, the sources, and holds the quality bar under More', async () => {
    let last = blankDraft();
    const { container } = render(
      <Harness
        seen={(d) => {
          last = d;
        }}
        step={(p) => <IdeaStep {...p} chooseId={true} />}
      />,
    );
    await userEvent.type(screen.getByRole('textbox', { name: /^Name/ }), 'My edge');
    await userEvent.type(screen.getByRole('textbox', { name: /^Id/ }), 'my-edge');
    await userEvent.type(screen.getByRole('textbox', { name: /^Thesis/ }), 'T');
    await userEvent.type(screen.getByRole('textbox', { name: /^Why it should last/ }), 'M');
    await userEvent.type(screen.getByRole('textbox', { name: /Source 1: title/ }), 'JT');
    await userEvent.click(screen.getByRole('button', { name: 'Add a source' }));
    expect(screen.getByRole('textbox', { name: /Source 2: title/ })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: 'Remove' })[1] as HTMLElement);
    expect(screen.queryByRole('textbox', { name: /Source 2: title/ })).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', { name: /More: the rest of the quality bar/ }),
    );
    expect(
      screen.getAllByRole('textbox', { name: /How it fails|What else could explain it/ }),
    ).toHaveLength(2);
    await userEvent.type(screen.getByRole('textbox', { name: /How it fails/ }), 'crash');
    expect(last).toMatchObject({
      name: 'My edge',
      id: 'my-edge',
      thesis: 'T',
      mechanism: 'M',
      sources: [{ title: 'JT', url: '' }],
      qualityBar: expect.objectContaining({ failure_modes: 'crash' }) as unknown,
    });
    await expectNoA11yViolations(container);
  });

  it('asks for the id only when the edge has none, and shows its error', () => {
    render(<IdeaStep draft={blankDraft()} onChange={vi.fn()} chooseId={false} />);
    expect(screen.queryByRole('textbox', { name: /^Id/ })).not.toBeInTheDocument();
  });
});

describe('Step 2, Screens', () => {
  it('lists each screen once with its record, and chooses several', async () => {
    let last = blankDraft();
    render(
      <Harness
        seen={(d) => {
          last = d;
        }}
        step={(p) => <ScreensStep {...p} onOpenScreen={vi.fn()} />}
      />,
    );
    expect(screen.getAllByText('record momo')).toHaveLength(1);
    expect(screen.getByText('Choose at least one screen.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: /^momo/ }));
    await userEvent.click(screen.getByRole('checkbox', { name: /^size_small/ }));
    expect(last.screeners).toEqual(['momo', 'size_small']);
    await userEvent.click(screen.getByRole('checkbox', { name: /^momo/ }));
    expect(last.screeners).toEqual(['size_small']);
  });

  it('opens the Screen Builder on a screen, or on a new one', async () => {
    const onOpenScreen = vi.fn();
    render(<ScreensStep draft={blankDraft()} onChange={vi.fn()} onOpenScreen={onOpenScreen} />);
    await userEvent.click(
      screen.getByRole('button', { name: 'Edit size_small in Screen Builder' }),
    );
    expect(onOpenScreen).toHaveBeenLastCalledWith('size_small');
    await userEvent.click(screen.getByRole('button', { name: '+ New screen' }));
    expect(onOpenScreen).toHaveBeenLastCalledWith(null);
  });

  it('keeps a chosen screen the list does not have', () => {
    render(
      <ScreensStep
        draft={{ ...blankDraft(), screeners: ['gone'] }}
        onChange={vi.fn()}
        onOpenScreen={vi.fn()}
      />,
    );
    expect(screen.getByRole('checkbox', { name: /^gone/ })).toBeChecked();
  });
});

describe('Step 3, Picks', () => {
  it('chooses when it fires, the event and how many it takes', async () => {
    let last = blankDraft();
    render(
      <Harness
        seen={(d) => {
          last = d;
        }}
        step={(p) => <PicksStep {...p} />}
      />,
    );
    expect(screen.queryByRole('combobox', { name: 'Event' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'On an event' }));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Event' }), 'ex_dividend');
    expect(last).toMatchObject({ schedule: 'on_event', event: 'ex_dividend' });
    const n = screen.getByRole('spinbutton', { name: /^N/ });
    await userEvent.clear(n);
    await userEvent.type(n, '7{Enter}');
    expect(last.topK).toBe(7);
    await userEvent.click(screen.getByRole('radio', { name: 'All that qualify' }));
    expect(last.take).toBe('all');
    expect(screen.queryByRole('spinbutton', { name: /^N/ })).not.toBeInTheDocument();
  });
});

describe('Step 4, Trade', () => {
  it('sets the entry, holding periods, costs and what a win is', async () => {
    let last = blankDraft();
    render(
      <Harness
        seen={(d) => {
          last = d;
        }}
        step={(p) => <TradeStep {...p} />}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '60 days' }));
    expect(last.horizons).toEqual([20, 60]);
    await userEvent.click(screen.getByRole('button', { name: '20 days' }));
    expect(last.horizons).toEqual([60]);
    const costs = screen.getByRole('spinbutton', { name: /^Costs/ });
    await userEvent.clear(costs);
    await userEvent.type(costs, '25{Enter}');
    expect(last.costBps).toBe(25);
    await userEvent.click(screen.getByRole('radio', { name: 'Rises after costs' }));
    expect(last.win).toBe('rises');
  });

  it('offers the edges own holding periods and keeps a win test it cannot edit', () => {
    render(
      <TradeStep
        draft={{ ...blankDraft(), horizons: [20, 33], win: 'other' }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: '33 days' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Win test kept')).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Rises after costs' })).not.toBeInTheDocument();
  });
});

describe('Step 5, Compare against', () => {
  it('chooses the universe among the presets the screens use, and the decoys', async () => {
    let last = blankDraft();
    render(
      <Harness
        seen={(d) => {
          last = d;
        }}
        step={(p) => <CompareStep {...p} />}
      />,
    );
    const universe = screen.getByRole('combobox', { name: /^Universe/ });
    expect(
      within(universe)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Choose a universe', 'liquid', 'small']);
    await userEvent.selectOptions(universe, 'small');
    await userEvent.click(screen.getByRole('checkbox', { name: 'size_small' }));
    expect(last).toMatchObject({ universe: 'small', baselines: ['size_small'] });
  });
});

describe('Step 6, Test and run', () => {
  const props = { trials: 0, ready: true, saving: false, onSave: vi.fn() };

  it('validates the out-of-sample date and summarises the draft', async () => {
    let last = blankDraft();
    render(
      <Harness
        seen={(d) => {
          last = d;
        }}
        step={(p) => <TestStep {...p} {...props} />}
        start={{ ...blankDraft(), screeners: ['momo'] }}
      />,
    );
    expect(screen.getByText('momo')).toBeInTheDocument();
    const date = screen.getByRole('textbox', { name: /^Out-of-sample from/ });
    await userEvent.type(date, '2026-02-30');
    expect(screen.getByText('Use a real day written yyyy-mm-dd.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save and run backtest' })).toBeDisabled();
    await userEvent.clear(date);
    await userEvent.type(date, '2026-04-01');
    expect(last.frozenFrom).toBe('2026-04-01');
    expect(screen.getByRole('button', { name: 'Save and run backtest' })).toBeEnabled();
  });

  it('warns about the variants tried and saves with or without the run', async () => {
    const onSave = vi.fn();
    render(
      <TestStep draft={blankDraft()} onChange={vi.fn()} {...props} trials={4} onSave={onSave} />,
    );
    expect(screen.getByText('4 variants tried')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSave).toHaveBeenLastCalledWith(false);
    await userEvent.click(screen.getByRole('button', { name: 'Save and run backtest' }));
    expect(onSave).toHaveBeenLastCalledWith(true);
  });

  it('does not warn without variants and cannot save an incomplete draft', () => {
    render(<TestStep draft={blankDraft()} onChange={vi.fn()} {...props} ready={false} />);
    expect(screen.queryByText(/variants tried/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
});
