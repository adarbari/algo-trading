import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { staleReason } from './check-node-modules';

const lock = {
  packages: {
    '': {},
    'node_modules/a': { version: '1.0.0' },
    'node_modules/@algotrade/ui': { link: true },
    'node_modules/@rolldown/binding-linux': { version: '1.0.0', optional: true, os: ['linux'] },
  },
};

describe('staleReason', () => {
  it('is fine when every package is installed at the locked version', () => {
    expect(staleReason(lock, { packages: { 'node_modules/a': { version: '1.0.0' } } })).toBeNull();
  });

  it('names a locked package that is not installed (a new dependency, e.g. @floating-ui/react)', () => {
    expect(staleReason(lock, { packages: {} })).toMatch(/node_modules\/a@1.0.0 is not installed/);
  });

  it('names a package installed at another version', () => {
    expect(staleReason(lock, { packages: { 'node_modules/a': { version: '0.9.0' } } })).toMatch(
      /is 0.9.0 but package-lock.json wants 1.0.0/,
    );
  });

  it('fails when node_modules was never installed', () => {
    expect(staleReason(lock, null)).toMatch(/not installed/);
  });
});

describe('the predev command', () => {
  it('exits 1 with the fix when node_modules is behind the lockfile', () => {
    const root = mkdtempSync(join(tmpdir(), 'nm-guard-'));
    mkdirSync(join(root, 'scripts'));
    mkdirSync(join(root, 'node_modules'));
    writeFileSync(join(root, 'package-lock.json'), JSON.stringify(lock));
    writeFileSync(join(root, 'node_modules/.package-lock.json'), JSON.stringify({ packages: {} }));
    const script = join(root, 'scripts/check-node-modules.ts');
    copyFileSync(join(import.meta.dirname, 'check-node-modules.ts'), script);
    let stderr = '';
    try {
      execFileSync('node', [script], { stdio: 'pipe' });
    } catch (error) {
      stderr = String((error as { stderr: Buffer }).stderr);
    }
    expect(stderr).toContain('node_modules is out of date with package-lock.json');
    expect(stderr).toContain('make web-install');
  });
});
