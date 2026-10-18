/**
 * The criteria as the Builder lays them out (ADR 0071): a loose criterion is one row with its
 * grouping actions ("Either this or the previous", "Exclude (none of)"); a gate of one level is a
 * `ConditionGroup` of editable rows ("Exclude", "Ungroup" in its header); a deeper tree (from
 * Describe it or TOML) is one read-only group with its plain-English expression, members
 * expandable, and "Ungroup" when it is the draft's own. Every member keeps its mode control.
 */
import { Button, ConditionGroup, Divider, Stack, StatusBadge, Text } from '@algotrade/ui';

import { byName, useFeatureCatalogue, type CatalogueFeature } from '@/entities/feature';
import {
  CONNECTOR_LABEL,
  describeCriterion,
  KIND_LABEL,
  KIND_TERM,
  type Criterion,
  type CriterionGroup,
  type LayoutNode,
} from '@/entities/screen';
import { CriterionRow, useScreenerBuilder } from '@/features/screener-builder';
import { GuideHelp, termHelp } from '@/features/guide-help';

import { NEVER_REJECTS, neverRejects } from '../model/group-labels';
import { groupExpression } from '../model/plain-english';

type Node = LayoutNode<Criterion>;

export function CriteriaRows({ nodes }: { nodes: readonly Node[] }) {
  const builder = useScreenerBuilder();
  const catalogue = useFeatureCatalogue();
  const features: readonly CatalogueFeature[] = catalogue.data ?? [];
  const byFeature = byName(features);

  const row = (criterion: Criterion, loose: boolean) => (
    <CriterionRow
      criterion={criterion}
      catalogue={features}
      catalogueLoading={catalogue.isPending}
      onChange={builder.setCriterion}
      onRemove={() => {
        builder.removeCriterion(criterion.id);
      }}
      renderFieldHelp={(field, onUse) => (
        <GuideHelp entry={{ kind: 'field', id: field }} onUse={onUse} />
      )}
      error={builder.errorCriterion === criterion.id ? builder.preview.error : null}
      actions={
        loose ? (
          <>
            {builder.canJoinPrevious(criterion.id) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  builder.joinWithPrevious(criterion.id);
                }}
              >
                Either this or the previous
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                builder.excludeCriterion(criterion.id);
              }}
            >
              Exclude (none of)
            </Button>
          </>
        ) : null
      }
    />
  );

  const expression = (group: CriterionGroup) =>
    groupExpression(group, builder.criteria, features, builder.groups);

  const readOnly = (node: Extract<Node, { type: 'group' }>, nested: boolean) => {
    const { group } = node;
    const label = neverRejects(group, builder.criteria) ? (
      <StatusBadge tone="neutral">{NEVER_REJECTS}</StatusBadge>
    ) : null;
    return (
      <Stack gap={2} key={group.id}>
        <ConditionGroup
          kind={group.kind}
          kindLabel={KIND_LABEL[group.kind]}
          title={group.id}
          connectorLabel={CONNECTOR_LABEL[group.kind]}
          joinedByLabel="joined by"
          // The read-only row is one button and shows no header actions: the Guide help is
          // drawn beside it, below.
          actions={termHelp(KIND_TERM[group.kind])}
          expression={
            <>
              {expression(group)} {label}
            </>
          }
          readOnly
        >
          {node.members.map((member) =>
            member.type === 'group' ? (
              readOnly(member, true)
            ) : (
              <Stack direction="row" gap={2} align="center" wrap key={member.criterion.id}>
                <Text size="sm">
                  {describeCriterion(member.criterion, byFeature.get(member.criterion.field))}
                </Text>
                <Text size="xs" tone="muted">
                  {member.criterion.mode}
                </Text>
              </Stack>
            ),
          )}
        </ConditionGroup>
        <Stack direction="row" gap={2} align="center">
          {termHelp(KIND_TERM[group.kind])}
          {!nested && node.owned && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                builder.ungroup(group.id);
              }}
            >
              Ungroup
            </Button>
          )}
        </Stack>
      </Stack>
    );
  };

  return (
    <>
      {nodes.map((node, index) => (
        <Stack gap={3} key={node.type === 'group' ? node.group.id : node.criterion.id}>
          {index > 0 && <Divider tone="soft" />}
          {node.type === 'criterion' ? (
            row(node.criterion, true)
          ) : node.editable ? (
            <ConditionGroup
              kind={node.group.kind}
              kindLabel={KIND_LABEL[node.group.kind]}
              title={expression(node.group)}
              connectorLabel={CONNECTOR_LABEL[node.group.kind]}
              joinedByLabel="joined by"
              actions={
                <>
                  {termHelp(KIND_TERM[node.group.kind])}
                  {neverRejects(node.group, builder.criteria) && (
                    <StatusBadge tone="neutral">{NEVER_REJECTS}</StatusBadge>
                  )}
                  {node.group.kind === 'any' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        builder.excludeGroup(node.group);
                      }}
                    >
                      Exclude (none of)
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      builder.ungroup(node.group.id);
                    }}
                  >
                    Ungroup
                  </Button>
                </>
              }
            >
              {node.members.flatMap((member) =>
                member.type === 'criterion' ? [row(member.criterion, false)] : [],
              )}
            </ConditionGroup>
          ) : (
            readOnly(node, false)
          )}
        </Stack>
      ))}
    </>
  );
}
