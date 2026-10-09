import { describe, expect, it } from 'vitest';

import {
  measure,
  staticClosure,
  table,
  updated,
  violations,
  type Manifest,
} from './check-bundle-budgets';
import { shrunk, type Budgets } from './perf-budgets';

// index.html (entry) -> react; page "a" -> react + shared + its css; the chart engine is lazy.
const manifest: Manifest = {
  'index.html': {
    file: 'assets/index.js',
    isEntry: true,
    imports: ['_react.js'],
    css: ['assets/index.css'],
  },
  '_react.js': { file: 'assets/react.js' },
  '_shared.js': { file: 'assets/shared.js', imports: ['_react.js'] },
  'src/pages/a/index.ts': {
    file: 'assets/a.js',
    isDynamicEntry: true,
    imports: ['_react.js', '_shared.js', 'index.html'],
    css: ['assets/a.css'],
  },
  'src/pages/b/index.ts': { file: 'assets/b.js', isDynamicEntry: true, imports: ['_react.js'] },
  'design-system/components/Chart/engine.ts': { file: 'assets/engine.js', isDynamicEntry: true },
};
const SIZES: Record<string, number> = {
  'assets/index.js': 30,
  'assets/index.css': 5,
  'assets/react.js': 100,
  'assets/shared.js': 7,
  'assets/a.js': 20,
  'assets/a.css': 3,
  'assets/b.js': 4,
  'assets/engine.js': 60,
};
const gzipSize = (file: string): number => SIZES[file] ?? 0;
const LAZY = ['design-system/components/Chart/engine.ts'];

const budgets: Budgets['bundle'] = {
  entry_gzip_bytes: 40,
  entry_closure_gzip_bytes: 140,
  lazy_only: LAZY,
  routes: { 'src/pages/a/index.ts': 30, 'src/pages/b/index.ts': 4 },
};

describe('staticClosure', () => {
  it('follows static imports only, through a cycle back to the entry', () => {
    expect([...staticClosure(manifest, 'src/pages/a/index.ts')].sort()).toEqual([
      '_react.js',
      '_shared.js',
      'index.html',
      'src/pages/a/index.ts',
    ]);
  });
});

describe('measure', () => {
  it('sizes the entry, its closure and what each page adds beyond the closure', () => {
    const sizes = measure(manifest, gzipSize, LAZY);
    expect(sizes.entry).toBe(35); // its own JS + CSS, not the vendor chunk
    expect(sizes.entryClosure).toBe(135);
    expect(sizes.routes).toEqual({ 'src/pages/a/index.ts': 30, 'src/pages/b/index.ts': 4 });
    expect(sizes.leaked).toEqual([]);
  });

  it('reports a lazy-only library that the entry imports statically', () => {
    const leaky: Manifest = {
      ...manifest,
      'index.html': {
        ...manifest['index.html'],
        imports: ['design-system/components/Chart/engine.ts'],
      } as never,
    };
    expect(measure(leaky, gzipSize, LAZY).leaked).toEqual(LAZY);
  });

  it('needs exactly one entry', () => {
    expect(() => measure({ '_x.js': { file: 'x.js' } }, gzipSize, [])).toThrow(/one entry/);
  });
});

describe('violations', () => {
  it('is empty within every budget', () => {
    expect(violations(measure(manifest, gzipSize, LAZY), budgets)).toEqual([]);
  });

  it('names the entry, a page over its budget, a page without one and a leak', () => {
    const sizes = measure(manifest, gzipSize, LAZY);
    const out = violations(
      { ...sizes, entry: 41, routes: { ...sizes.routes, 'src/pages/c/index.ts': 1 }, leaked: LAZY },
      { ...budgets, routes: { 'src/pages/a/index.ts': 10, 'src/pages/b/index.ts': 4 } },
    );
    expect(out.join('\n')).toMatch(/entry chunk.*41 B.*budget of 40 B/);
    expect(out.join('\n')).toMatch(/src\/pages\/a\/index.ts.*30 B.*10 B/);
    expect(out.join('\n')).toMatch(/src\/pages\/c\/index.ts: no budget/);
    expect(out.join('\n')).toMatch(/Chart\/engine.ts is in the entry's static imports/);
  });
});

describe('updated and shrunk', () => {
  it('sets a first budget at the measured size + 10 % (rounded up to 100 B)', () => {
    expect(shrunk(undefined, 12_000)).toBe(13_200);
  });

  it('never raises a budget, only shrinks it', () => {
    expect(shrunk(20_000, 12_000)).toBe(13_200);
    expect(shrunk(10_000, 12_000)).toBe(10_000);
  });

  it('drops pages that no longer exist and adds new ones', () => {
    const sizes = measure(manifest, gzipSize, LAZY);
    const after = updated(sizes, {
      bundle: { ...budgets, routes: { 'src/pages/gone/index.ts': 5 } },
      e2e: {},
    });
    expect(Object.keys(after.bundle.routes).sort()).toEqual([
      'src/pages/a/index.ts',
      'src/pages/b/index.ts',
    ]);
    expect(after.bundle.entry_gzip_bytes).toBe(40); // 35 + 10 % is 100 after rounding: kept
  });
});

describe('table', () => {
  it('marks a size over its budget', () => {
    const sizes = measure(manifest, gzipSize, LAZY);
    const text = table(sizes, { ...budgets, entry_gzip_bytes: 10 });
    expect(text).toMatch(/entry chunk \(JS \+ CSS\) \| 0.0 kB \| 0.0 kB \| OVER/);
    expect(text).toMatch(/src\/pages\/b\/index.ts \| 0.0 kB \| 0.0 kB \| ok/);
  });
});
