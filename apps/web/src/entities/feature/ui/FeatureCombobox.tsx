/**
 * The catalogue feature picker: a searchable Combobox over feature options (`fieldOptions`
 * for a field to name, `columnOptions` for a column to add), with the catalogue's loading and
 * failed states. One place for "find a feature by typing"; callers own the value and the
 * options, so each says what a pick means.
 */
import { Combobox, type ComboboxProps } from '@algotrade/ui';

export interface FeatureComboboxProps extends Omit<
  ComboboxProps,
  'value' | 'onValueChange' | 'loading' | 'error' | 'emptyMessage'
> {
  /** The chosen feature name (null: none). */
  value?: string | null;
  /** Called with the feature name picked (never with an empty pick). */
  onPick: (name: string) => void;
  loading?: boolean;
  /** The catalogue failed to load. */
  failed?: boolean;
}

export function FeatureCombobox({
  value = null,
  onPick,
  loading = false,
  failed = false,
  ...rest
}: FeatureComboboxProps) {
  return (
    <Combobox
      {...rest}
      value={value || null}
      loading={loading}
      {...(failed ? { error: 'The feature catalogue failed to load.' } : {})}
      emptyMessage="No feature matches"
      onValueChange={(next) => {
        if (next) onPick(next);
      }}
    />
  );
}
