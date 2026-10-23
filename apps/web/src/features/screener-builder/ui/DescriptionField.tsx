/**
 * The one-line description of a screener, asked when saving it: a Field with a TextArea (one
 * line, at most 140 characters, a counter) and, under it, the list row it will be on. Required to
 * finalize, not to save a draft.
 */
import { Field, Stack, Text, TextArea } from '@algotrade/ui';

import { MAX_DESCRIPTION_LENGTH, oneLine, ScreenerDescription } from '@/entities/screen';

/** The inline error when finalizing without a description (also shown for the server's). */
export const DESCRIPTION_REQUIRED =
  'Add a one-line description so you can tell your screeners apart.';

export interface DescriptionFieldProps {
  /** The screener's name, for the preview of its list row. */
  name: string;
  value: string;
  onChange: (text: string) => void;
  /** Shown inline under the field. */
  error?: string | undefined;
}

export function DescriptionField({ name, value, onChange, error }: DescriptionFieldProps) {
  return (
    <Stack gap={2}>
      <Field
        label="Description"
        hint="Shown on the Screeners list and its page, so say what it finds and why you look for it"
        error={error}
      >
        <TextArea
          rows={2}
          value={value}
          onValueChange={(text) => {
            onChange(oneLine(text));
          }}
        />
      </Field>
      <Text
        size="xs"
        tone="muted"
      >{`${String(value.length)} / ${String(MAX_DESCRIPTION_LENGTH)}`}</Text>
      {value.trim() !== '' && (
        <Stack gap={1}>
          <Text size="xs" tone="muted">
            On the Screeners list
          </Text>
          <Text as="span" weight="medium">
            {name}
          </Text>
          <ScreenerDescription description={value} />
        </Stack>
      )}
    </Stack>
  );
}
