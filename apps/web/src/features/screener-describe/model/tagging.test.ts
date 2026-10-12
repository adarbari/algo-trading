import { describe, expect, it } from 'vitest';

import { TAG_LABELS, tagSentence } from './tagging';

const SENTENCE = 'liquid optionable stocks over $5 with a rising moat score';

describe('tagSentence', () => {
  it('tags the given spans with their text label and leaves the words between plain', () => {
    const segments = tagSentence(SENTENCE, [
      { span: 'liquid', kind: 'ask' },
      { span: 'rising moat score', kind: 'gap' },
    ]);
    expect(segments.map((s) => [s.kind, s.text])).toEqual([
      ['ask', 'liquid'],
      ['plain', 'optionable stocks over $5 with a'],
      ['gap', 'rising moat score'],
    ]);
    expect(segments[0]?.label).toBe(TAG_LABELS.ask);
    expect(segments[2]?.label).toBe('not available yet');
    expect(segments[1]?.label).toBeUndefined();
  });

  it('reads back as the sentence', () => {
    const segments = tagSentence(SENTENCE, [{ span: 'over $5', kind: 'applied' }]);
    expect(segments.map((s) => s.text).join(' ')).toBe(SENTENCE);
  });

  it('finds a span ignoring case and keeps the words as typed', () => {
    const [first] = tagSentence('Liquid stocks', [{ span: 'liquid', kind: 'ask' }]);
    expect(first).toMatchObject({ kind: 'ask', text: 'Liquid' });
  });

  it('skips a span that is not in the sentence and one that is empty', () => {
    const segments = tagSentence(SENTENCE, [
      { span: 'not there', kind: 'gap' },
      { span: '', kind: 'ask' },
    ]);
    expect(segments).toHaveLength(1);
    expect(segments[0]).toMatchObject({ kind: 'plain', text: SENTENCE });
  });

  it('lets the earlier span win when two overlap, whatever order they arrive in', () => {
    const segments = tagSentence('very liquid stocks', [
      { span: 'liquid stocks', kind: 'gap' },
      { span: 'very liquid', kind: 'ask' },
    ]);
    expect(segments.map((s) => [s.kind, s.text])).toEqual([
      ['ask', 'very liquid'],
      ['plain', 'stocks'],
    ]);
  });

  it('returns one plain segment with no tags and none for an empty sentence', () => {
    expect(tagSentence('big stocks', [])).toHaveLength(1);
    expect(tagSentence('', [{ span: 'x', kind: 'ask' }])).toEqual([]);
  });
});
