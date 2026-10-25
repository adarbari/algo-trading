/**
 * The known-value panel's columns: one security type, or one cause of a gap, per row (not
 * instruments x features). Every header has its Guide button. The shares and counts are the
 * server's; nothing is derived here.
 */
import type { DataTableColumn } from '@algotrade/ui';

import type { HelpedColumn } from '@/entities/feature';
import type { KnownByType, KnownGapCount } from '@/entities/ingestion';
import { helped } from '@/features/guide-help';

const GAP_LABELS: Record<string, string> = {
  BLANK_CHECK: 'Blank-check company',
  NO_CIK: 'No CIK',
  NO_FACTS: 'No share count filed',
  NO_ROW: 'No row stored',
};

const BY_TYPE: HelpedColumn<KnownByType>[] = [
  {
    id: 'type',
    header: 'Security type',
    value: (r) => r.securityType,
    mono: true,
    grow: true,
    help: { kind: 'term', id: 'known_security_type' },
  },
  {
    id: 'names',
    header: 'Names',
    value: (r) => r.names,
    format: { kind: 'number' },
    width: 'sm',
    help: { kind: 'term', id: 'known_names' },
  },
  {
    id: 'rows',
    header: 'Rows stored',
    value: (r) => r.rows,
    format: { kind: 'number' },
    width: 'sm',
    help: { kind: 'term', id: 'known_rows' },
  },
  {
    id: 'known',
    header: 'Known',
    value: (r) => r.known,
    format: { kind: 'number' },
    width: 'sm',
    help: { kind: 'term', id: 'known_values' },
  },
  {
    id: 'share',
    header: 'Known share',
    value: (r) => r.share,
    format: { kind: 'percent', digits: 1 },
    width: 'sm',
    help: { kind: 'term', id: 'known_share' },
  },
];

const GAPS: HelpedColumn<KnownGapCount>[] = [
  {
    id: 'gap',
    header: 'Why no value',
    value: (r) => GAP_LABELS[r.gap] ?? r.gap,
    grow: true,
    help: { kind: 'term', id: 'known_gap' },
  },
  {
    id: 'names',
    header: 'Operating companies',
    value: (r) => r.names,
    format: { kind: 'number' },
    width: 'md',
    help: { kind: 'term', id: 'known_gap_names' },
  },
];

export const typeColumns = (): DataTableColumn<KnownByType>[] => BY_TYPE.map((c) => helped(c));

export const gapColumns = (): DataTableColumn<KnownGapCount>[] => GAPS.map((c) => helped(c));
