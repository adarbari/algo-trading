/**
 * One chip per screener the viewer sees, under the Ideas heading: its name (a link to its
 * results), then its state for the served session in public words: the picks it made when it ran,
 * "partial" with what the run went without (the server's generic words) or "Not run". Informational
 * only: Ideas updates by itself when a run lands, so nothing here starts a run. The counts and
 * reasons are the server's; every state has its Guide help button (ADR 0056: no step or table).
 */
import { Stack, StatusBadge, Text, TextLink } from '@algotrade/ui';

import { screenerResultsPath } from '@/entities/guide';
import type { ScreenerSummary } from '@/entities/idea';
import { termHelp } from '@/features/guide-help';

function picks(n: number): string {
  return `${String(n)} ${n === 1 ? 'pick' : 'picks'}`;
}

function State({ screener }: { screener: ScreenerSummary }) {
  if (screener.notRun) {
    return (
      <>
        <StatusBadge title={screener.notRun.kindText}>Not run</StatusBadge>
        {termHelp(screener.notRun.guideTerm)}
      </>
    );
  }
  if (screener.coverage === 'PARTIAL') {
    const gaps = [...new Set(screener.gaps.map((g) => g.kindText))].join(', ');
    return (
      <>
        <StatusBadge tone="warning">{`${picks(screener.picked)} · partial`}</StatusBadge>
        {gaps && (
          <Text size="sm" tone="muted">
            {gaps}
          </Text>
        )}
        {termHelp('partial_run')}
      </>
    );
  }
  return <StatusBadge tone="positive">{picks(screener.picked)}</StatusBadge>;
}

export function ScreenerChips({ screeners }: { screeners: ScreenerSummary[] }) {
  if (screeners.length === 0) return null;
  return (
    <Stack direction="row" gap={3} wrap align="center" as="ul" aria-label="Screeners">
      {screeners.map((s) => (
        <Stack key={s.id} direction="row" gap={1} wrap align="center" as="li">
          <TextLink href={screenerResultsPath(s.id)} size="sm">
            {s.name}
          </TextLink>
          <State screener={s} />
        </Stack>
      ))}
    </Stack>
  );
}
