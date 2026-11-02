/**
 * The selected grid cell: its figures, each named and explained by its Guide term (the name
 * and the help text come from the Guide; nothing is written here).
 */
import { KeyValue, Text } from '@algotrade/ui';

import { useGuideTerm } from '@/entities/guide';
import { detailFigures, type GridFigures } from '@/entities/option-grid';
import { termHelp } from '@/features/guide-help';

function TermName({ id }: { id: string }) {
  const term = useGuideTerm(id).data?.entry.term;
  return <Text size="sm">{term ?? '…'}</Text>;
}

export function CellDetail({ figures }: { figures: GridFigures }) {
  return (
    <KeyValue
      label="Selected cell"
      alignValues="end"
      items={detailFigures(figures).map(({ term, value }) => ({
        id: term,
        label: <TermName id={term} />,
        action: termHelp(term),
        value,
        mono: true,
      }))}
    />
  );
}
