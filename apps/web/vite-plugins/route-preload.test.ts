import { describe, expect, it } from 'vitest';

import {
  hasPages,
  preloadScript,
  preloadTable,
  ROUTE_PAGES,
  type ChunkInfo,
} from './route-preload';

const chunk = (fileName: string, over: Partial<ChunkInfo> = {}): ChunkInfo => ({
  type: 'chunk',
  fileName,
  imports: [],
  isEntry: false,
  facadeModuleId: null,
  ...over,
});

const bundle = {
  'assets/index.js': chunk('assets/index.js', { isEntry: true, imports: ['assets/react.js'] }),
  'assets/react.js': chunk('assets/react.js'),
  'assets/page.js': chunk('assets/page.js', {
    facadeModuleId: '/repo/apps/web/src/pages/trader-ideas/index.ts',
    imports: ['assets/react.js', 'assets/table.js'],
    viteMetadata: { importedCss: new Set(['assets/page.css']) },
  }),
  'assets/table.js': chunk('assets/table.js', { imports: ['assets/react.js'] }),
  'assets/cache.js': chunk('assets/cache.js', {
    facadeModuleId: '/repo/apps/web/src/entities/page-cache/index.ts',
  }),
  'assets/ibm-plex-sans-latin-400-normal-AbC.woff2': { type: 'asset' as const },
  'assets/ibm-plex-sans-latin-300-normal-AbC.woff2': { type: 'asset' as const },
  'assets/early.js': chunk('assets/early.js', {
    facadeModuleId: '/repo/apps/web/src/app/router/early-reads.ts',
  }),
  'assets/signals.js': chunk('assets/signals.js', {
    facadeModuleId: '/repo/apps/web/src/widgets/edge-signals/index.ts',
  }),
};

/** Runs the generated inline script as the browser would. */
function runScript(script: string): () => void {
  // eslint-disable-next-line @typescript-eslint/no-implied-eval -- the script under test
  return new Function(script) as () => void;
}

describe('preloadTable', () => {
  it("lists a page's closure and stylesheets, minus the files the entry already loads", () => {
    const table = preloadTable(bundle, { '/ideas': ['src/pages/trader-ideas/index.ts'] });
    expect(table['/ideas']).toEqual([
      'assets/page.js',
      'assets/page.css',
      'assets/table.js',
      'assets/cache.js', // every page needs the saved page cache
      'assets/early.js', // and the start-up read of its data
      'assets/ibm-plex-sans-latin-400-normal-AbC.woff2', // a first-paint font, after the scripts
    ]);
  });

  it('joins the files of every source of a path', () => {
    const table = preloadTable(bundle, {
      '/ideas': ['src/pages/trader-ideas/index.ts', 'src/widgets/edge-signals/index.ts'],
    });
    expect(table['/ideas']).toContain('assets/signals.js');
  });

  it('fails the build when a listed page has no chunk (a renamed page would lose its preload)', () => {
    expect(() => preloadTable(bundle)).toThrow(/no chunk for src\/pages/);
  });

  it('names only pages that exist as lazy page entries', () => {
    for (const sources of Object.values(ROUTE_PAGES)) {
      sources.forEach((s) => {
        expect(s).toMatch(/^src\/(pages|widgets)\//);
      });
    }
  });
});

describe('hasPages', () => {
  it("is true for the app's bundle and false for one with no listed page (Storybook)", () => {
    expect(hasPages(bundle, { '/ideas': ['src/pages/trader-ideas/index.ts'] })).toBe(true);
    expect(hasPages({ 'assets/index.js': bundle['assets/index.js'] })).toBe(false);
  });
});

describe('preloadScript', () => {
  it('is one line of valid JavaScript carrying the table and the base', () => {
    const script = preloadScript({ '/ideas': ['assets/a.js'] }, '/');
    expect(script).not.toContain('\n');
    expect(script).toContain('"/ideas":["assets/a.js"]');
    expect(() => runScript(script)).not.toThrow();
  });

  it('adds modulepreload links for scripts and preload-as-style links for stylesheets', () => {
    window.history.replaceState({}, '', '/ideas');
    document.head.innerHTML = '';
    runScript(
      preloadScript({ '/ideas': ['assets/a.js', 'assets/a.css', 'assets/f.woff2'] }, '/'),
    )();
    const links = Array.from(document.head.querySelectorAll('link')).map((l) => [
      l.getAttribute('rel'),
      l.getAttribute('href'),
      l.getAttribute('as'),
    ]);
    expect(links).toEqual([
      ['modulepreload', '/assets/a.js', null],
      ['preload', '/assets/a.css', 'style'],
      ['preload', '/assets/f.woff2', 'font'],
    ]);
  });

  it('preloads nothing for a path it does not know', () => {
    window.history.replaceState({}, '', '/guide');
    document.head.innerHTML = '';
    runScript(preloadScript({ '/ideas': ['assets/a.js'] }, '/'))();
    expect(document.head.querySelectorAll('link')).toHaveLength(0);
  });
});
