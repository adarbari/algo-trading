/**
 * One gate of a pick that is a group (ADR 0071): a read-only ConditionGroup with its outcome, the
 * member that decided it and the Guide help for its kind. Lazy: only a screen with groups loads it.
 */
import { ConditionGroup, StatusBadge } from '@algotrade/ui';

import {
  CONNECTOR_LABEL,
  DECIDED_BY_LABEL,
  KIND_LABEL,
  KIND_TERM,
  outcomeLabel,
  outcomeTone,
  type GroupKind,
  type ScorecardGate,
} from '@/entities/screen';
import { termHelp } from '@/features/guide-help';

export default function GateRow({ gate }: { gate: ScorecardGate }) {
  const { group, names, decidedBy, members } = gate;
  const kind = group.kind as GroupKind;
  return (
    <ConditionGroup
      kind={kind}
      kindLabel={KIND_LABEL[kind]}
      title={names.join(` ${CONNECTOR_LABEL[kind]} `)}
      connectorLabel={CONNECTOR_LABEL[kind]}
      joinedByLabel="joined by"
      info={termHelp(KIND_TERM[kind])}
      expression={
        <>
          {group.outcome ? (
            <StatusBadge tone={outcomeTone(group.outcome)}>
              {outcomeLabel(group.outcome)}
            </StatusBadge>
          ) : null}
          {decidedBy ? ` ${DECIDED_BY_LABEL} ${decidedBy}` : ''}
        </>
      }
      readOnly
    >
      {members}
    </ConditionGroup>
  );
}
