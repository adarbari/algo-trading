/**
 * The dependency audit gate (docs/ci.md "Dependency audit"): runs `npm audit --json` over every
 * dependency (dev tools included) and fails on any high or critical advisory that is not a
 * reviewed, unexpired entry of audit-allowlist.json. It also fails on an allow-list entry whose
 * advisory is no longer reported (drop it), so the list only holds advisories still waiting for
 * a fixed release. `tsx scripts/check-audit.ts` (`npm run audit:check`).
 */
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export interface AllowEntry {
  advisory: string;
  package: string;
  reason: string;
  added: string;
  expires: string;
}

interface Advisory {
  url: string;
  title: string;
  severity: string;
  name: string;
}

/** The part of `npm audit --json` (auditReportVersion 2) the gate reads. */
export interface AuditReport {
  vulnerabilities: Record<string, { via: (string | Advisory)[] }>;
}

export interface Finding {
  advisory: string;
  package: string;
  severity: string;
  title: string;
}

const GATED = new Set(['high', 'critical']);

/** Every high or critical advisory in the report, once per (advisory, package). */
export function gatedFindings(report: AuditReport): Finding[] {
  const found = new Map<string, Finding>();
  for (const { via } of Object.values(report.vulnerabilities)) {
    for (const v of via) {
      if (typeof v === 'string' || !GATED.has(v.severity)) continue;
      const advisory = v.url.split('/').pop() ?? v.url;
      found.set(`${advisory} ${v.name}`, {
        advisory,
        package: v.name,
        severity: v.severity,
        title: v.title,
      });
    }
  }
  return [...found.values()].sort((a, b) => a.advisory.localeCompare(b.advisory));
}

/** What fails the gate on `today` (ISO date): unlisted findings, expired and stale entries. */
export function violations(findings: Finding[], allowed: AllowEntry[], today: string): string[] {
  const out: string[] = [];
  const listed = (f: Finding): AllowEntry | undefined =>
    allowed.find((e) => e.advisory === f.advisory && e.package === f.package);
  for (const f of findings) {
    const entry = listed(f);
    if (entry === undefined) {
      out.push(
        `${f.severity} ${f.advisory} in ${f.package}: ${f.title} (upgrade, or review it into audit-allowlist.json)`,
      );
    } else if (entry.expires < today) {
      out.push(
        `${f.advisory} in ${f.package}: the allow-list entry expired on ${entry.expires}; re-review it or upgrade`,
      );
    }
  }
  for (const e of allowed) {
    if (!findings.some((f) => f.advisory === e.advisory && f.package === e.package)) {
      out.push(
        `${e.advisory} in ${e.package} is no longer reported: drop it from audit-allowlist.json`,
      );
    }
  }
  return out;
}

function main(): void {
  const audit = spawnSync('npm', ['audit', '--json'], { encoding: 'utf8', maxBuffer: 64 << 20 });
  const report = JSON.parse(audit.stdout) as Partial<AuditReport> & { error?: unknown };
  if (report.error !== undefined || report.vulnerabilities === undefined) {
    console.error(`npm audit failed: ${audit.stdout}${audit.stderr}`);
    process.exit(2);
  }
  const allowList = new URL('../audit-allowlist.json', import.meta.url);
  const { allowed } = JSON.parse(readFileSync(allowList, 'utf8')) as { allowed: AllowEntry[] };
  const findings = gatedFindings({ vulnerabilities: report.vulnerabilities });
  const today = new Date().toISOString().slice(0, 10);
  for (const f of findings) {
    const note = allowed.some((e) => e.advisory === f.advisory) ? ' (allow-listed)' : '';
    console.log(`${f.severity.padEnd(8)} ${f.advisory} ${f.package}${note}`);
  }
  const failed = violations(findings, allowed, today);
  if (failed.length > 0) {
    console.error(
      `\nDependency audit gate failed (docs/ci.md "Dependency audit"):\n- ${failed.join('\n- ')}`,
    );
    process.exit(1);
  }
  console.log(`dependency audit: ${findings.length} high/critical advisories, all allow-listed`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
