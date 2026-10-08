/**
 * "Add formula feature": the user names a formula over catalogue features, sees it type
 * checked as they type (its type, what it reads, a few sample values on the latest session) and
 * saves it as one of their own features, selectable as `feature.<name>`.
 */
import { Banner, Button, Dialog, Field, Input, KeyValue, Select, Stack, Text } from '@algotrade/ui';
import { useState } from 'react';

import { fromRest, UnavailableNote } from '@/entities/availability';
import { errorDetail } from '@/shared/api';

import { useDebounced } from '@/shared/lib';

import { useFormulaCheck, useSaveFormulaFeature } from '../api/hooks';
import { guessUnit, isFeatureName, UNITS } from '../model/formula';

const CHECK_DEBOUNCE_MS = 300;

export interface FormulaFeatureDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The feature was saved: its field (`feature.<name>`). */
  onSaved: (field: string) => void;
}

export function FormulaFeatureDialog({ open, onOpenChange, onSaved }: FormulaFeatureDialogProps) {
  const [name, setName] = useState('');
  const [expr, setExpr] = useState('');
  const [unit, setUnit] = useState<string | null>(null);
  const [description, setDescription] = useState('');
  const [nullMeaning, setNullMeaning] = useState('');
  const check = useFormulaCheck(useDebounced(expr, CHECK_DEBOUNCE_MS));
  const save = useSaveFormulaFeature();
  const checked = check.data;
  const nameError =
    name !== '' && !isFeatureName(name)
      ? 'Use lowercase letters, digits and _, starting with a letter.'
      : undefined;
  const ready =
    Boolean(checked) &&
    isFeatureName(name) &&
    description.trim() !== '' &&
    nullMeaning.trim() !== '' &&
    expr.trim() === (checked?.expr ?? '');

  const submit = () => {
    if (!checked) return;
    save.mutate(
      {
        name,
        expr: expr.trim(),
        dtype: checked.dtype,
        unit: unit ?? guessUnit(checked.dtype),
        description: description.trim(),
        null_meaning: nullMeaning.trim(),
      },
      {
        onSuccess: (saved) => {
          onSaved(saved.field);
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add formula feature"
      description="A formula over catalogue features, saved as your own feature."
      size="lg"
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button variant="primary" disabled={!ready} loading={save.isPending} onClick={submit}>
            Save feature
          </Button>
        </>
      }
    >
      <Stack gap={3}>
        <Field
          label="Name"
          hint="Selected as feature.<name>"
          {...(nameError ? { error: nameError } : {})}
        >
          <Input value={name} onValueChange={setName} mono autoComplete="off" spellCheck={false} />
        </Field>
        <Field label="Formula" hint="e.g. rollup.iv30@v1.iv30 - rollup.price_stats@v2.hv30">
          <Input value={expr} onValueChange={setExpr} mono autoComplete="off" spellCheck={false} />
        </Field>
        {expr.trim() !== '' && check.isError && (
          <Banner tone="negative" title="This formula does not check">
            {errorDetail(check.error)}
          </Banner>
        )}
        {checked && (
          <KeyValue
            label="Formula check"
            items={[
              { label: 'Type', value: `${checked.type} (${checked.dtype})` },
              { label: 'Reads', value: checked.inputs.join(', ') || 'nothing' },
              { label: 'Licence', value: checked.licence },
              {
                label: checked.session ? `On ${checked.session}` : 'Sample',
                value: checked.session
                  ? `${checked.non_null.toLocaleString('en-US')} of ${checked.rows.toLocaleString('en-US')} have a value`
                  : 'nothing stored to sample',
              },
              ...(checked.sample.length > 0
                ? [
                    {
                      label: 'Examples',
                      value: checked.sample.map((s) => String(s.value ?? 'empty')).join(' · '),
                    },
                  ]
                : []),
            ]}
          />
        )}
        {checked && <UnavailableNote gaps={fromRest(checked.unavailable)} />}
        <Field label="Unit">
          <Select
            options={UNITS.map((u) => ({ value: u, label: u.replace(/_/g, ' ') }))}
            value={unit ?? guessUnit(checked?.dtype ?? 'float')}
            onValueChange={setUnit}
          />
        </Field>
        <Field label="What it is" hint="One line: what the number means">
          <Input value={description} onValueChange={setDescription} />
        </Field>
        <Field
          label="When it is empty"
          hint="Why a value can be missing; a missing value never passes a rule"
        >
          <Input value={nullMeaning} onValueChange={setNullMeaning} />
        </Field>
        {save.isError && (
          <Text tone="negative" size="sm" as="p">
            {errorDetail(save.error)}
          </Text>
        )}
      </Stack>
    </Dialog>
  );
}
