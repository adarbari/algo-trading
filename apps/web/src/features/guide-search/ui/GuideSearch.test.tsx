import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { GuideSearchProvider } from '../model/provider';
import { GuideSearchButton } from './GuideSearchButton';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);
const NAME = 'rollup.momentum@v1.rel_volume';
const SERVED = {
  guideSearch: {
    query: 'volume',
    groups: [
      {
        kind: 'field',
        hits: [{ kind: 'field', id: NAME, title: NAME, snippet: 'Volume over its average.' }],
      },
      {
        kind: 'term',
        hits: [
          {
            kind: 'term',
            id: 'liquidity_risk',
            title: 'LIQUIDITY_RISK',
            snippet: 'Thin volume for the size.',
          },
        ],
      },
    ],
  },
};

function setup(navigate = vi.fn()) {
  render(
    <TestQueryProvider>
      <GuideSearchProvider navigate={navigate}>
        <GuideSearchButton />
      </GuideSearchProvider>
    </TestQueryProvider>,
  );
  return { navigate };
}

const BOX = { name: 'Search', hidden: false } as const;

/** Serve `guide` for the Guide search and the ticker table the given rows (none by default). */
function serve(guide: unknown, rows: { symbol: string; name: string }[] = []) {
  GQL.mockImplementation(((_doc: unknown, variables: Record<string, unknown>) =>
    Promise.resolve('limit' in variables ? guide : tableOf(rows))) as never);
}
const tableOf = (rows: { symbol: string; name: string }[]) => ({
  table: { instruments: rows.map((r) => ({ instrumentId: `EQ:${r.symbol}`, ...r })) },
});
const guideCalls = () => GQL.mock.calls.filter(([, v]) => 'limit' in (v as object));

beforeEach(() => {
  GQL.mockReset();
  serve(SERVED);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('Guide search', () => {
  it('opens from the rail button and from Ctrl+K and ⌘K, and closes on the chord again', async () => {
    setup();
    const user = userEvent.setup();
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Search the Guide' }));
    expect(await screen.findByRole('dialog', { name: 'Search' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.keyboard('{Control>}k{/Control}');
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await user.keyboard('{Control>}k{/Control}');
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.keyboard('{Meta>}k{/Meta}');
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('asks the server once, about 200 ms after the last keystroke, not on every key', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    setup();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'volume');
    expect(GQL).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    await waitFor(() => {
      expect(guideCalls()).toHaveLength(1);
    });
    expect(guideCalls()[0]?.[1]).toEqual({ q: 'volume', limit: 6 });
  });

  it('shows the server’s groups in its order with their titles, snippets and links', async () => {
    setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'volume');
    const fields = within(await screen.findByRole('region', { name: 'Fields' }));
    expect(fields.getByText('Volume over its average.')).toBeInTheDocument();
    expect(fields.getByRole('link')).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(NAME)}`,
    );
    const glossary = within(screen.getByRole('region', { name: 'Glossary' }));
    expect(glossary.getByRole('link')).toHaveAttribute('href', '/guide/glossary/liquidity_risk');
    expect(screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'))).toEqual([
      'Fields',
      'Glossary',
    ]);
    await expectNoA11yViolations(document.body);
  });

  it('lists matching tickers first, each opening it in Explore', async () => {
    serve(SERVED, [{ symbol: 'VLO', name: 'Valero Energy' }]);
    setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'vlo');
    const tickers = within(await screen.findByRole('region', { name: 'Tickers' }));
    expect(tickers.getByText('Valero Energy')).toBeInTheDocument();
    expect(tickers.getByRole('link')).toHaveAttribute('href', '/explore?sel=VLO&focus=VLO');
    expect(screen.getAllByRole('region')[0]).toHaveAccessibleName('Tickers');
  });

  it('groups the mechanisms and the edges, each hit linking to its Guide page', async () => {
    serve({
      guideSearch: {
        query: 'drift',
        groups: [
          {
            kind: 'mechanism',
            hits: [
              {
                kind: 'mechanism',
                id: 'slow_to_update',
                title: 'Slow to update',
                snippet: 'Prices absorb news in steps.',
              },
            ],
          },
          {
            kind: 'edge',
            hits: [
              {
                kind: 'edge',
                id: 'pead',
                title: 'Post-earnings drift',
                snippet: 'Stocks keep drifting after a surprise.',
              },
            ],
          },
        ],
      },
    });
    setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'drift');
    const mechanisms = within(await screen.findByRole('region', { name: 'Mechanisms' }));
    expect(mechanisms.getByRole('link')).toHaveAttribute('href', '/guide/edges/m/slow_to_update');
    const edges = within(screen.getByRole('region', { name: 'Setups' }));
    expect(edges.getByRole('link')).toHaveAttribute('href', '/edges?edge=pead');
  });

  it('shows a screener category as a Screener categories result linking to its page', async () => {
    serve({
      guideSearch: {
        query: 'income',
        groups: [
          {
            kind: 'screener_category',
            hits: [
              {
                kind: 'screener_category',
                id: 'income',
                title: 'Income',
                snippet: 'Screens that pay you to wait.',
              },
            ],
          },
        ],
      },
    });
    setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'income');
    const group = within(await screen.findByRole('region', { name: 'Screener categories' }));
    expect(group.getByRole('link')).toHaveAttribute('href', '/guide/screeners/c/income');
  });

  it('opens the first result on Enter and the focused one after the arrows, under /guide', async () => {
    const { navigate } = setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'volume');
    await screen.findByRole('region', { name: 'Fields' });
    await user.keyboard('{Enter}');
    expect(navigate).toHaveBeenLastCalledWith(`/guide/fields/${encodeURIComponent(NAME)}`);
    expect(screen.queryByRole('dialog')).toBeNull();

    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'volume');
    await screen.findByRole('region', { name: 'Glossary' });
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{Enter}');
    expect(navigate).toHaveBeenLastCalledWith('/guide/glossary/liquidity_risk');
  });

  it('holds Enter typed before the answer and opens the result when it arrives', async () => {
    const { navigate } = setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'volume{Enter}');
    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith(`/guide/fields/${encodeURIComponent(NAME)}`);
    });
  });

  it('says when nothing matches, and offers a retry when the read fails', async () => {
    serve({ guideSearch: { query: 'zzzz', groups: [] } });
    setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'zzzz');
    expect(await screen.findByText('Nothing matches “zzzz”.')).toBeInTheDocument();
    await user.clear(screen.getByRole('searchbox'));
    GQL.mockRejectedValue(new Error('down'));
    await user.type(screen.getByRole('searchbox'), 'down');
    expect(await screen.findByRole('alert')).toHaveTextContent('The search failed.');
    expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument();
  });

  it('starts empty each time it opens', async () => {
    setup();
    const user = userEvent.setup();
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('searchbox', BOX), 'volume');
    await user.keyboard('{Escape}');
    await user.keyboard('{Control>}k{/Control}');
    expect(await screen.findByRole('searchbox', BOX)).toHaveValue('');
  });
});
