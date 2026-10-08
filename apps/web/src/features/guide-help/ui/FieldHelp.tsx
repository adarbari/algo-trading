/**
 * A catalogue field's help: the catalogue name, the title, the theme and unit, how to read it,
 * what to use it for (each intent with its rule, and "Use this" when the page passes `onUse`) and
 * how many caveats the full page lists. The text is the server's; nothing is written here.
 */
import { Button, HelpLead, HelpSection, Mono, Stack, Surface, Text } from '@algotrade/ui';

import { featureTitle, ruleText, unitLabel, type GuideUse } from '@/entities/feature';

import { useGuideHelp } from '../api/hooks';
import { HelpShell } from './HelpShell';

export interface FieldHelpProps {
  /** The catalogue name. */
  name: string;
  /** Set the thing being edited to one of the field's intents (a criterion row in the Builder). */
  onUse?: ((use: GuideUse) => void) | undefined;
  /** The "Use this" buttons are inert (a read-only form). */
  useDisabled?: boolean;
}

/** "3 caveats" / "1 caveat", for the line that points to the full page. */
const caveatCount = (n: number) => `${String(n)} ${n === 1 ? 'caveat' : 'caveats'}`;

export function FieldHelp({ name, onUse, useDisabled = false }: FieldHelpProps) {
  const help = useGuideHelp(name);
  const title = featureTitle(name);
  const guide = help.data?.guide ?? null;
  const unit = unitLabel(help.data?.unit ?? null);
  const meta = [guide?.theme, unit].filter(Boolean).join(' · ');
  return (
    <HelpShell
      entry={{ kind: 'field', id: name }}
      label={`What is ${title}?`}
      title={title}
      eyebrow={<Mono>{name}</Mono>}
      {...(meta ? { meta } : {})}
      summary={guide?.summary}
      state={help.isPending ? 'pending' : help.isError ? 'error' : !guide ? 'missing' : 'ready'}
      missingText="The Guide has no entry for this field yet."
      onRetry={() => {
        void help.refetch();
      }}
      retrying={help.isFetching}
    >
      {(close) =>
        guide && (
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
                        {onUse ? (
                          <Stack direction="row" gap={2}>
                            <Button
                              size="sm"
                              variant="ghost"
                              aria-label={`Use this: ${use.intent}`}
                              disabled={useDisabled}
                              onClick={() => {
                                close();
                                onUse(use);
                              }}
                            >
                              Use this
                            </Button>
                          </Stack>
                        ) : null}
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
        )
      }
    </HelpShell>
  );
}
