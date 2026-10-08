import { describe, expect, it } from 'vitest';

import { groupByKind } from './group';
import { fromRest } from './rest';
import { unknownText, unknownWord } from './unknown';

describe('groupByKind', () => {
  it('merges the gaps of one kind, keeps each cause apart and lists a failure first', () => {
    const chain = {
      links: [{ level: 'TABLE', subject: 't', status: 'MISSING', message: '' }],
    } as const;
    const groups = groupByKind([
      { kind: 'NOT_STORED', features: ['a'], guideTerm: 'unavailable_not_stored', cause: null },
      { kind: 'SYSTEM', features: ['b', 'c'], guideTerm: 'unavailable_system', cause: chain },
      { kind: 'SYSTEM', features: ['c', 'd'], guideTerm: 'unavailable_system', cause: chain },
    ]);
    expect(groups.map((g) => [g.kind, g.features, g.causes.length])).toEqual([
      ['SYSTEM', ['b', 'c', 'd'], 2],
      ['NOT_STORED', ['a'], 0],
    ]);
  });
});

describe('unknown words', () => {
  const base = { guideTerm: 'g', cause: null } as const;
  it('goes by kind, never by code, except an explained null', () => {
    expect(unknownText({ ...base, code: 'NO_ROW', kind: 'SYSTEM' })).toBe(
      'not available because of a system error',
    );
    expect(unknownText({ ...base, code: 'NO_ROW', kind: 'NOT_STORED' })).toBe(
      'not available for this instrument',
    );
    expect(
      unknownText({ ...base, code: 'EXPLAINED', kind: 'NOT_STORED', reason: 'NO_TRADE' }),
    ).toBe('no trade on this session: no bar');
    expect(unknownText(null)).toBe('not known');
    expect(unknownWord({ ...base, code: 'NO_ROW', kind: 'NOT_APPLICABLE' })).toBe('n/a');
    expect(unknownWord({ ...base, code: 'NULL', kind: 'ILLIQUID' })).toBe('Illiquid');
    expect(unknownWord({ ...base, code: 'NO_ROW', kind: 'SYSTEM' })).toBe('Unknown');
  });
});

describe('fromRest', () => {
  it('reads a REST gap as the GraphQL shape, a missing chain as none', () => {
    const [gap, bare] = fromRest([
      {
        kind: 'SYSTEM',
        features: ['x'],
        guide_term: 'unavailable_system',
        cause: [{ level: 'STEP', subject: 's', status: 'FAILED', message: 'm', run_id: 'r1' }],
      },
      { kind: 'NOT_STORED', features: [], guide_term: 'unavailable_not_stored', cause: null },
    ]);
    expect(gap?.guideTerm).toBe('unavailable_system');
    expect(gap?.cause?.links[0]).toMatchObject({ subject: 's', runId: 'r1' });
    expect(bare?.cause).toBeNull();
    expect(fromRest(undefined)).toEqual([]);
  });
});
