/**
 * One indicator card (RG7): the plain name and verdict, where today's value sits on its
 * low-risk to high-risk band with the "on" threshold marked, how it is calculated (the terms
 * linked), where it comes from (the exact series, its cadence and links) with its provenance,
 * then two disclosures: its history over the years (mounted only when opened) and why it
 * matters, what it did before past falls and where to read more.
 */
import {
  Box,
  Disclosure,
  IndicatorRow,
  LinkedText,
  ScoreMeter,
  SourceLine,
  Stack,
  Text,
} from '@algotrade/ui';
import { useState } from 'react';

import {
  indicatorChange,
  indicatorFormat,
  indicatorStatus,
  meterDirection,
  meterThresholds,
  onWhenLine,
  provenanceLine,
  sourceItems,
  type RegimeIndicator,
} from '@/entities/regime';
import { IndicatorHistory } from '@/features/indicator-history';
import { RegimeRangeControl, useRegimeRange } from '@/features/regime-range';

import { IndicatorDetail } from './IndicatorDetail';

const isNumber = (value: unknown): value is number => typeof value === 'number';

export function IndicatorCard({
  indicator,
  session,
  explainable,
}: {
  indicator: RegimeIndicator;
  /** The regime's session: the end of the history window and of the presets. */
  session: string;
  explainable: boolean;
}) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const range = useRegimeRange(session);
  const format = indicatorFormat(indicator);
  const change = indicatorChange(indicator);
  const reason = indicator.unknown?.detail;
  const sources = sourceItems(indicator);
  const provenance = indicator.sources.flatMap((source) => provenanceLine(source) ?? []);
  const thresholds = meterThresholds(indicator);
  const onWhen = onWhenLine(indicator, format);
  return (
    <Stack gap={0}>
      <IndicatorRow
        status={indicatorStatus(indicator.status)}
        name={indicator.plainName}
        technicalName={indicator.technicalName}
        description={reason ? `${indicator.oneLiner} Unknown: ${reason}` : indicator.oneLiner}
        {...(change ? { changed: change.change, changedLabel: change.label } : {})}
      />
      <Box paddingX={3} paddingY={2}>
        <Stack gap={2}>
          <ScoreMeter
            label={indicator.technicalName}
            value={isNumber(indicator.value) ? indicator.value : null}
            min={indicator.range.min}
            max={indicator.range.max}
            direction={meterDirection(indicator)}
            thresholds={thresholds}
            {...(thresholds.length > 0 ? { baseTone: 'positive', baseLabel: 'off' } : {})}
            format={format}
            {...(onWhen === undefined ? {} : { caption: onWhen })}
            {...(reason ? { unknownReason: reason } : {})}
          />
          {indicator.how.length > 0 && (
            <LinkedText
              size="sm"
              tone="secondary"
              parts={indicator.how.map((part) => ({
                text: part.text,
                ...(part.url === null ? {} : { href: part.url }),
              }))}
            />
          )}
          <SourceLine sources={sources.linked} />
          {sources.unlinked.map((line) => (
            <Text key={line} size="sm" tone="muted">
              {line}
            </Text>
          ))}
          {provenance.map((line) => (
            <Text key={line} size="sm" tone="muted">
              {line}
            </Text>
          ))}
          <Disclosure label="Show history" open={historyOpen} onOpenChange={setHistoryOpen}>
            {historyOpen && (
              <IndicatorHistory
                indicator={indicator}
                window={range.window}
                toolbar={<RegimeRangeControl session={session} />}
              />
            )}
          </Disclosure>
          <Disclosure label="Why it matters, what it did before, and where to read more">
            <IndicatorDetail indicator={indicator} explainable={explainable} />
          </Disclosure>
        </Stack>
      </Box>
    </Stack>
  );
}
