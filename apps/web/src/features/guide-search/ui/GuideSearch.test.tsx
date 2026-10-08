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

const BOX = { name: 'Search the Guide', hidden: false } as const;

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue(SERVED);
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
    expect(await screen.findByRole('dialog', { name: 'Search the Guide' })).toBeInTheDocument();
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
      expect(GQL).toHaveBeenCalledTimes(1);
    });
    expect(GQL.mock.calls[0]?.[1]).toEqual({ q: 'volume', limit: 6 });
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
    GQL.mockResolvedValue({ guideSearch: { query: 'zzzz', groups: [] } });
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
