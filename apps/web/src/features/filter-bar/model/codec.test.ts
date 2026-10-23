import { describe, expect, it } from 'vitest';

import { decodeFilters, encodeFilters } from './codec';
import type { FilterState } from './state';

const SPEC = 'decision:QUALIFIED,WATCH;dte:..14;rsi_14@v1:30..70;!liq:risk';

describe('the f grammar', () => {
  it('reads the spec example', () => {
    expect(decodeFilters(SPEC)).toEqual([
      { id: 'decision', values: ['QUALIFIED', 'WATCH'], active: true },
      { id: 'dte', max: 14, active: true },
      { id: 'rsi_14@v1', min: 30, max: 70, active: true },
      { id: 'liq', values: ['risk'], active: false },
    ]);
  });

  it('writes the spec example back unchanged', () => {
    expect(encodeFilters(decodeFilters(SPEC))).toBe(SPEC);
  });

  it.each([
    ['earn:..5s', { id: 'earn', within: { amount: 5, unit: 'sessions' }, active: true }],
    ['earn:..14d', { id: 'earn', within: { amount: 14, unit: 'days' }, active: true }],
    ['x:5..', { id: 'x', min: 5, active: true }],
    ['x:-2.5..-1', { id: 'x', min: -2.5, max: -1, active: true }],
    ['x:1e-7..', { id: 'x', min: 1e-7, active: true }],
    ['x:', { id: 'x', active: true }],
  ] as [string, FilterState][])('reads %s', (text, expected) => {
    expect(decodeFilters(text)).toEqual([expected]);
    expect(decodeFilters(encodeFilters([expected]))).toEqual([expected]);
  });

  it('percent-encodes the separators in ids and values', () => {
    const filters: FilterState[] = [
      {
        id: 'a:b;c',
        values: ['x,y', 'p;q', 'r:s', '50%', '!bang', 'a..b', '..5s', ' sp'],
        active: true,
      },
    ];
    const text = encodeFilters(filters);
    expect(text).not.toMatch(/[^;]*;.*;/);
    expect(text.split(';')).toHaveLength(1);
    expect(decodeFilters(text)).toEqual(filters);
  });

  it('ignores malformed entries instead of throwing', () => {
    for (const bad of [
      '',
      'nocolon',
      ':x',
      'x:a..b',
      'x:..',
      'x:..5q',
      'x:%ZZ',
      'x:1..2,3',
      ';;;',
    ]) {
      expect(() => decodeFilters(bad)).not.toThrow();
    }
    expect(decodeFilters('nocolon;ok:a;x:a..b;y:..;z:%ZZ')).toEqual([
      { id: 'ok', values: ['a'], active: true },
    ]);
    expect(decodeFilters(undefined)).toEqual([]);
  });

  it('keeps the first of a repeated id and the given order', () => {
    expect(decodeFilters('b:1;a:2;b:3').map((f) => f.id)).toEqual(['b', 'a']);
    expect(
      encodeFilters([
        { id: 'b', active: true },
        { id: 'a', active: true },
        { id: 'b', active: false },
      ]),
    ).toBe('b:;a:');
  });

  it('round-trips generated filters and settles to one spelling', () => {
    let seed = 7;
    const rand = (n: number) => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed % n;
    };
    const alphabet = ['a', 'Z', '0', ',', ';', ':', '%', '.', '!', ' ', '-', '@', 'é', '/', '='];
    const text = () =>
      Array.from({ length: 1 + rand(6) }, () => alphabet[rand(alphabet.length)]).join('');
    for (let i = 0; i < 400; i++) {
      const filters: FilterState[] = [];
      for (let k = 0; k < rand(5); k++) {
        const id = `f${String(k)}${text()}`;
        const active = rand(2) === 0;
        const kind = rand(4);
        if (kind === 0)
          filters.push({ id, values: Array.from({ length: 1 + rand(3) }, text), active });
        else if (kind === 1) filters.push({ id, min: rand(200) - 100 + rand(4) / 4, active });
        else if (kind === 2) {
          filters.push({ id, min: -rand(50), max: rand(50) / 2, active });
        } else
          filters.push({
            id,
            within: { amount: rand(60), unit: rand(2) ? 'days' : 'sessions' },
            active,
          });
      }
      const encoded = encodeFilters(filters);
      expect(decodeFilters(encoded)).toEqual(filters);
      expect(encodeFilters(decodeFilters(encoded))).toBe(encoded);
    }
  });
});
