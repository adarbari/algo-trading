import { describe, expect, it } from 'vitest';

import { groupByKind } from './group';
import { fromRest } from './rest';
import { unknownText, unknownWord } from './unknown';
import { cellText, cellWord, reasonLabel, reasonText } from './words';

describe('groupByKind', () => {
  it('merges the gaps of one kind, keeps each cause apart and lists a failure first', () => {
    const chain = {
      links: [{ level: 'TABLE', subject: 't', status: 'MISSING', message: '' }],
    } as const;
    const groups = groupByKind([
      {
        kind: 'NOT_STORED',
        features: ['a'],
        guideTerm: 'unavailable_not_stored',
        kindText: 'not available for this instrument',
        cause: null,
      },
      {
        kind: 'SYSTEM',
        features: ['b', 'c'],
        guideTerm: 'unavailable_system',
        kindText: 'not available because of a system error',
        cause: chain,
      },
      {
        kind: 'SYSTEM',
        features: ['c', 'd'],
        guideTerm: 'unavailable_system',
        kindText: 'not available because of a system error',
        cause: chain,
      },
    ]);
    expect(groups.map((g) => [g.kind, g.features, g.causes.length])).toEqual([
      ['SYSTEM', ['b', 'c', 'd'], 2],
      ['NOT_STORED', ['a'], 0],
    ]);
  });
});

describe('unknown words', () => {
  const base = { guideTerm: 'g', cause: null } as const;
  const words = (kind: string) => `words of ${kind}`;
  it('goes by kind, never by code, except an explained null', () => {
    expect(
      unknownText({ ...base, code: 'NO_ROW', kind: 'SYSTEM', kindText: words('SYSTEM') }),
    ).toBe('words of SYSTEM');
    expect(
      unknownText({ ...base, code: 'NO_ROW', kind: 'NOT_STORED', kindText: words('NOT_STORED') }),
    ).toBe('words of NOT_STORED');
    expect(
      unknownText({
        ...base,
        code: 'EXPLAINED',
        kind: 'NOT_STORED',
        reason: 'NO_TRADE',
        kindText: words('NOT_STORED'),
      }),
    ).toBe('no trade on this session: no bar');
    expect(unknownText(null)).toBe('not known');
    expect(unknownWord({ ...base, code: 'NO_ROW', kind: 'NOT_APPLICABLE', kindText: '' })).toBe(
      'n/a',
    );
    expect(unknownWord({ ...base, code: 'NULL', kind: 'ILLIQUID', kindText: '' })).toBe('Illiquid');
    expect(unknownWord({ ...base, code: 'NO_ROW', kind: 'SYSTEM', kindText: '' })).toBe('Unknown');
  });
});

describe('fromRest', () => {
  it('reads a REST gap as the GraphQL shape, a missing chain as none', () => {
    const [gap, bare] = fromRest([
      {
        kind: 'SYSTEM',
        features: ['x'],
        guide_term: 'unavailable_system',
        kind_text: 'not available because of a system error',
        cause: [{ level: 'STEP', subject: 's', status: 'FAILED', message: 'm', run_id: 'r1' }],
      },
      {
        kind: 'NOT_STORED',
        features: [],
        guide_term: 'unavailable_not_stored',
        kind_text: 'not available for this instrument',
        cause: null,
      },
    ]);
    expect(gap?.guideTerm).toBe('unavailable_system');
    expect(gap?.cause?.links[0]).toMatchObject({ subject: 's', runId: 'r1' });
    expect(bare?.cause).toBeNull();
    expect(fromRest(undefined)).toEqual([]);
  });
});

describe('cell words', () => {
  it('draws a cell by its kind: the same NO_ROW is a system gap or not stored', () => {
    expect(cellText('SYSTEM', 'NO_ROW', 'system words', 'null means x')).toBe('system words');
    expect(cellText('NOT_STORED', 'NO_ROW', 'stored words', 'null means x')).toBe('null means x');
    expect(cellText(null, null, null)).toBe('not known');
    expect(cellWord('NOT_APPLICABLE', 'NO_ROW')).toBe('n/a');
    expect(cellWord('ILLIQUID', 'NULL')).toBe('Illiquid');
    expect([
      cellWord('SYSTEM', 'NO_ROW'),
      cellWord('NOT_STORED', 'NULL'),
      cellWord(null, null),
    ]).toEqual(['Unknown', 'Unknown', 'Unknown']);
  });

  it('words each explained absence, exhaustively (ADR 0046)', () => {
    const reasons = ['NO_TRADE', 'NOT_ANNOUNCED', 'NEW_LISTING', 'FEW_BARS'] as const;
    expect(reasons.map(reasonLabel)).toEqual([
      'No trade',
      'Not announced',
      'New listing',
      'Too few trades',
    ]);
    expect(reasons.map((r) => cellWord('NOT_APPLICABLE', 'EXPLAINED', r))).toEqual(
      reasons.map(reasonLabel),
    );
    expect(reasons.map(reasonText)).toEqual([
      'no trade on this session: no bar',
      'the next report date is not announced',
      'listed too recently for the window',
      'trades too rarely to fill the window',
    ]);
    expect(cellWord('NOT_STORED', 'EXPLAINED')).toBe('Unknown');
  });
});
