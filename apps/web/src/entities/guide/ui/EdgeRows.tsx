/**
 * The Guide's lists of edges and ideas (ADR 0051): an edge as a row (its name linking to its
 * Guide page, its status, asset, holding and side, the thesis), an idea researched but not built
 * as a row (its title, its published verdict, what building it would take, why it is not built).
 * A list of rows, not a table: the sentences wrap, which a one-line table cell would cut. The
 * words are the server's; the meaning of a status or verdict is a glossary term the section's
 * heading carries.
 */
import { Chip, Stack, StatusBadge, Text, TextLink } from '@algotrade/ui';

import {
  edgeSideText,
  edgeStatusText,
  edgeStatusTone,
  ideaVerdictTone,
} from '../model/edge-status';
import { edgeGuidePath, mechanismPath } from '../model/paths';
import { GuideProse, type GuideProseValue } from './GuideProse';

export interface EdgeRowValue {
  id: string;
  name: string;
  thesis: string;
  mechanism: string | null;
  assetText: string;
  side: string;
  holdingText: string;
  status: string;
}

export interface EdgeRowsProps {
  edges: readonly EdgeRowValue[];
  /** Mechanism titles by id: with it, each row names its mechanism (a link). */
  mechanisms?: ReadonlyMap<string, string>;
  /** The reason on file per edge id (the edges set aside). */
  why?: ReadonlyMap<string, GuideProseValue>;
  'aria-label': string;
}

export function EdgeRows({ edges, mechanisms, why, 'aria-label': ariaLabel }: EdgeRowsProps) {
  return (
    <Stack as="ul" gap={3} aria-label={ariaLabel}>
      {edges.map((edge) => {
        const mechanism = edge.mechanism === null ? undefined : mechanisms?.get(edge.mechanism);
        const reason = why?.get(edge.id);
        return (
          <Stack as="li" key={edge.id} gap={1}>
            <Stack direction="row" gap={2} align="center" wrap>
              <TextLink href={edgeGuidePath(edge.id)}>{edge.name}</TextLink>
              <StatusBadge tone={edgeStatusTone(edge.status)}>
                {edgeStatusText(edge.status)}
              </StatusBadge>
              <Chip label={edge.assetText} />
              <Chip label={edge.holdingText} />
              <Chip label={edgeSideText(edge.side)} />
              {edge.mechanism !== null && mechanism !== undefined && (
                <TextLink href={mechanismPath(edge.mechanism)} size="sm" tone="secondary">
                  {mechanism}
                </TextLink>
              )}
            </Stack>
            <Text as="p" size="sm" tone="secondary">
              {edge.thesis}
            </Text>
            {reason && (
              <Text as="p" size="sm">
                <GuideProse prose={reason} size="sm" />
              </Text>
            )}
          </Stack>
        );
      })}
    </Stack>
  );
}

export interface IdeaRowValue {
  id: string;
  title: string;
  mechanism: string;
  verdictText: string;
  verdict: string;
  feasibilityText: string;
  whyNotBuilt: string;
}

export interface IdeaRowsProps {
  ideas: readonly IdeaRowValue[];
  /** Mechanism titles by id: with it, each row names its mechanism (a link). */
  mechanisms?: ReadonlyMap<string, string>;
  'aria-label': string;
}

export function IdeaRows({ ideas, mechanisms, 'aria-label': ariaLabel }: IdeaRowsProps) {
  return (
    <Stack as="ul" gap={3} aria-label={ariaLabel}>
      {ideas.map((idea) => {
        const mechanism = mechanisms?.get(idea.mechanism);
        return (
          <Stack as="li" key={idea.id} gap={1}>
            <Stack direction="row" gap={2} align="center" wrap>
              <Text weight="semibold">{idea.title}</Text>
              <StatusBadge tone={ideaVerdictTone(idea.verdict)}>{idea.verdictText}</StatusBadge>
              <Chip label={idea.feasibilityText} />
              {mechanism !== undefined && (
                <TextLink href={mechanismPath(idea.mechanism)} size="sm" tone="secondary">
                  {mechanism}
                </TextLink>
              )}
            </Stack>
            <Text as="p" size="sm" tone="secondary">
              {idea.whyNotBuilt}
            </Text>
          </Stack>
        );
      })}
    </Stack>
  );
}
