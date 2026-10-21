/**
 * Vite plugin: the opened URL's page files start downloading from index.html, not from the entry
 * script. Without it a lazy page costs a serial round trip: html, then the entry and its static
 * imports, then (only once the entry runs and its router imports the page) the page chunk, its
 * shared chunks and its stylesheet. For a client 280 ms away that is the longest chain of the load.
 * The plugin writes a small inline script into the page's head: a table of URL path -> the files
 * of that page's chunk (its static closure minus the entry's own, plus its stylesheets), and the
 * links that preload the opened path's files. Unknown paths preload nothing. Build only.
 */
import type { Plugin } from 'vite';

/** URL path -> the manifest sources of the page chunks that URL opens (a path not listed: none). */
export const ROUTE_PAGES: Record<string, string[]> = {
  '/ideas': ['src/pages/trader-ideas/index.ts', 'src/widgets/edge-signals/index.ts'],
  '/screeners': ['src/pages/trader-screeners/index.ts'],
  '/edges': ['src/pages/trader-edges/index.ts'],
  '/regime': ['src/pages/trader-regime/index.ts'],
  '/calendar': ['src/pages/trader-calendar/index.ts'],
  '/explore': ['src/pages/trader-explore/index.ts'],
  '/admin/ingestion': ['src/pages/admin-ingestion/index.ts'],
};

/** Chunks every listed path needs early: the saved page cache the loaders wait for (briefly). */
const EVERY_PAGE = ['src/entities/page-cache/index.ts'];

/** The fonts the first paint uses (hashed file names found in the bundle): after the scripts. */
const FONT = /ibm-plex-(sans-latin-(400|600)|mono-latin-400)-normal-.*\.woff2$/;

/** What the plugin needs of a Rollup output chunk (asset entries are skipped). */
export interface ChunkInfo {
  type: 'chunk';
  fileName: string;
  imports: string[];
  isEntry: boolean;
  facadeModuleId: string | null;
  viteMetadata?: { importedCss: Set<string> };
}

type Bundle = Record<string, ChunkInfo | { type: 'asset' }>;

/** The chunk's file and every file it imports statically, with the stylesheets of each. */
function closure(bundle: Bundle, root: string, into = new Set<string>()): Set<string> {
  if (into.has(root)) return into;
  into.add(root);
  const chunk = bundle[root];
  if (chunk?.type !== 'chunk') return into;
  chunk.viteMetadata?.importedCss.forEach((css) => into.add(css));
  chunk.imports.forEach((file) => closure(bundle, file, into));
  return into;
}

/** URL path -> files to preload (the pages' closures minus what the entry already loads). */
export function preloadTable(
  bundle: Bundle,
  pages: Record<string, string[]> = ROUTE_PAGES,
): Record<string, string[]> {
  const chunks = Object.values(bundle).filter((c): c is ChunkInfo => c.type === 'chunk');
  const entry = chunks.find((c) => c.isEntry);
  const own = entry ? closure(bundle, entry.fileName) : new Set<string>();
  const fonts = Object.keys(bundle).filter((file) => FONT.test(file));
  const table: Record<string, string[]> = {};
  for (const [path, sources] of Object.entries(pages)) {
    const files = new Set<string>();
    for (const source of [...sources, ...EVERY_PAGE]) {
      const chunk = chunks.find((c) =>
        c.facadeModuleId?.replaceAll('\\', '/').endsWith(`/${source}`),
      );
      if (!chunk) throw new Error(`route-preload: no chunk for ${source} (${path})`);
      closure(bundle, chunk.fileName, files);
    }
    table[path] = [...[...files].filter((file) => !own.has(file)), ...fonts];
  }
  return table;
}

/** The inline script: the table and the few lines that add the opened path's links. */
export function preloadScript(table: Record<string, string[]>, base: string): string {
  return `(function(){var t=${JSON.stringify(table)},l=t[location.pathname.replace(/\\/$/,'')];if(!l)return;l.forEach(function(f){var k=document.createElement('link'),e=f.split('.').pop();if(e=='css'||e=='woff2'){k.rel='preload';k.setAttribute('as',e=='css'?'style':'font');if(e=='woff2')k.crossOrigin=''}else k.rel='modulepreload';k.onload=k.onerror=function(){k.remove()};k.href=${JSON.stringify(base)}+f;document.head.appendChild(k)})})();`;
}

/** Whether the bundle is the app's (it has a listed page): the Storybook build carries none. */
export function hasPages(bundle: Bundle, pages: Record<string, string[]> = ROUTE_PAGES): boolean {
  const sources = Object.values(pages).flat();
  return Object.values(bundle).some(
    (c) =>
      c.type === 'chunk' &&
      sources.some((source) => c.facadeModuleId?.replaceAll('\\', '/').endsWith(`/${source}`)),
  );
}

export function routePreload(): Plugin {
  let base = '/';
  return {
    name: 'route-preload',
    apply: 'build',
    configResolved(config) {
      base = config.base;
    },
    transformIndexHtml: {
      order: 'post',
      handler(_html, ctx) {
        if (!ctx.bundle || !hasPages(ctx.bundle)) return undefined;
        const table = preloadTable(ctx.bundle);
        return [{ tag: 'script', children: preloadScript(table, base), injectTo: 'head-prepend' }];
      },
    },
  };
}
