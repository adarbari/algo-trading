import { Text } from '@algotrade/ui';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { DescribeForm } from './DescribeForm';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn() } };
});

const POST = vi.mocked(api.POST);
const DOCUMENT = {
  id: 'mine',
  criteria: { price: { field: 'rollup.price_stats@v2.close', op: 'gt', value: 1 } },
};
const ANSWER = {
  screener_id: 'mine',
  document: {
    id: 'mine',
    kind: 'screener',
    impl: 'rules',
    criteria: {
      active: { field: 'instrument.status', op: 'eq', value: 'ACTIVE' },
      price: { field: 'rollup.price_stats@v2.close', op: 'gt', value: 5 },
    },
  },
  dropped: [
    {
      id: 'iv_rank',
      field: 'rollup.nope@v1.iv_rank',
      reason: "field 'rollup.nope@v1.iv_rank' is not in the catalogue (IV rank above 50%)",
    },
  ],
  notes: ['no IV rank field in the catalogue'],
};
const OK = { response: new Response(null, { status: 200 }) };

interface Options {
  draftSessionId?: string;
  onAnswer?: () => void;
}

function setup({ draftSessionId, onAnswer }: Options = {}) {
  const onDraft = vi.fn();
  const onSession = vi.fn();
  const view = render(
    <TestQueryProvider>
      <DescribeForm
        screenerId="mine"
        document={DOCUMENT}
        onDraft={onDraft}
        onSession={onSession}
        {...(onAnswer ? { onAnswer } : {})}
        {...(draftSessionId ? { draftSessionId } : {})}
        renderTermHelp={(term) => <Text>{`help ${term}`}</Text>}
        renderReview={({ answer, text }): ReactNode => (
          <Text>{`review of "${text}" with ${String(Object.keys(answer.document['criteria'] ?? {}).length)} criteria`}</Text>
        )}
      />
    </TestQueryProvider>,
  );
  return { onDraft, onSession, ...view };
}

const type = (sentence: string) =>
  userEvent.type(screen.getByRole('textbox', { name: 'Describe the screen' }), sentence);

beforeEach(() => {
  POST.mockReset();
});

describe('DescribeForm', () => {
  it('sends the sentence with the current document, loads the draft and hands the answer to the review', async () => {
    POST.mockResolvedValue({ data: ANSWER, ...OK });
    const onAnswer = vi.fn();
    const { onDraft, container } = setup({ onAnswer });
    expect(screen.getByRole('button', { name: 'Draft it' })).toBeDisabled();
    await type('active stocks over $5 with IV rank above 50%{Enter}');
    await waitFor(() => {
      expect(onDraft).toHaveBeenCalledWith(ANSWER.document);
    });
    expect(POST).toHaveBeenCalledWith(
      '/screeners/{screener_id}/draft-from-text',
      expect.objectContaining({
        params: { path: { screener_id: 'mine' } },
        body: { text: 'active stocks over $5 with IV rank above 50%', document: DOCUMENT },
      }),
    );
    expect(onAnswer).toHaveBeenCalledWith(ANSWER);
    expect(
      screen.getByText('review of "active stocks over $5 with IV rank above 50%" with 2 criteria'),
    ).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("sends the previous answer's session id with the next sentence and reports the new one", async () => {
    POST.mockResolvedValue({ data: { ...ANSWER, draft_session_id: 'sess-2' }, ...OK });
    const { onSession } = setup({ draftSessionId: 'sess-1' });
    await type('and liquid{Enter}');
    await waitFor(() => {
      expect(onSession).toHaveBeenCalledWith('sess-2');
    });
    expect(POST).toHaveBeenCalledWith(
      '/screeners/{screener_id}/draft-from-text',
      expect.objectContaining({
        body: { text: 'and liquid', document: DOCUMENT, draft_session_id: 'sess-1' },
      }),
    );
  });

  it('keeps the Builder document when the answer has no criteria, and still shows the review', async () => {
    POST.mockResolvedValue({
      data: { ...ANSWER, document: { id: 'mine', criteria: {} }, dropped: [] },
      ...OK,
    });
    const { onDraft } = setup();
    await type('something nobody stores{Enter}');
    expect(
      await screen.findByText(/review of "something nobody stores" with 0 criteria/),
    ).toBeVisible();
    expect(onDraft).not.toHaveBeenCalled();
  });

  it("says drafting is off in the trader's words, never the API's text, with no Try again", async () => {
    POST.mockResolvedValue({
      error: { detail: 'the text model is off: enable it in config/site/llm.toml (ADR 0041)' },
      response: new Response(null, { status: 503 }),
    });
    const { onDraft, container } = setup();
    await type('stocks{Enter}');
    expect(await screen.findByText('Drafting is off')).toBeInTheDocument();
    expect(screen.getByText('help describe_failure_off')).toBeInTheDocument();
    expect(screen.queryByText(/config\/site/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(onDraft).not.toHaveBeenCalled();
    await expectNoA11yViolations(container);
  });

  it('never shows the raw "answer is not JSON"; Try again asks again and clears the message', async () => {
    POST.mockResolvedValueOnce({
      error: { detail: "the model's answer is not JSON" },
      response: new Response(null, { status: 503 }),
    }).mockResolvedValue({ data: ANSWER, ...OK });
    const { onDraft } = setup();
    await type('stocks{Enter}');
    expect(await screen.findByText('The model could not answer')).toBeInTheDocument();
    expect(screen.queryByText(/JSON/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => {
      expect(onDraft).toHaveBeenCalledWith(ANSWER.document);
    });
    expect(screen.queryByText('The model could not answer')).not.toBeInTheDocument();
    expect(POST).toHaveBeenCalledTimes(2);
  });

  it('shows a waiting phase with Cancel, and ignores the answer that arrives after it', async () => {
    let answer: (value: unknown) => void = () => undefined;
    POST.mockImplementation(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }) as never,
    );
    const { onDraft, onSession } = setup();
    await type('stocks{Enter}');
    expect(await screen.findByText('Drafting your screen')).toBeInTheDocument();
    const signal = (POST.mock.calls[0]?.[1] as { signal?: AbortSignal } | undefined)?.signal;
    expect(signal?.aborted).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(signal?.aborted).toBe(true);
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    answer({ data: ANSWER, ...OK });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(onDraft).not.toHaveBeenCalled();
    expect(onSession).not.toHaveBeenCalled();
    expect(screen.queryByText(/review of/)).not.toBeInTheDocument();
    expect(screen.queryByText('The model could not answer')).not.toBeInTheDocument();
  });
});
