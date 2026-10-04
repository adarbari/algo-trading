/**
 * `predev` / `prestorybook` guard: fail fast, with the fix, when node_modules does not match
 * package-lock.json (a pull changed the dependencies and `npm ci` was not re-run). Without it
 * a long-running `npm run dev` dies later with "Failed to resolve import ...". Compares the
 * lockfile with npm's own record of what is installed (node_modules/.package-lock.json).
 * Plain Node (type stripping): it must run even when node_modules is broken.
 */
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

interface LockEntry {
  version?: string;
  link?: boolean;
  optional?: boolean;
  os?: unknown;
  cpu?: unknown;
}
export interface Lockfile {
  packages?: Record<string, LockEntry>;
}

export const FIX = 'run `make web-install`';

/** Why `installed` (node_modules/.package-lock.json) is out of date with `lock`, else null. */
export function staleReason(lock: Lockfile, installed: Lockfile | null): string | null {
  if (installed === null) return 'node_modules has no .package-lock.json (not installed)';
  const have = installed.packages ?? {};
  for (const [path, entry] of Object.entries(lock.packages ?? {})) {
    if (path === '' || entry.link) continue; // the root and workspace links are not installed copies
    const found = have[path];
    if (found === undefined) {
      // Platform-specific optional packages are legitimately absent.
      if (entry.optional || entry.os !== undefined || entry.cpu !== undefined) continue;
      return `${path}@${entry.version ?? '?'} is not installed`;
    }
    if (found.version !== entry.version) {
      return `${path} is ${found.version ?? '?'} but package-lock.json wants ${entry.version ?? '?'}`;
    }
  }
  return null;
}

function read(path: string): Lockfile | null {
  return existsSync(path) ? (JSON.parse(readFileSync(path, 'utf8')) as Lockfile) : null;
}

if (
  process.argv[1] &&
  realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))
) {
  const root = new URL('../', import.meta.url);
  const lock = read(fileURLToPath(new URL('package-lock.json', root))) ?? {};
  const installed = read(fileURLToPath(new URL('node_modules/.package-lock.json', root)));
  const reason = staleReason(lock, installed);
  if (reason !== null) {
    console.error(`node_modules is out of date with package-lock.json (${reason}) — ${FIX}.`);
    process.exit(1);
  }
}
