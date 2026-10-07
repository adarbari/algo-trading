import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { gql, TestQueryProvider } from '@/shared/api';
import { expectNoA11yViolations } from '@/shared/lib/testing';

import { GuideHelpProvider } from '../model/navigation';
import { GuideHelp } from './GuideHelp';

vi.mock('@/shared/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  gql: vi.fn(),
}));

const GQL = vi.mocked(gql);
const NAME = 'rollup.momentum@v1.rel_volume';
const SERVED = {
  guideField: {
    info: {
      name: NAME,
      unit: 'ratio',
      guide: {
        theme: 'momentum and trend',
        reads: 'Today volume over its 20-day average. Above 2 is heavy.',
        summary: 'Today volume over its 20-day average.',
        caveats: ['A halt distorts it.', 'An earnings day inflates it.'],
        uses: [
          {
            intent: 'heavy volume',
            op: 'gte',
            value: 2,
            mode: 'soft',
            tolerance: null,
            onMiss: null,
            note: '',
          },
        ],
      },
    },
  },
};

const BUTTON = { name: /^What is .*\?$/ };

/** The button once the read arrived: it gains its hover summary, which replaces the element. */
async function summarised() {
  await waitFor(() => {
    expect(screen.getByRole('button', BUTTON)).toHaveAttribute('aria-describedby');
  });
  return screen.getByRole('button', BUTTON);
}

function setup(navigate = vi.fn()) {
  const view = render(
    <TestQueryProvider>
      <GuideHelpProvider navigate={navigate}>
        <GuideHelp entry={{ kind: 'field', id: NAME }} />
      </GuideHelpProvider>
    </TestQueryProvider>,
  );
  return { ...view, navigate };
}

beforeEach(() => {
  GQL.mockReset();
  GQL.mockResolvedValue(SERVED);
});

describe('GuideHelp', () => {
  it('opens the field: name, title, theme and unit, how to read it, the rules, the caveat count', async () => {
    const { container } = setup();
    const button = await summarised();
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(button);
    const drawer = await screen.findByRole('dialog');
    expect(drawer).toHaveTextContent(NAME);
    expect(drawer).toHaveAccessibleDescription(/momentum and trend/);
    expect(await within(drawer).findByText(/Above 2 is heavy/)).toBeVisible();
    expect(within(drawer).getByRole('heading', { level: 3, name: 'Use it for' })).toBeVisible();
    expect(within(drawer).getByText('heavy volume')).toBeVisible();
    expect(within(drawer).getByText('gte 2 soft')).toBeVisible();
    expect(within(drawer).getByText(/2 caveats on the full page/)).toBeVisible();
    expect(button).toHaveAttribute('aria-expanded', 'true');
    await expectNoA11yViolations(container);
    expect(GQL.mock.calls[0]?.[1]).toEqual({ name: NAME });
  });

  it('shows the first sentence as the hover summary', async () => {
    setup();
    const button = await summarised();
    await userEvent.hover(button);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Today volume over its 20-day average.',
    );
  });

  it('opens the full page through the app navigation and closes the drawer', async () => {
    const { navigate } = setup();
    await userEvent.click(await summarised());
    await userEvent.click(await screen.findByRole('button', { name: 'Open full page' }));
    expect(navigate).toHaveBeenCalledWith(`/guide/fields/${encodeURIComponent(NAME)}`);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('says so when the Guide has no entry, and offers a retry when the read fails', async () => {
    GQL.mockResolvedValue({ guideField: { info: { name: NAME, unit: null, guide: null } } });
    const first = setup();
    await userEvent.click(await screen.findByRole('button', { name: /^What is .*\?$/ }));
    expect(await screen.findByText(/no entry for this field yet/)).toBeVisible();
    first.unmount();
    GQL.mockRejectedValue(new Error('down'));
    setup();
    await userEvent.click(await screen.findByRole('button', { name: /^What is .*\?$/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be loaded/);
    expect(screen.getByRole('button', { name: /Retry/ })).toBeVisible();
  });
});
