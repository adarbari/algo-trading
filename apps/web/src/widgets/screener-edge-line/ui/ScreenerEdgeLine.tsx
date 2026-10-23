/**
 * The edge context of a screener's page, one line under its header (ADR 0053): its headline edge
 * (the strongest by status, then by trades) with its status, win rate against the base rate, lift,
 * trades, holding period and when its frozen period began; a "+N edges" chip when more than one
 * edge lists the screener; and an Evidence control that opens each edge's record. A screener no
 * edge lists says so, and one whose edge has not run says why (the server's words). Only the
 * frozen-period record is read, never an exploratory run.
 */
import { Box, Button, Skeleton, Stack, StatusBadge, Surface, Text } from '@algotrade/ui';
import { useId, useState } from 'react';

import { statusLabel, statusTone, useScreenerEdges } from '@/entities/edge';
import { termHelp } from '@/features/guide-help';

import { EdgeRecord } from './EdgeRecord';

export interface ScreenerEdgeLineProps {
  screenerId: string;
  /** Open an edge's page. */
  onOpenEdge: (edgeId: string) => void;
}

export function ScreenerEdgeLine({ screenerId, onOpenEdge }: ScreenerEdgeLineProps) {
  const edges = useScreenerEdges(screenerId);
  const [open, setOpen] = useState(false);
  const panel = useId();
  if (edges.isPending) return <Skeleton lines={1} label="Loading the screener's edge…" />;
  if (edges.isError) {
    return (
      <Text size="sm" tone="muted">
        The edge record failed to load.
      </Text>
    );
  }
  const [headline, ...others] = edges.data;
  if (!headline) {
    return (
      <Stack direction="row" gap={1} align="center">
        <Text size="sm" tone="muted">
          Not part of an edge: no out-of-sample record covers this screener.
        </Text>
        {termHelp('screener_edge_line')}
      </Stack>
    );
  }
  return (
    <Surface padding={3}>
      <Stack gap={2}>
        <Stack direction="row" gap={2} align="start" justify="between" wrap>
          <Stack gap={1}>
            <Stack direction="row" gap={2} align="center" wrap>
              <Text size="sm" weight="medium">
                {headline.edgeName}
              </Text>
              {termHelp('screener_edge_line')}
              {headline.status ? (
                <StatusBadge tone={statusTone(headline.status)}>
                  {statusLabel(headline.status)}
                </StatusBadge>
              ) : null}
              {others.length > 0 ? (
                <StatusBadge tone="neutral">{`+${String(others.length)} ${others.length === 1 ? 'edge' : 'edges'}`}</StatusBadge>
              ) : null}
            </Stack>
          </Stack>
          <Button
            size="sm"
            variant="secondary"
            iconEnd={open ? 'chevron-up' : 'chevron-down'}
            aria-expanded={open}
            aria-controls={panel}
            onClick={() => {
              setOpen(!open);
            }}
          >
            Evidence
          </Button>
        </Stack>
        <EdgeRecord edge={headline} onOpenEdge={onOpenEdge} compact />
        {open ? (
          <Box id={panel}>
            <Stack gap={3}>
              {[headline, ...others].map((edge) => (
                <EdgeRecord key={edge.edgeId} edge={edge} onOpenEdge={onOpenEdge} />
              ))}
            </Stack>
          </Box>
        ) : null}
      </Stack>
    </Surface>
  );
}
