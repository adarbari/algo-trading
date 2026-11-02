/**
 * The sections of one idea's page, each filled from the setup (never written per pick; ADR 0083
 * amendment (b)): why it is here (the setup's thesis and the criteria this name met), the
 * setup's historical exit rule, its evidence (every figure labelled backtested, hypothetical),
 * what could go wrong, and the setup to learn. A section whose input the server could not read
 * says why through its `unknown`; every figure is the server's, formatted here and never derived.
 */
import {
  Button,
  formatValue,
  KeyValue,
  Panel,
  Stack,
  StatStrip,
  StatusBadge,
  Text,
  TextLink,
  type KeyValueItem,
  type StatItem,
} from '@algotrade/ui';

import { UnknownNote } from '@/entities/availability';
import { verdictLabel, verdictTone } from '@/entities/edge';
import { edgeGuidePath } from '@/entities/guide';
import type { IdeaDetail } from '@/entities/idea';
import { CriteriaScorecard } from '@/entities/screen';
import { termHelp } from '@/features/guide-help';

import { exitRuleText } from '../model/exit-rule';

const BASIS = 'Backtested (hypothetical)';

type Exit = IdeaDetail['exitRule'];

function stopItems(exit: Exit): KeyValueItem[] {
  const stop = exit.stop;
  if (!stop) return [];
  const items: KeyValueItem[] = [];
  if (stop.fraction !== null) {
    items.push({
      label: 'Stop, below the entry close',
      value: stop.fraction,
      format: { kind: 'percent', digits: 1 },
    });
  } else if (stop.multiple !== null) {
    items.push({
      label: 'Stop, ATR(14) multiple',
      value: `${formatValue(stop.multiple, { kind: 'number', digits: 1 }).text} × ATR`,
    });
    if (stop.atr !== null) {
      items.push({ label: 'ATR(14)', value: stop.atr, format: { kind: 'currency' } });
    }
  }
  if (stop.beyond !== null) {
    items.push({
      label: 'Winners that went past it',
      value: stop.beyond,
      format: { kind: 'percent', digits: 0 },
    });
  }
  if (stop.winners !== null) {
    items.push({ label: 'Winning trades it rests on', value: stop.winners });
  }
  return items;
}

export function WhySection({ idea }: { idea: IdeaDetail }) {
  const why = idea.why;
  return (
    <Panel title="Why it is here" actions={termHelp('idea_why')}>
      <Stack gap={3}>
        <Text>{why.thesis}</Text>
        {why.unknown ? (
          <UnknownNote unknown={why.unknown} />
        ) : (
          <CriteriaScorecard
            screenerId={why.basisScreener}
            entries={why.criteria.map((c) => ({
              id: c.id,
              field: c.field,
              outcome: c.outcome,
              value: c.value,
              distance: c.distance,
            }))}
            label="Criteria this name met"
          />
        )}
      </Stack>
    </Panel>
  );
}

export function ExitRuleSection({ idea }: { idea: IdeaDetail }) {
  const exit = idea.exitRule;
  const items = stopItems(exit);
  const text = exitRuleText(exit);
  return (
    <Panel title="Historical exit rule" description={BASIS} actions={termHelp('idea_exit_rule')}>
      <Stack gap={3}>
        {exit.unknown ? <UnknownNote unknown={exit.unknown} /> : null}
        {items.length > 0 || exit.holdSessions !== null ? (
          <KeyValue
            label="Exit rule figures"
            items={[
              ...items,
              ...(exit.holdSessions === null
                ? []
                : [{ label: 'Hold, in sessions', value: exit.holdSessions }]),
            ]}
          />
        ) : null}
        {exit.inSampleOnly ? <StatusBadge tone="warning">In-sample trades only</StatusBadge> : null}
        {text ? (
          <Button
            variant="secondary"
            onClick={() => {
              void navigator.clipboard.writeText(text);
            }}
          >
            Copy exit rule as text
          </Button>
        ) : null}
      </Stack>
    </Panel>
  );
}

export function EvidenceSection({ idea }: { idea: IdeaDetail }) {
  const e = idea.evidence;
  const items: StatItem[] = [
    {
      label: 'Verdict',
      value: <StatusBadge tone={verdictTone(e.level)}>{verdictLabel(e.level)}</StatusBadge>,
      sub: BASIS,
    },
    {
      label: 'Out-of-sample lift',
      value: e.liftPts,
      format: { kind: 'number', digits: 1 },
      sub: `points · ${BASIS}`,
    },
    {
      label: 'Out-of-sample trades',
      value: e.oosTrades,
      format: { kind: 'number', digits: 0 },
      sub: BASIS,
    },
    ...(e.basisHorizon === null
      ? []
      : [{ label: 'Hold, in sessions', value: e.basisHorizon, sub: BASIS }]),
  ];
  return (
    <Panel title="Evidence" actions={termHelp('idea_evidence')}>
      <Stack gap={3}>
        <StatStrip label="Evidence figures" items={items} />
        <Text size="sm" tone="secondary">
          {e.result}
        </Text>
      </Stack>
    </Panel>
  );
}

export function RisksSection({ idea }: { idea: IdeaDetail }) {
  const r = idea.risks;
  return (
    <Panel title="What could go wrong" actions={termHelp('idea_risks')}>
      <Stack gap={3}>
        <Text>{r.persistence}</Text>
        {r.unknown ? <UnknownNote unknown={r.unknown} /> : null}
        {r.events.length > 0 ? (
          <Stack gap={1} as="div" aria-label="Events before the hold ends">
            {r.events.map((e) => (
              <Text key={`${e.label}:${e.date}`} size="sm">
                {`${e.name} · ${formatValue(e.date, { kind: 'date', style: 'weekday' }).text}`}
              </Text>
            ))}
          </Stack>
        ) : null}
        {r.watchOut.length > 0 ? (
          <Stack direction="row" gap={2} align="center" wrap>
            {r.watchOut.map((w) => (
              <StatusBadge key={w} tone="warning">
                {w.replaceAll('_', ' ')}
              </StatusBadge>
            ))}
          </Stack>
        ) : null}
      </Stack>
    </Panel>
  );
}

export function LearnSection({
  idea,
  onOpenEdge,
}: {
  idea: IdeaDetail;
  onOpenEdge: (edgeId: string) => void;
}) {
  return (
    <Panel title="Learn this setup" actions={termHelp('idea_learn')}>
      <Stack direction="row" gap={3} align="center" wrap>
        <TextLink href={edgeGuidePath(idea.learn)} icon="book">
          {`About ${idea.setup.edgeName}`}
        </TextLink>
        <Button
          variant="secondary"
          onClick={() => {
            onOpenEdge(idea.learn);
          }}
        >
          Open the setup
        </Button>
      </Stack>
    </Panel>
  );
}
