import { describe, expect, it } from 'vitest';

import { gatedFindings, violations, type AllowEntry, type AuditReport } from './check-audit';

const advisory = (id: string, name: string, severity: string) => ({
  url: `https://github.com/advisories/${id}`,
  title: `${name} is vulnerable`,
  severity,
  name,
});

// braces is the root advisory; micromatch is vulnerable only through it (a string `via`).
const report: AuditReport = {
  vulnerabilities: {
    braces: { via: [advisory('GHSA-aaaa', 'braces', 'high')] },
    micromatch: { via: ['braces'] },
    handlebars: {
      via: [
        advisory('GHSA-bbbb', 'handlebars', 'critical'),
        advisory('GHSA-cccc', 'handlebars', 'moderate'),
      ],
    },
  },
};

const entry = (over: Partial<AllowEntry> = {}): AllowEntry => ({
  advisory: 'GHSA-aaaa',
  package: 'braces',
  reason: 'no fixed release',
  added: '2026-10-08',
  expires: '2026-12-31',
  ...over,
});

describe('gatedFindings', () => {
  it('keeps the high and critical root advisories only', () => {
    expect(gatedFindings(report).map((f) => `${f.advisory} ${f.package} ${f.severity}`)).toEqual([
      'GHSA-aaaa braces high',
      'GHSA-bbbb handlebars critical',
    ]);
  });
});

describe('violations', () => {
  const findings = gatedFindings(report);

  it('fails an advisory that is not allow-listed', () => {
    const out = violations(findings, [entry()], '2026-10-08');
    expect(out).toHaveLength(1);
    expect(out[0]).toContain('GHSA-bbbb in handlebars');
  });

  it('passes when every finding is listed and unexpired', () => {
    const all = [entry(), entry({ advisory: 'GHSA-bbbb', package: 'handlebars' })];
    expect(violations(findings, all, '2026-12-31')).toEqual([]);
  });

  it('fails an expired entry', () => {
    const all = [
      entry({ expires: '2026-10-07' }),
      entry({ advisory: 'GHSA-bbbb', package: 'handlebars' }),
    ];
    expect(violations(findings, all, '2026-10-08')).toEqual([
      'GHSA-aaaa in braces: the allow-list entry expired on 2026-10-07; re-review it or upgrade',
    ]);
  });

  it('fails an entry whose advisory is no longer reported', () => {
    expect(violations([], [entry()], '2026-10-08')).toEqual([
      'GHSA-aaaa in braces is no longer reported: drop it from audit-allowlist.json',
    ]);
  });
});
