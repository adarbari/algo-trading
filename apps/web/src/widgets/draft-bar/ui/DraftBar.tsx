/**
 * The Builder's header: the screener's name, its state (DRAFT vN, unsaved changes), the preset it
 * is based on, and Discard / Save draft / Finalize; the nightly schedule is a separate switch
 * beside them. A newer preset version shows the rebase banner; a site preset not yet copied is
 * shown read-only with "Copy to my screeners".
 */
import { Banner, Button, Heading, Mono, Stack, StatusBadge, Text } from '@algotrade/ui';
import { useState } from 'react';

import { CopyPresetDialog } from '@/features/screener-copy';
import { useScreenerBuilder } from '@/features/screener-builder';
import { FinaliseButton, RebaseBanner, ScheduleToggle } from '@/features/screener-finalise';

import { draftState } from '../model/state';

export interface DraftBarProps {
  /** Open another screener's Builder (after copying a preset). */
  onOpen: (id: string) => void;
}

export function DraftBar({ onOpen }: DraftBarProps) {
  const builder = useScreenerBuilder();
  const [copying, setCopying] = useState(false);
  const { detail } = builder;
  const state = draftState(builder);
  const preset = detail?.preset ?? null;

  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          <Text size="sm" tone="muted">{`Screeners / ${builder.id}`}</Text>
          <Stack direction="row" gap={2} align="baseline" wrap>
            <Heading level={1}>
              <Mono size="xl">{builder.id}</Mono>
            </Heading>
            <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
            {preset && (
              <Text size="sm" tone="muted">
                {`based on preset ${preset.preset_id}${preset.pinned === null ? '' : ` v${String(preset.pinned)}`}`}
              </Text>
            )}
          </Stack>
        </Stack>
        {builder.readOnly ? (
          <Button
            variant="primary"
            onClick={() => {
              setCopying(true);
            }}
          >
            Copy to my screeners
          </Button>
        ) : (
          <Stack direction="row" gap={2} align="center" wrap>
            <ScheduleToggle
              screenerId={builder.id}
              schedule={detail?.schedule ?? null}
              finalised={(detail?.versions.length ?? 0) > 0}
            />
            <Button
              disabled={!builder.dirty && !detail?.draft}
              loading={builder.discarding}
              onClick={() => {
                void builder.discard();
              }}
            >
              Discard
            </Button>
            <Button
              disabled={!builder.dirty}
              loading={builder.saving}
              onClick={() => {
                void builder.save().catch(() => undefined);
              }}
            >
              Save draft
            </Button>
            <FinaliseButton
              screenerId={builder.id}
              version={builder.nextVersion}
              prepare={builder.save}
              disabled={builder.criteria.length === 0 || (!builder.dirty && !detail?.draft)}
            />
          </Stack>
        )}
      </Stack>
      {builder.readOnly && (
        <Banner tone="info" title="Site preset">
          Presets are changed by pull request. Copy it to your screeners to edit a pinned copy; the
          preview needs a copy too.
        </Banner>
      )}
      {preset?.rebase_available && preset.pinned !== null && preset.current !== null && (
        <RebaseBanner
          screenerId={builder.id}
          preset={preset.preset_id}
          pinned={preset.pinned}
          current={preset.current}
          disabled={builder.dirty}
        />
      )}
      {detail?.draft_error && !builder.dirty && (
        <Banner tone="warning" title="This draft would not finalize">
          {detail.draft_error}
        </Banner>
      )}
      <CopyPresetDialog
        preset={builder.id}
        open={copying}
        onOpenChange={setCopying}
        onCopied={onOpen}
      />
    </Stack>
  );
}
