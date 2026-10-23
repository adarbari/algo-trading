/**
 * The pill's detail: the session and when it became known, one row per dataset with its status
 * and the server's share of names, how many of the viewer's screeners the data touches, and the
 * Guide. An admin also reads the cause chain the server sent for a dataset and gets a link to
 * the ingestion page; a trader's response carries none. Lazy: loaded when the pill opens.
 */
import { formatValue, Stack, StatusBadge, Text, TextLink } from '@algotrade/ui';

import { GapCauses } from '@/entities/availability';
import {
  DATASET_LABEL,
  DATASET_STATE_LABEL,
  DATASET_STATE_TONE,
  type DataStatusView,
} from '@/entities/system-status';
import { GuideHelp, guidePath } from '@/features/guide-help';

export interface DataStatusPanelProps {
  data: DataStatusView;
  admin: boolean;
}

const date = (iso: string) => formatValue(iso, { kind: 'date', style: 'short' }).text;
/** The server's UTC instant as "2026-10-22 21:05 UTC" (a text slice: no clock or zone maths). */
const instant = (iso: string) => `${iso.slice(0, 16).replace('T', ' ')} UTC`;
const percent = (share: number) => formatValue(share, { kind: 'percent', digits: 0 }).text;

export function DataStatusPanel({ data, admin }: DataStatusPanelProps) {
  const known = data.knowledgeTs === null ? 'not complete yet' : instant(data.knowledgeTs);
  return (
    <Stack gap={2}>
      <Stack direction="row" gap={1} align="center">
        <Text weight="medium">
          Session {date(data.date)} · known from {known}
        </Text>
        <GuideHelp entry={{ kind: 'term', id: 'data_state' }} />
      </Stack>
      <Stack gap={1} aria-label="Datasets">
        {data.datasets.map((dataset) => (
          <Stack key={dataset.name} gap={1}>
            <Stack direction="row" gap={2} align="center" justify="between">
              <Stack direction="row" gap={1} align="center">
                <Text>{DATASET_LABEL[dataset.name]}</Text>
                <GuideHelp entry={{ kind: 'term', id: 'dataset_status' }} />
              </Stack>
              <Stack direction="row" gap={2} align="center">
                {dataset.share !== null && (
                  <Text tone="secondary" numeric>
                    {percent(dataset.share)} of names
                  </Text>
                )}
                <StatusBadge tone={DATASET_STATE_TONE[dataset.status]}>
                  {DATASET_STATE_LABEL[dataset.status]}
                </StatusBadge>
              </Stack>
            </Stack>
            <GapCauses gaps={dataset.gaps} />
          </Stack>
        ))}
      </Stack>
      <Text tone="secondary">
        Affects {data.affectedScreeners} of your {data.totalScreeners} screeners
      </Text>
      <Stack direction="row" gap={3} align="center" wrap>
        <TextLink href={guidePath({ kind: 'term', id: 'data_state' })} icon="book" size="sm">
          Guide
        </TextLink>
        {admin && (
          <TextLink href="/admin/ingestion" size="sm">
            Ingestion
          </TextLink>
        )}
      </Stack>
    </Stack>
  );
}

export default DataStatusPanel;
