/**
 * A regime indicator's help: its summary, why it matters, when it is on, its lead time and its
 * track record (the false alarms), the plain name over the technical one. The text is the card's
 * (`config/site/regime/cards.toml`) as the server links it; nothing is written here.
 */
import { HelpLead, HelpSection, Text } from '@algotrade/ui';

import { GuideProse, useGuideIndicator } from '@/entities/guide';

import { HelpShell } from './HelpShell';

export function IndicatorHelp({ indicatorKey }: { indicatorKey: string }) {
  const query = useGuideIndicator(indicatorKey);
  const indicator = query.data;
  const summary = indicator?.summary.segments.map((s) => s.text).join('');
  return (
    <HelpShell
      entry={{ kind: 'indicator', id: indicatorKey }}
      label={`What is ${indicator?.plainName ?? 'this warning sign'}?`}
      title={indicator?.plainName ?? 'Warning sign'}
      eyebrow={indicator?.technicalName ?? 'Regime indicator'}
      {...(indicator ? { meta: indicator.pace === 'slow' ? 'Slow-moving' : 'Fast-moving' } : {})}
      summary={summary}
      state={
        query.isPending ? 'pending' : query.isError ? 'error' : !indicator ? 'missing' : 'ready'
      }
      missingText="The Guide has no entry for this warning sign yet."
      onRetry={() => {
        void query.refetch();
      }}
      retrying={query.isFetching}
    >
      {indicator && (
        <>
          <HelpLead>
            <GuideProse prose={indicator.summary} />
          </HelpLead>
          <HelpSection title="Why it matters">
            <Text as="p">
              <GuideProse prose={indicator.whyItMatters} />
            </Text>
          </HelpSection>
          <HelpSection title="When it is on">
            <Text as="p">
              <GuideProse prose={indicator.whatOnMeans} />
            </Text>
          </HelpSection>
          <HelpSection title="Lead time and track record">
            <Text as="p">
              <GuideProse prose={indicator.leadTime} />
            </Text>
            <Text as="p">
              <GuideProse prose={indicator.trackRecord} />
            </Text>
          </HelpSection>
        </>
      )}
    </HelpShell>
  );
}
