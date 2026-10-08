import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoA11yViolations, fakeQuery } from '@/shared/lib/testing';

import { GuideGlossaryIndex } from './GuideGlossaryIndex';
import { GuideTerm } from './GuideTerm';

const hooks = vi.hoisted(() => ({ useGuideIndex: vi.fn(), useGuideTerm: vi.fn() }));

vi.mock('@/entities/guide', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useGuideIndex: hooks.useGuideIndex,
  useGuideTerm: hooks.useGuideTerm,
}));

const index = {
  sections: [{ id: 'glossary', title: 'Glossary', purpose: 'The app’s own words.', entries: 4 }],
  terms: [
    { id: 'unknown', term: 'UNKNOWN', short: 'A value the app does not have.' },
    { id: 'session', term: 'Session', short: 'The day a page reads.' },
    { id: 'not_run', term: 'NOT_RUN', short: 'No run for the session.' },
    { id: 'selection', term: 'Selection', short: 'The rules that pick names.' },
  ],
};
const term = {
  entry: { id: 'not_run', term: 'NOT_RUN', short: 'No run for the session.' },
  body: { segments: [{ text: 'It is not the same as zero hits.' }] },
  seeAlso: [{ id: 'session', term: 'Session', short: 'The day a page reads.' }],
};

beforeEach(() => {
  hooks.useGuideIndex.mockReturnValue(fakeQuery(index));
  hooks.useGuideTerm.mockReturnValue(fakeQuery(term));
});

describe('GuideGlossaryIndex', () => {
  it('lists the terms A to Z under their letters, each a link with its short line', async () => {
    const { container } = render(<GuideGlossaryIndex />);
    expect(screen.getByRole('heading', { level: 1, name: 'Glossary' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'N',
      'S',
      'U',
    ]);
    const s = within(screen.getByRole('region', { name: 'Terms starting with S' }));
    expect(s.getAllByRole('link').map((l) => l.textContent)).toEqual(['Selection', 'Session']);
    expect(s.getByRole('link', { name: 'Session' })).toHaveAttribute(
      'href',
      '/guide/glossary/session',
    );
    expect(s.getByText('The day a page reads.')).toBeInTheDocument();
    expect(
      within(screen.getByRole('navigation', { name: 'Letters' }))
        .getAllByRole('link')
        .map((l) => l.textContent),
    ).toEqual(['N', 'S', 'U']);
    await expectNoA11yViolations(container);
  });

  it('shows an error with a retry and an empty glossary', async () => {
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideIndex.mockReturnValue(failed);
    const { rerender } = render(<GuideGlossaryIndex />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
    hooks.useGuideIndex.mockReturnValue(fakeQuery({ ...index, terms: [] }));
    rerender(<GuideGlossaryIndex />);
    expect(screen.getByText('The glossary has no terms yet.')).toBeInTheDocument();
  });
});

describe('GuideTerm', () => {
  it('shows the term, its definition, the body and the terms to read next', async () => {
    const { container } = render(<GuideTerm id="not_run" />);
    expect(screen.getByRole('heading', { level: 1, name: 'NOT_RUN' })).toBeInTheDocument();
    expect(screen.getByText('No run for the session.')).toBeInTheDocument();
    expect(screen.getByText('It is not the same as zero hits.')).toBeInTheDocument();
    const also = within(screen.getByRole('region', { name: 'See also' }));
    expect(also.getByRole('link', { name: 'Session' })).toHaveAttribute(
      'href',
      '/guide/glossary/session',
    );
    await expectNoA11yViolations(container);
  });

  it('says so for a term that does not exist, and offers a retry when it fails', async () => {
    hooks.useGuideTerm.mockReturnValue(fakeQuery(null));
    const { rerender } = render(<GuideTerm id="nope" />);
    expect(screen.getByText('No such term')).toBeInTheDocument();
    const failed = fakeQuery(undefined, { isError: true });
    hooks.useGuideTerm.mockReturnValue(failed);
    rerender(<GuideTerm id="nope" />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalled();
  });
});
