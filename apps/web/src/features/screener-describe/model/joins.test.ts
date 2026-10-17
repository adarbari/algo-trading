import { describe, expect, it } from 'vitest';

import { joinToken } from './joins';

const part = (join: 'and' | 'or' | 'and_not' | null, join_words: string) => ({
  join,
  join_words,
});

describe('joinToken', () => {
  it('shows or and and-not always, with the trader label', () => {
    expect(joinToken(part('or', 'or'))).toEqual({ join: 'or', label: 'or', words: 'or' });
    expect(joinToken(part('and_not', 'except'))).toEqual({
      join: 'and_not',
      label: 'but not',
      words: 'except',
    });
    expect(joinToken(part('and_not', ''))).toEqual({
      join: 'and_not',
      label: 'but not',
      words: '',
    });
  });

  it('hides a plain and, whatever the case or spacing', () => {
    for (const words of ['', 'and', ' AND ', 'with', 'plus', 'also', 'then', ',']) {
      expect(joinToken(part('and', words))).toBeNull();
    }
  });

  it('shows an and the trader worded otherwise', () => {
    for (const words of [
      'but',
      'yet',
      'while',
      'although',
      'as long as',
      'only if',
      'provided that',
    ]) {
      expect(joinToken(part('and', words))).toEqual({ join: 'and', label: 'and', words });
    }
  });

  it('shows nothing without a join', () => {
    expect(joinToken(part(null, 'but'))).toBeNull();
    expect(joinToken({ join_words: '' })).toBeNull();
  });
});
