/**
 * The help button for a Guide entry and the drawer it opens (ADR 0051, docs/ui/guide.md
 * "The help drawer"): an `InfoButton` whose hover is the entry's first sentence and whose click
 * opens the entry: the catalogue name, the title, the theme and unit, how to read it, what to use
 * it for (each intent with its rule), how many caveats the full page lists, and "Open full page".
 * The text is the server's; nothing is written here.
 */
import {
  Button,
  ErrorState,
  HelpDrawer,
  HelpLead,
  HelpSection,
  InfoButton,
  Mono,
  Skeleton,
  Stack,
  Surface,
  Text,
} from '@algotrade/ui';
import { useState } from 'react';

import { featureTitle, ruleText, unitLabel } from '@/entities/feature';

import { useGuideHelp } from '../api/hooks';
import { guidePath, type GuideEntry } from '../model/entry';
import { useGuideNavigate } from '../model/navigation';

export interface GuideHelpProps {
  /** The Guide entry the button explains. */
  entry: GuideEntry;
}

/** "3 caveats" / "1 caveat", for the line that points to the full page. */
const caveatCount = (n: number) => `${String(n)} ${n === 1 ? 'caveat' : 'caveats'}`;

export function GuideHelp({ entry }: GuideHelpProps) {
  const [open, setOpen] = useState(false);
  const navigate = useGuideNavigate();
  const help = useGuideHelp(entry.id);
  const title = featureTitle(entry.id);
  const guide = help.data?.guide ?? null;
  const unit = unitLabel(help.data?.unit ?? null);
  const meta = [guide?.theme, unit].filter(Boolean).join(' · ');
  return (
    <>
      <InfoButton
        label={`What is ${title}?`}
        {...(guide ? { summary: guide.summary } : {})}
        expanded={open}
        onClick={() => {
          setOpen(true);
        }}
      />
      <HelpDrawer
        open={open}
        onOpenChange={setOpen}
        eyebrow={<Mono>{entry.id}</Mono>}
        title={title}
        {...(meta ? { meta } : {})}
        fullPage={
          <Button
            variant="ghost"
            size="sm"
            iconEnd="chevron-right"
            onClick={() => {
              setOpen(false);
              navigate(guidePath(entry));
            }}
          >
            Open full page
          </Button>
        }
      >
        {help.isPending ? (
          <Skeleton label={`Loading ${title}`} />
        ) : help.isError ? (
          <ErrorState
            title={`${title} could not be loaded.`}
            onRetry={() => {
              void help.refetch();
            }}
            retrying={help.isFetching}
            compact
          />
        ) : !guide ? (
          <Text tone="muted">The Guide has no entry for this field yet.</Text>
        ) : (
          <>
            <HelpLead>{guide.reads}</HelpLead>
            {guide.uses.length > 0 ? (
              <HelpSection title="Use it for">
                <Stack gap={2}>
                  {guide.uses.map((use) => (
                    <Surface key={use.intent} tone="row" border="all" radius="lg" padding={3}>
                      <Stack gap={1}>
                        <Text weight="medium">{use.intent}</Text>
                        <Text size="sm" mono>
                          {ruleText(use)}
                        </Text>
                      </Stack>
                    </Surface>
                  ))}
                </Stack>
              </HelpSection>
            ) : null}
            {guide.caveats.length > 0 ? (
              <Text size="sm" tone="muted">
                {caveatCount(guide.caveats.length)} on the full page.
              </Text>
            ) : null}
          </>
        )}
      </HelpDrawer>
    </>
  );
}
