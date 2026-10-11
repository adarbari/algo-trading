/**
 * The evidence curve of an edge (its own read, `edgeResult.curve`): what the picks of the
 * verdict's basis earned window by window, added up, against the universe, with the in-sample and
 * out-of-sample stretches shaded, the paper record continuing it as a dashed stroke and the
 * spans with no number in a lane. A gap in the data says why through the Guide; a copy's
 * withheld out-of-sample result says so. States: loading, error, unknown, hidden, ready.
 */
import { Chart, Checkbox, Panel, Stack, StatusBadge, Text } from '@algotrade/ui';
import { useState } from 'react';

import { UnknownNote } from '@/entities/availability';
import { EDGE_UNKNOWN_WORDS, useEdgeCurve } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { curveChart, decoyNames } from '../model/curve';

export interface EdgeCurveProps {
  edgeId: string;
}

export function EdgeCurve({ edgeId }: EdgeCurveProps) {
  const query = useEdgeCurve(edgeId);
  const [shown, setShown] = useState<readonly string[]>([]);
  const curve = query.data;
  if (query.isPending) {
    return (
      <Panel
        title="Evidence curve"
        headingLevel={3}
        actions={termHelp('evidence_curve')}
        state="loading"
        loadingLabel="Loading the curve…"
      />
    );
  }
  if (query.isError || !curve) {
    return (
      <Panel
        title="Evidence curve"
        headingLevel={3}
        actions={termHelp('evidence_curve')}
        state="error"
        errorMessage="The curve failed to load."
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (curve.unknown) {
    return (
      <Panel title="Evidence curve" headingLevel={3} actions={termHelp('evidence_curve')}>
        <UnknownNote unknown={curve.unknown} kindWords={EDGE_UNKNOWN_WORDS} />
      </Panel>
    );
  }
  const chart = curveChart(curve, shown);
  const decoys = decoyNames(curve);
  return (
    <Panel title="Evidence curve" headingLevel={3} actions={termHelp('evidence_curve')}>
      <Stack gap={2}>
        {curve.hidden && (
          <Stack direction="row" gap={1} align="center">
            <StatusBadge tone="neutral">Out-of-sample hidden</StatusBadge>
            {termHelp('show_out_of_sample')}
          </Stack>
        )}
        <Text size="xs" tone="muted">
          {curve.kind === 'excess_wins' ? 'Excess wins, cumulative' : 'Excess return, cumulative'}
        </Text>
        {decoys.length > 0 && (
          <Stack as="ul" direction="row" gap={3} align="center" wrap aria-label="Decoys to draw">
            {decoys.map((name) => (
              <Stack as="li" key={name}>
                <Checkbox
                  label={name}
                  checked={shown.includes(name)}
                  onCheckedChange={(on) => {
                    setShown((now) => (on ? [...now, name] : now.filter((n) => n !== name)));
                  }}
                />
              </Stack>
            ))}
          </Stack>
        )}
        <Chart
          label="Evidence curve of the picks against the universe"
          series={chart.series}
          bands={chart.bands}
          lanes={chart.lanes}
          format={chart.format}
          emptyMessage="No windows to draw"
        />
        {curve.gaps.map((gap) =>
          gap.unknown ? (
            <UnknownNote
              key={`${gap.from}:${gap.to}`}
              unknown={gap.unknown}
              kindWords={EDGE_UNKNOWN_WORDS}
            />
          ) : null,
        )}
      </Stack>
    </Panel>
  );
}
