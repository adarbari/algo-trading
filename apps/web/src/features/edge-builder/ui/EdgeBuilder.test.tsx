import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Text } from '@algotrade/ui';

import { EDGES_FIXTURE } from '@/entities/edge';
import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations, fakeQuery, stubElementSize } from '@/shared/lib/testing';

import type { EdgeSettings } from '../api/settings';
import { QUALITY_KEYS } from '../model/draft';
import { HelpProvider } from '../model/help';
import { clearStash, NEW_KEY, unstash } from '../model/stash';
import { EdgeBuilder, type EdgeBuilderProps } from './EdgeBuilder';

const hooks = vi.hoisted(() => ({
  useEdges: vi.fn(),
  useEdgeSettings: vi.fn(),
  useScreeners: vi.fn(),
}));
vi.mock('@/entities/edge', async (importOriginal) => {
  const { Text } = await import('@algotrade/ui');
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    useEdges: hooks.useEdges,
    ScreenerRecord: ({ screenerId }: { screenerId: string }) => (
      <Text>{`record ${screenerId}`}</Text>
    ),
  };
});
vi.mock('@/entities/screen', () => ({ useScreeners: hooks.useScreeners }));
vi.mock('../api/settings', () => ({ useEdgeSettings: hooks.useEdgeSettings }));
vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { PUT: vi.fn() } };
});

const PUT = vi.mocked(api.PUT);
const screens = () => within(document.getElementById('screens') as HTMLElement);
const ok = (data: unknown) => ({ data, response: new Response(null, { status: 200 }) }) as never;

const served: EdgeSettings = {
  schedule: 'on_event:earnings_reaction',
  frozenFrom: '2026-04-01',
  replaces: null,
  settings: {
    topK: 20,
    universe: 'liquid',
    kind: 'excess_return',
    benchmark: 'SPY',
    startOffsetSessions: 1,
    costBps: 15,
    qualityBar: QUALITY_KEYS.map((key) => ({ key, text: `answer ${key}` })),
    own: { extends: 'momentum_12_1', notes: 'kept' },
  },
};

stubElementSize();

beforeEach(() => {
  PUT.mockReset();
  clearStash('my_momentum');
  clearStash(NEW_KEY);
  hooks.useEdges.mockReturnValue(
    fakeQuery(
      EDGES_FIXTURE.edges.map((e) =>
        e.id === 'my_momentum' ? { ...e, sources: [{ title: 'JT 1993', url: '' }] } : e,
      ),
    ),
  );
  hooks.useEdgeSettings.mockReturnValue(fakeQuery(served));
  hooks.useScreeners.mockReturnValue(
    fakeQuery([
      { configId: 'momentum_12_1', scope: 'site', selection: 'liquid' },
      { configId: 'size_small', scope: 'site', selection: 'small' },
    ]),
  );
});

function setup(over: Partial<EdgeBuilderProps> = {}) {
  const props: EdgeBuilderProps = {
    id: 'my_momentum',
    onSaved: vi.fn(),
    onCancel: vi.fn(),
    onOpenScreen: vi.fn(),
    ...over,
  };
  const view = render(
    <TestQueryProvider>
      <HelpProvider value={(term) => <Text>{`help ${term}`}</Text>}>
        <EdgeBuilder {...props} />
      </HelpProvider>
    </TestQueryProvider>,
  );
  return { props, ...view };
}

describe('EdgeBuilder', () => {
  it('shows the six steps of a copy, started from what the server resolved', async () => {
    const { container } = setup();
    expect(screen.getByText('Your copy of an edge')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'My momentum' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Edge builder steps' });
    expect(nav.textContent).toContain('1 · Idea');
    expect(nav.textContent).toContain('6 · Test and run');
    expect(screens().getByRole('checkbox', { name: /^momentum_12_1/ })).toBeChecked();
    expect(screen.getByRole('spinbutton', { name: /^N/ })).toHaveValue('20');
    expect(screen.getByRole('textbox', { name: /^Out-of-sample from/ })).toHaveValue('2026-04-01');
    expect(screen.getByText('help edge_builder_idea')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /^Id/ })).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('saves the whole document, keeping what the user set earlier, then runs when asked', async () => {
    PUT.mockResolvedValue(ok({ edge_id: 'my_momentum', document: {} }));
    const { props } = setup();
    const n = screen.getByRole('spinbutton', { name: /^N/ });
    await userEvent.clear(n);
    await userEvent.type(n, '5{Enter}');
    expect(screen.getByText('Draft · unsaved changes')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save and run backtest' }));
    await waitFor(() => {
      expect(props.onSaved).toHaveBeenCalledWith('my_momentum', true);
    });
    expect(PUT).toHaveBeenCalledOnce();
    const [path, init] = PUT.mock.calls[0] as unknown as [
      string,
      { params: unknown; body: { document: Record<string, unknown> } },
    ];
    expect(path).toBe('/edges/{edge_id}');
    expect(init.params).toEqual({ path: { edge_id: 'my_momentum' } });
    expect(init.body.document).toMatchObject({
      id: 'my_momentum',
      extends: 'momentum_12_1',
      notes: 'kept',
      top_k: 5,
      universe: 'liquid',
      screeners: ['momentum_12_1'],
      frozen_from: '2026-04-01',
    });
  });

  it('saves without running', async () => {
    PUT.mockResolvedValue(ok({}));
    const { props } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => {
      expect(props.onSaved).toHaveBeenCalledWith('my_momentum', false);
    });
  });

  it('shows the API refusal and does not leave', async () => {
    PUT.mockResolvedValue({
      error: { detail: 'screeners: no screener preset "zzz"' },
      response: new Response(null, { status: 400 }),
    } as never);
    const { props } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('The edge was not saved')).toBeInTheDocument();
    expect(props.onSaved).not.toHaveBeenCalled();
  });

  it('cannot save until every answer is there', async () => {
    setup();
    await userEvent.clear(screen.getByRole('textbox', { name: /^Thesis/ }));
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.getAllByText('Needs an answer')).toHaveLength(1);
  });

  it('keeps the draft while the user edits a screen, and adds the screen made there', async () => {
    const { props, unmount } = setup();
    await userEvent.type(screen.getByRole('textbox', { name: /^Thesis/ }), ' more');
    await userEvent.click(
      screen.getByRole('button', { name: 'Edit size_small in Screen Builder' }),
    );
    expect(props.onOpenScreen).toHaveBeenCalledWith('size_small');
    expect(unstash('my_momentum')?.thesis).toContain(' more');
    unmount();
    setup({ addScreen: 'size_small' });
    expect(screen.getByRole('textbox', { name: /^Thesis/ })).toHaveValue(
      expect.stringContaining(' more') as string,
    );
    expect(screens().getByRole('checkbox', { name: /^size_small/ })).toBeChecked();
    expect(screens().getByRole('checkbox', { name: /^momentum_12_1/ })).toBeChecked();
  });

  it('Cancel drops the kept draft', async () => {
    const { props } = setup();
    await userEvent.click(
      screen.getByRole('button', { name: 'Edit size_small in Screen Builder' }),
    );
    expect(unstash('my_momentum')).toBeDefined();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(props.onCancel).toHaveBeenCalled();
    expect(unstash('my_momentum')).toBeUndefined();
  });

  it('builds a new edge: chooses its id and sends a document without extends', async () => {
    PUT.mockResolvedValue(ok({}));
    hooks.useEdgeSettings.mockReturnValue(fakeQuery(undefined));
    const { props } = setup({ id: null });
    expect(screen.getByText('New edge')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Untitled edge' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    await userEvent.type(screen.getByRole('textbox', { name: /^Name/ }), 'Fresh');
    await userEvent.type(screen.getByRole('textbox', { name: /^Id/ }), 'Bad Id');
    expect(screen.getByText('Use 1-64 of a-z, 0-9, _ and -.')).toBeInTheDocument();
    expect(props.onSaved).not.toHaveBeenCalled();
  });

  it('says so when the edge is not the users own or does not exist', () => {
    setup({ id: 'momentum_12_1' });
    expect(screen.getByText('You have no edge of this name to change.')).toBeInTheDocument();
  });

  it('shows a loading state and a failure', () => {
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isPending: true }));
    const { unmount } = setup();
    expect(screen.getByText('Loading the edge…')).toBeInTheDocument();
    unmount();
    hooks.useEdges.mockReturnValue(fakeQuery(undefined, { isError: true }));
    setup();
    expect(screen.getByText('The edge could not be loaded.')).toBeInTheDocument();
  });

  it('names a trial edge a new version', () => {
    hooks.useEdges.mockReturnValue(
      fakeQuery(
        EDGES_FIXTURE.edges.map((e) => (e.id === 'my_momentum' ? { ...e, state: 'trial' } : e)),
      ),
    );
    setup();
    expect(screen.getByText('New version of an edge')).toBeInTheDocument();
  });
});
