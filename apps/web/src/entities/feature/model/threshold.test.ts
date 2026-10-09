import { describe, expect, it } from 'vitest';

import type { CatalogueFeature } from './catalogue';
import {
  allowsTolerance,
  coerceValue,
  fieldKind,
  opFor,
  operatorsFor,
  parseList,
  scaleOf,
  shapeOf,
  toStored,
  toTyped,
} from './threshold';

const feature = (dtype: string, unit: string | null = null): CatalogueFeature =>
  ({ dtype, unit }) as CatalogueFeature;

describe('field kinds and operators', () => {
  it('derives the kind from the dtype', () => {
    expect(fieldKind(feature('float32'))).toBe('number');
    expect(fieldKind(feature('int'))).toBe('number');
    expect(fieldKind(feature('bool'))).toBe('bool');
    expect(fieldKind(feature('date'))).toBe('date');
    expect(fieldKind(feature('str'))).toBe('text');
    expect(fieldKind(undefined)).toBe('number');
  });

  it('offers only operators the type allows', () => {
    expect(operatorsFor('number').map((o) => o.value)).toContain('between');
    expect(operatorsFor('bool').map((o) => o.value)).toEqual(['eq', 'ne', 'is_null', 'not_null']);
    expect(opFor('text', 'gte')).toBe('eq');
    // `in` / `not_in` are for text only (ADR 0030): a number uses a comparison or `between`
    expect(operatorsFor('number').map((o) => o.value)).not.toContain('in');
    expect(operatorsFor('text').map((o) => o.value)).toEqual(
      expect.arrayContaining(['in', 'not_in']),
    );
    expect(opFor('number', 'lt')).toBe('lt');
  });

  it('knows the threshold shape and when a tolerance applies', () => {
    expect(shapeOf('gte')).toBe('single');
    expect(shapeOf('between')).toBe('range');
    expect(shapeOf('not_in')).toBe('list');
    expect(shapeOf('is_null')).toBe('none');
    expect(allowsTolerance('gte', 'number')).toBe(true);
    expect(allowsTolerance('eq', 'number')).toBe(false);
    expect(allowsTolerance('gte', 'date')).toBe(false);
  });
});

describe('coerceValue', () => {
  it('keeps a value that still fits and drops one that does not', () => {
    expect(coerceValue('gte', 'number', 5)).toBe(5);
    expect(coerceValue('gte', 'number', 'x')).toBeUndefined();
    expect(coerceValue('between', 'number', 5)).toBeUndefined();
    expect(coerceValue('between', 'number', [1, 2])).toEqual([1, 2]);
    expect(coerceValue('in', 'text', 'HIGH')).toEqual(['HIGH']);
    expect(coerceValue('eq', 'bool', undefined)).toBe(true);
    expect(coerceValue('is_null', 'number', 5)).toBeUndefined();
  });
});

describe('number scale', () => {
  it('types a fraction as a percent without float noise', () => {
    const scale = scaleOf(feature('float32', 'decimal'));
    expect(toTyped(0.07, scale)).toBe(7);
    expect(toStored(7, scale)).toBe(0.07);
    expect(scale.suffix).toBe('%');
  });

  it('prefixes dollars and leaves plain numbers alone', () => {
    expect(scaleOf(feature('float', 'usd_per_share')).prefix).toBe('$');
    expect(scaleOf(feature('int')).step).toBe(1);
  });
});

describe('parseList', () => {
  it('splits text and parses numbers for a number field', () => {
    expect(parseList('HIGH, LOW ,', 'text')).toEqual(['HIGH', 'LOW']);
    expect(parseList('1, 2.5', 'number')).toEqual([1, 2.5]);
    expect(parseList('1, x', 'number')).toBeUndefined();
    expect(parseList('  ', 'text')).toBeUndefined();
  });
});
