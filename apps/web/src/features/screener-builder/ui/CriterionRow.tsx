/**
 * One criterion: mode (Hard / Soft / Score), the feature, the operator, the threshold, remove.
 * Under it: what the feature is (description, unit, licence), the tolerance of a soft or score
 * criterion, the field's help button beside the picker (a slot the widget fills with the guide's
 * drawer, whose "Use this" sets the row to an intent) and the field's distribution with the
 * threshold marked (opened on demand).
 */
import {
  Box,
  Disclosure,
  IconButton,
  Mono,
  SegmentedControl,
  Select,
  Stack,
  Text,
} from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import {
  allowsTolerance,
  coerceValue,
  featureMarks,
  fieldKind,
  opFor,
  operatorsFor,
  unitLabel,
  type CatalogueFeature,
  type GuideUse,
} from '@/entities/feature';
import { MODES, type Criterion, type CriterionMode } from '@/entities/screen';

import { applyGuideUse } from '../model/guide';

import { FeaturePicker } from './FeaturePicker';
import { ThresholdDistribution } from './ThresholdDistribution';
import { ThresholdInput } from './ThresholdInput';
import { ToleranceFields } from './ToleranceFields';

const MODE_HELP: Record<CriterionMode, string> = {
  hard: 'Hard: must pass; a miss rejects the row',
  soft: 'Soft: a miss within the tolerance is a near miss (watch); beyond it rejects',
  score: 'Score: never rejects; a miss only lowers the score',
};
const MODE_OPTIONS = MODES.map((mode) => ({
  value: mode,
  label: mode.charAt(0).toUpperCase() + mode.slice(1),
  description: MODE_HELP[mode],
}));

export interface CriterionRowProps {
  criterion: Criterion;
  catalogue: readonly CatalogueFeature[];
  catalogueLoading?: boolean;
  onChange: (criterion: Criterion) => void;
  onRemove: () => void;
  /** The API's message when this criterion stops the draft running. */
  error?: string | null;
  disabled?: boolean;
  /**
   * The help for the row's field (the widget passes the Guide's drawer: features never import
   * each other); `onUse` sets this row to one of the field's guided intents.
   */
  renderFieldHelp?: (field: string, onUse: (use: GuideUse) => void) => ReactNode;
}

export function CriterionRow({
  criterion,
  catalogue,
  catalogueLoading = false,
  onChange,
  onRemove,
  error = null,
  disabled = false,
  renderFieldHelp,
}: CriterionRowProps) {
  const feature = catalogue.find((f) => f.name === criterion.field);
  const kind = fieldKind(feature);
  const [showDistribution, setShowDistribution] = useState(false);
  const tolerant = allowsTolerance(criterion.op, kind);
  const threshold = typeof criterion.value === 'number' ? criterion.value : null;

  const setField = (field: string) => {
    const next = catalogue.find((f) => f.name === field);
    const nextKind = fieldKind(next);
    const op = opFor(nextKind, criterion.op);
    const sameField = field === criterion.field;
    onChange({
      ...criterion,
      field,
      op,
      value: sameField ? criterion.value : coerceValue(op, nextKind, undefined),
      tolerance: allowsTolerance(op, nextKind) ? criterion.tolerance : undefined,
      mode: allowsTolerance(op, nextKind) || criterion.mode === 'hard' ? criterion.mode : 'hard',
    });
  };
  const setOp = (op: string) => {
    onChange({
      ...criterion,
      op,
      value: coerceValue(op, kind, criterion.value),
      ...(allowsTolerance(op, kind) ? {} : { tolerance: undefined, mode: 'hard' }),
    });
  };
  const setMode = (value: string) => {
    const mode = value as CriterionMode;
    onChange({
      ...criterion,
      mode,
      tolerance:
        mode === 'hard' ? undefined : (criterion.tolerance ?? (mode === 'soft' ? 0 : undefined)),
      on_miss: mode === 'soft' ? criterion.on_miss : undefined,
    });
  };

  return (
    <Stack gap={2} as="div">
      <Stack direction="row" gap={2} align="center" wrap>
        <SegmentedControl
          aria-label={`Mode of ${criterion.id}`}
          size="sm"
          options={MODE_OPTIONS.map((o) => ({
            ...o,
            disabled: o.value !== 'hard' && !tolerant && criterion.field !== '',
          }))}
          value={criterion.mode}
          onValueChange={setMode}
          disabled={disabled}
        />
        <Box grow>
          <FeaturePicker
            catalogue={catalogue}
            loading={catalogueLoading}
            value={criterion.field}
            onChange={setField}
            invalid={error !== null}
            disabled={disabled}
          />
        </Box>
        {feature?.guide &&
          renderFieldHelp?.(criterion.field, (use) => {
            onChange(applyGuideUse(criterion, use));
          })}
        <Select
          aria-label="Operator"
          size="sm"
          width="auto"
          options={operatorsFor(kind)}
          value={criterion.op}
          onValueChange={setOp}
          disabled={disabled}
        />
        <ThresholdInput
          feature={feature}
          op={criterion.op}
          value={criterion.value}
          onChange={(value) => {
            onChange({ ...criterion, value });
          }}
          invalid={error !== null}
          disabled={disabled}
        />
        <IconButton
          icon="close"
          label={`Remove criterion ${criterion.id}`}
          size="sm"
          onClick={onRemove}
          disabled={disabled}
        />
      </Stack>
      {feature && (
        <Stack direction="row" gap={2} align="center" wrap>
          <Mono size="xs" tone="muted">
            {criterion.id}
          </Mono>
          <Text size="xs" tone="muted">
            {[feature.description, unitLabel(feature.unit), ...featureMarks(feature)]
              .filter(Boolean)
              .join(' · ')}
          </Text>
        </Stack>
      )}
      {criterion.mode !== 'hard' && tolerant && (
        <ToleranceFields
          criterion={criterion}
          feature={feature}
          onChange={onChange}
          disabled={disabled}
        />
      )}
      {error && (
        <Text size="sm" tone="negative" as="p">
          {error}
        </Text>
      )}
      {feature && kind === 'number' && (
        <Disclosure
          label="Distribution"
          variant="plain"
          open={showDistribution}
          onOpenChange={setShowDistribution}
        >
          {showDistribution && <ThresholdDistribution feature={feature} threshold={threshold} />}
        </Disclosure>
      )}
    </Stack>
  );
}
