/**
 * The Builder's header: the screener's name, its state (DRAFT vN, unsaved changes), the preset it
 * is a copy of ("Your copy of vrp_scanner v1"), and Discard / Save draft / Finalize; the nightly
 * schedule is a separate switch beside them. A newer preset version shows the rebase banner. A
 * site preset not yet copied is shown as it is (its live preview runs); the first edit makes the
 * user's copy, so there is no separate read-only mode.
 */
import { Banner, Button, Heading, Mono, Stack, StatusBadge, Text } from '@algotrade/ui';
import { useScreenerBuilder } from '@/features/screener-builder';
import { FinaliseButton, RebaseBanner, ScheduleToggle } from '@/features/screener-finalise';

import { draftState } from '../model/state';

export function DraftBar() {
  const builder = useScreenerBuilder();
  const { detail } = builder;
  const state = draftState(builder);
  const pin = detail?.preset ?? null;
  const untouched = builder.preset !== null && !builder.dirty;
  // The preset this screen is a copy of: its pin, or (the first edit, the copy in flight) the preset.
  const copyOf = builder.preset
    ? { id: builder.preset.id, version: builder.preset.version }
    : pin
      ? { id: pin.preset_id, version: pin.pinned }
      : null;
  const version = (v: number | null) => (v === null ? '' : ` v${String(v)}`);

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
            {copyOf && !untouched && (
              <Text size="sm" tone="muted">
                {`Your copy of ${copyOf.id}${version(copyOf.version)}`}
              </Text>
            )}
          </Stack>
        </Stack>
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
      </Stack>
      {untouched && (
        <Banner tone="info" title="Site preset">
          {`This is the site preset${version(builder.preset?.version ?? null)} with its live preview. Change anything and a copy of it becomes yours (pinned to this version); the preset itself changes only by pull request.`}
        </Banner>
      )}
      {pin?.rebase_available && pin.pinned !== null && pin.current !== null && (
        <RebaseBanner
          screenerId={builder.id}
          preset={pin.preset_id}
          pinned={pin.pinned}
          current={pin.current}
          disabled={builder.dirty}
        />
      )}
      {detail?.draft_error && !builder.dirty && (
        <Banner tone="warning" title="This draft would not finalize">
          {detail.draft_error}
        </Banner>
      )}
    </Stack>
  );
}
