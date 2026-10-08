/**
 * A Start here page's help: its summary and its first section, so a button beside a screen can
 * show the opening of the how-to and "Open full page" the rest. The text is the page's
 * (`config/site/guide/start.toml`) as the server links it; nothing is written here.
 */
import { HelpLead, HelpSection, Text } from '@algotrade/ui';

import { GuideProse, useGuideStartPage } from '@/entities/guide';

import { HelpShell } from './HelpShell';

export function StartHelp({ id }: { id: string }) {
  const query = useGuideStartPage(id);
  const page = query.data;
  const first = page?.sections[0];
  return (
    <HelpShell
      entry={{ kind: 'start', id }}
      label={`How to: ${page?.entry.title ?? 'this guide'}`}
      title={page?.entry.title ?? 'Start here'}
      eyebrow="Start here"
      {...(page ? { meta: `Step ${String(page.entry.order)}` } : {})}
      summary={page?.entry.summary}
      state={query.isPending ? 'pending' : query.isError ? 'error' : !page ? 'missing' : 'ready'}
      missingText="The Guide has no such page yet."
      onRetry={() => {
        void query.refetch();
      }}
      retrying={query.isFetching}
    >
      {page && (
        <>
          <HelpLead>{page.entry.summary}</HelpLead>
          {first && (
            <HelpSection title={first.title}>
              <Text as="p">
                <GuideProse prose={first.body} />
              </Text>
            </HelpSection>
          )}
        </>
      )}
    </HelpShell>
  );
}
