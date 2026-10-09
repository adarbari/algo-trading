import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { RunEvaluation } from './RunEvaluation';

vi.mock('@/shared/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, api: { POST: vi.fn(), GET: vi.fn() }, gql: vi.fn() };
});

const POST = vi.mocked(api.POST);
const GET = vi.mocked(api.GET);
const GQL = vi.mocked(gql);

const view = (state: string, extra: Record<string, unknown> = {}) => ({
  state,
  edge_id: 'drift',
  user: 'ann',
  job_id: 'job-1',
  run_id: state === 'complete' ? 'run-1' : null,
  exploratory: state === 'complete' ? true : null,
  error: null,
  ...extra,
});
const ok = (data: unknown) => Promise.resolve({ data, response: new Response() });

const setup = (role: string) => {
  GQL.mockResolvedValue({ viewer: { id: 'ann', name: 'Ann', role, workspaces: ['trader'] } });
  return render(
    <TestQueryProvider>
      <RunEvaluation edgeId="drift" />
    </TestQueryProvider>,
  );
};

beforeEach(() => {
  POST.mockReset();
  GET.mockReset();
  GQL.mockReset();
});

describe('RunEvaluation', () => {
  it('starts an evaluation for the user, follows the job and reports it done', async () => {
    POST.mockReturnValue(ok(view('running')));
    GET.mockReturnValue(ok(view('complete')));
    const { container } = setup('trader');
    await userEvent.click(screen.getByRole('button', { name: 'Run backtest' }));
    expect(POST).toHaveBeenCalledWith('/edges/{edge_id}/evaluate', {
      params: { path: { edge_id: 'drift' }, query: { as_site: false } },
    });
    expect(await screen.findByText('Done (exploratory)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run as site' })).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it('shows the API refusal while another evaluation runs', async () => {
    POST.mockReturnValue(
      Promise.resolve({
        error: { detail: 'an evaluation of drift is already running for ann' },
        response: new Response(null, { status: 409 }),
      }),
    );
    setup('trader');
    await userEvent.click(screen.getByRole('button', { name: 'Run backtest' }));
    expect(await screen.findByText(/already running for ann/)).toBeInTheDocument();
  });

  it('offers an admin the site run', async () => {
    POST.mockReturnValue(ok(view('running', { user: 'site' })));
    GET.mockReturnValue(ok(view('running', { user: 'site' })));
    setup('admin');
    await userEvent.click(await screen.findByRole('button', { name: 'Run as site' }));
    await waitFor(() => {
      expect(POST).toHaveBeenCalledWith('/edges/{edge_id}/evaluate', {
        params: { path: { edge_id: 'drift' }, query: { as_site: true } },
      });
    });
    expect(await screen.findByText('Evaluating…')).toBeInTheDocument();
  });
});
