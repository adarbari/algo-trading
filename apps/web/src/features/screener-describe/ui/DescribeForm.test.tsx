import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

function setup() {
  const onDraft = vi.fn();
  const view = render(
    <TestQueryProvider>
      <DescribeForm screenerId="mine" document={DOCUMENT} onDraft={onDraft} />
    </TestQueryProvider>,
  );
  return { onDraft, ...view };
}

beforeEach(() => {
  POST.mockReset();
});

describe('DescribeForm', () => {
  it('sends the sentence with the current document, loads the draft and says what was left out', async () => {
    POST.mockResolvedValue({ data: ANSWER, response: new Response(null, { status: 200 }) });
    const { onDraft, container } = setup();
    const box = screen.getByRole('textbox', { name: 'Describe the screen' });
    expect(screen.getByRole('button', { name: 'Draft it' })).toBeDisabled();
    await userEvent.type(box, 'active stocks over $5 with IV rank above 50%{Enter}');
    await waitFor(() => {
      expect(onDraft).toHaveBeenCalledWith(ANSWER.document);
    });
    expect(POST).toHaveBeenCalledWith('/screeners/{screener_id}/draft-from-text', {
      params: { path: { screener_id: 'mine' } },
      body: { text: 'active stocks over $5 with IV rank above 50%', document: DOCUMENT },
    });
    expect(screen.getByText('Drafted 2 criteria; review and save')).toBeInTheDocument();
    expect(screen.getByText(/Left out iv_rank/)).toBeInTheDocument();
    expect(screen.getByText('no IV rank field in the catalogue')).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("shows the API's refusal as the field's error", async () => {
    POST.mockResolvedValue({
      error: {
        detail: 'natural-language drafts are off: enable them in config/site/llm.toml (ADR 0041)',
      },
      response: new Response(null, { status: 503 }),
    });
    const { onDraft } = setup();
    await userEvent.type(screen.getByRole('textbox', { name: 'Describe the screen' }), 'stocks');
    await userEvent.click(screen.getByRole('button', { name: 'Draft it' }));
    expect(await screen.findByText(/drafts are off/)).toBeInTheDocument();
    expect(onDraft).not.toHaveBeenCalled();
  });
});
