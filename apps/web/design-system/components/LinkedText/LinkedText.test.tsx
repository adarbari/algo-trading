import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectNoA11yViolations } from '../../testing';
import { LinkedText, splitTerms, type LinkedTerm } from './LinkedText';

const TEXT = 'The Sahm rule and the yield curve flag a recession; the Sahm rule is monthly.';
const SAHM: LinkedTerm = {
  text: 'Sahm rule',
  href: 'https://fred.stlouisfed.org/series/SAHMREALTIME',
};
const CURVE: LinkedTerm = {
  text: 'yield curve',
  href: 'https://fred.stlouisfed.org/series/T10Y3M',
  title: 'FRED',
};

describe('splitTerms', () => {
  it('cuts at the first occurrence of each term, in sentence order', () => {
    const { parts, unmatched } = splitTerms(TEXT, [CURVE, SAHM]);
    expect(parts.map((p) => p.text).join('')).toBe(TEXT);
    expect(parts.filter((p) => p.href !== undefined).map((p) => p.text)).toEqual([
      'Sahm rule',
      'yield curve',
    ]);
    expect(parts.find((p) => p.text === 'yield curve')?.title).toBe('FRED');
    expect(unmatched).toEqual([]);
  });

  it('reports terms that are absent, empty or overlapping, and links the rest', () => {
    const { parts, unmatched } = splitTerms(TEXT, [
      SAHM,
      { text: 'inverted', href: 'https://example.org/a' },
      { text: '', href: 'https://example.org/b' },
      { text: 'rule and', href: 'https://example.org/c' },
    ]);
    expect(unmatched).toEqual(expect.arrayContaining(['inverted', '', 'rule and']));
    expect(parts.filter((p) => p.href !== undefined)).toHaveLength(1);
    expect(parts.map((p) => p.text).join('')).toBe(TEXT);
  });

  it('returns the sentence as one plain part without terms', () => {
    expect(splitTerms(TEXT, [])).toEqual({ parts: [{ text: TEXT }], unmatched: [] });
  });
});

describe('LinkedText', () => {
  it('renders a part with an href as a real anchor and the rest as text', () => {
    const { container } = render(<LinkedText parts={splitTerms(TEXT, [CURVE, SAHM]).parts} />);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAccessibleName('Sahm rule, opens in a new tab');
    expect(links[0]).toHaveAttribute('href', SAHM.href);
    expect(links[0]?.getAttribute('rel')).toContain('noopener');
    expect(links[1]).toHaveAttribute('title', 'FRED');
    expect(container.textContent.replaceAll(', opens in a new tab', '')).toBe(TEXT);
  });

  it('renders plain parts without links', () => {
    render(<LinkedText parts={[{ text: 'Plain' }]} tone="muted" size="sm" />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Plain')).toHaveAttribute('data-tone', 'muted');
    expect(screen.getByText('Plain')).toHaveAttribute('data-size', 'sm');
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<LinkedText parts={splitTerms(TEXT, [SAHM, CURVE]).parts} />);
    await expectNoA11yViolations(container);
  });
});
