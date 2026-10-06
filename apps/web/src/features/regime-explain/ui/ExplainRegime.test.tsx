import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { ExplainRegime } from './ExplainRegime';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn() } };
});

const POST = vi.mocked(api.POST);
const OK = new Response(null, { status: 200 });
const ANSWER = {
  text: 'The market is in a storm: stress is 71 out of 100.',
  citations: [{ title: 'FRED: the yield curve', url: 'https://fred.stlouisfed.org/series/T10Y3M' }],
  checked: true,
  note: null,
  cached: false,
};
const refusal = (status: number, detail: string) => ({
  error: { detail },
  response: new Response(null, { status }),
});

/** The probe answers 400 (a model is configured); the explain call answers `explain`. */
function server(explain: unknown, probe: unknown = refusal(400, 'ask one of question or card')) {
  POST.mockImplementation(((_path: string, init: { body: { question?: string | null } }) =>
    Promise.resolve(init.body.question === null ? probe : explain)) as never);
}

function setup(props: { card?: string } = {}) {
  return render(
    <TestQueryProvider>
      <ExplainRegime {...props} />
    </TestQueryProvider>,
  );
}

beforeEach(() => {
  POST.mockReset();
});

describe('ExplainRegime', () => {
  it('asks only when clicked, then shows the text, its citations and the model-text footer', async () => {
    server({ data: ANSWER, response: OK });
    const { container } = setup();
    const button = await screen.findByRole('button', { name: 'Explain in plain words' });
    expect(POST).toHaveBeenCalledTimes(1); // the probe only: nothing asked of the model
    await userEvent.click(button);
    expect(await screen.findByText(ANSWER.text)).toBeVisible();
    expect(POST).toHaveBeenLastCalledWith('/regime/explain', {
      body: { question: 'what is happening?', card: null },
    });
    expect(screen.getByRole('link', { name: /FRED: the yield curve/ })).toHaveAttribute(
      'href',
      'https://fred.stlouisfed.org/series/T10Y3M',
    );
    expect(
      screen.getByText(/text model from the facts on this page; it may be wrong/),
    ).toBeVisible();
    await expectNoA11yViolations(container);
  });

  it('explains one card by its key with its own words on the button', async () => {
    server({ data: ANSWER, response: OK });
    setup({ card: 'sahm' });
    await userEvent.click(await screen.findByRole('button', { name: 'Explain in plain words' }));
    await waitFor(() => {
      expect(POST).toHaveBeenLastCalledWith('/regime/explain', { body: { card: 'sahm' } });
    });
  });

  it('shows the note, not the text, when the numbers did not check out', async () => {
    server({
      data: {
        text: '',
        citations: [],
        checked: false,
        note: 'It quoted 99, not a fact.',
        cached: false,
      },
      response: OK,
    });
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Explain in plain words' }));
    expect(await screen.findByText('It quoted 99, not a fact.')).toBeVisible();
    expect(screen.queryByText(/it may be wrong/)).toBeNull();
  });

  it('says too many requests in one line and keeps the button', async () => {
    server(refusal(429, 'regime explanations: too many requests, try again in 30 s'));
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Explain in plain words' }));
    expect(await screen.findByText(/too many requests, try again in 30 s/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Explain in plain words' })).toBeVisible();
  });

  it('hides the button when no text model is configured', async () => {
    server(undefined, refusal(503, 'the text model is off'));
    setup();
    await waitFor(() => {
      expect(POST).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('hides the button when the model goes away on a click', async () => {
    server(refusal(503, 'llama: timed out'));
    setup();
    await userEvent.click(await screen.findByRole('button', { name: 'Explain in plain words' }));
    await waitFor(() => {
      expect(screen.queryByRole('button')).toBeNull();
    });
    expect(screen.queryByText(/timed out/)).toBeNull();
  });
});
