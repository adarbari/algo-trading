import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideStart } from './GuideStart';
import { GuideStartIndex } from './GuideStartIndex';

const hooks = vi.hoisted(() => ({ useGuideIndex: vi.fn(), useGuideStartPage: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
  useGuideStartPage: hooks.useGuideStartPage,
}));

const volume = 'feature.rel_volume';
const index = {
  sections: [{ id: 'start', title: 'Start here', purpose: 'How to use the app.', entries: 3 }],
  startPages: [
    { id: 'how_the_app_thinks', order: 1, title: 'How the app thinks', summary: 'A day.' },
    { id: 'read_a_result', order: 2, title: 'Read a result', summary: 'Hits and misses.' },
    { id: 'build_a_screen', order: 3, title: 'Build a screen', summary: 'From a playbook.' },
  ],
};
const page = {
  entry: { id: 'read_a_result', order: 2, title: 'Read a result', summary: 'Hits and misses.' },
  sections: [
    {
      title: 'A hit',
      body: {
        segments: [{ text: 'It passed every hard rule on ' }, { text: volume, field: volume }],
      },
    },
    { title: 'A near miss', body: { segments: [{ text: 'It failed a soft rule by a little.' }] } },
  ],
  links: [
    { kind: 'term', id: 'not_run', title: 'NOT_RUN' },
    { kind: 'field', id: volume, title: volume },
    { kind: 'playbook', id: 'breakout', title: 'Breakout' },
  ],
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
  hooks.useGuideStartPage.mockReturnValue(fakeQuery(page));
});

describe('GuideStartIndex', () => {
  it('lists the pages in order, numbered, each a link with its summary', async () => {
    const { container } = render(<GuideStartIndex />);
    expect(screen.getByRole('heading', { level: 1, name: 'Start here' })).toBeInTheDocument();
    const list = within(screen.getByRole('list', { name: /reading order/ }));
    expect(list.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      '1How the app thinksA day.',
      '2Read a resultHits and misses.',
      '3Build a screenFrom a playbook.',
    ]);
    expect(list.getByRole('link', { name: 'Read a result' })).toHaveAttribute(
      'href',
      '/guide/start/read_a_result',
    );
    await expectNoA11yViolations(container);
  });

  it('shows an error with a retry and an empty list', async () => {
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideIndex.mockReturnValue(failed);
    const { rerender } = render(<GuideStartIndex />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideIndex.mockReturnValue(fakeQuery({ ...index, startPages: [] }));
    rerender(<GuideStartIndex />);
    expect(screen.getByText('Start here has no pages yet.')).toBeInTheDocument();
  });
});

describe('GuideStart', () => {
  it('shows the step, title, summary, the sections with names linked, links by kind and the next page', async () => {
    const { container } = render(<GuideStart id="read_a_result" />);
    expect(screen.getByText('Start here · step 2')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Read a result' })).toBeInTheDocument();
    const hit = within(screen.getByRole('region', { name: 'A hit' }));
    expect(hit.getByRole('link', { name: volume })).toHaveAttribute(
      'href',
      `/guide/fields/${encodeURIComponent(volume)}`,
    );
    const next = within(screen.getByRole('region', { name: 'Where to look next' }));
    expect(next.getByRole('link', { name: 'NOT_RUN' })).toHaveAttribute(
      'href',
      '/guide/glossary/not_run',
    );
    expect(next.getByRole('link', { name: 'Breakout' })).toHaveAttribute(
      'href',
      '/guide/playbooks/breakout',
    );
    expect(next.getByText('Playbooks')).toBeInTheDocument();
    expect(
      within(screen.getByRole('navigation', { name: 'Next page' })).getByRole('link'),
    ).toHaveAttribute('href', '/guide/start/build_a_screen');
    await expectNoA11yViolations(container);
  });

  it('has no next link on the last page', () => {
    render(<GuideStart id="build_a_screen" />);
    expect(screen.queryByRole('navigation', { name: 'Next page' })).toBeNull();
  });

  it('says so for a page that does not exist, and offers a retry when it fails', async () => {
    hooks.useGuideStartPage.mockReturnValue(fakeQuery(null));
    const { rerender } = render(<GuideStart id="nope" />);
    expect(screen.getByText('No such page')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideStartPage.mockReturnValue(failed);
    rerender(<GuideStart id="nope" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
