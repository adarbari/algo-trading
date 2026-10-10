/**
 * The Builder's header: the screener's name, its state (DRAFT vN, unsaved changes), the preset it
 * is a copy of ("Your copy of vrp_scanner v1"), and Delete (the user's own screen, after a
 * confirmation) / Discard (the unsaved edits and the saved draft) / Save draft / Finalize (a
 * finalised screen runs nightly, ADR 0033). A newer preset version shows the rebase banner. A
 * site preset (or a copy of one) carries a link to its playbook in the Guide. A site
 * preset not yet copied is shown as it is (its live preview runs); the first edit makes the
 * user's copy, so there is no separate read-only mode. Opened from an edge's builder it also
 * offers "Save and return to edge".
 */
import { Banner, Button, Heading, Mono, Stack, StatusBadge, Text, TextLink } from '@algotrade/ui';

import { playbookPath } from '@/entities/guide';
import { useScreenerBuilder } from '@/features/screener-builder';
import { DeleteScreenerButton } from '@/features/screener-delete';
import { FinaliseButton, RebaseBanner } from '@/features/screener-finalise';

import { draftState } from '../model/state';

export interface DraftBarProps {
  /** Without the page heading (inside a drawer): the state and the actions only. */
  compact?: boolean;
  /** The screener was deleted: leave its pages. Without it there is no Delete. */
  onDeleted?: () => void;
  /** Opened from an edge: "Save and return to edge" saves the draft and goes back. */
  onReturn?: () => void;
}

export function DraftBar({ compact = false, onDeleted, onReturn }: DraftBarProps) {
  const builder = useScreenerBuilder();
  const { detail } = builder;
  const state = draftState(builder);
  const pin = detail?.preset ?? null;
  const untouched = builder.preset !== null && !builder.dirty;
  // The user's own screen (a version or a saved draft); an uncopied preset changes only by PR.
  const own = detail !== undefined && (detail.versions.length > 0 || detail.draft !== null);
  // The preset this screen is a copy of: its pin, or (the first edit, the copy in flight) the preset.
  const copyOf = builder.preset
    ? { id: builder.preset.id, version: builder.preset.version }
    : pin
      ? { id: pin.presetId, version: pin.pinned }
      : null;
  const version = (v: number | null) => (v === null ? '' : ` v${String(v)}`);

  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          {!compact && <Text size="sm" tone="muted">{`Screeners / ${builder.id}`}</Text>}
          <Stack direction="row" gap={2} align="baseline" wrap>
            {!compact && (
              <Heading level={1}>
                <Mono size="xl">{builder.id}</Mono>
              </Heading>
            )}
            <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
            {copyOf && !untouched && (
              <Text size="sm" tone="muted">
                {`Your copy of ${copyOf.id}${version(copyOf.version)}`}
              </Text>
            )}
            {copyOf && (
              <TextLink href={playbookPath(copyOf.id)} icon="book" size="sm">
                Playbook
              </TextLink>
            )}
          </Stack>
        </Stack>
        <Stack direction="row" gap={2} align="center" wrap>
          {onDeleted && own && (
            <DeleteScreenerButton screenerId={builder.id} onDeleted={onDeleted} />
          )}
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
          {onReturn && (
            <Button
              variant="primary"
              loading={builder.saving}
              onClick={() => {
                void (builder.dirty ? builder.save() : Promise.resolve())
                  .then(onReturn)
                  .catch(() => undefined);
              }}
            >
              Save and return to edge
            </Button>
          )}
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
      {pin?.rebaseAvailable && pin.pinned !== null && pin.current !== null && (
        <RebaseBanner
          screenerId={builder.id}
          preset={pin.presetId}
          pinned={pin.pinned}
          current={pin.current}
          disabled={builder.dirty}
        />
      )}
      {detail?.draftError && !builder.dirty && (
        <Banner tone="warning" title="This draft would not finalize">
          {detail.draftError}
        </Banner>
      )}
    </Stack>
  );
}
