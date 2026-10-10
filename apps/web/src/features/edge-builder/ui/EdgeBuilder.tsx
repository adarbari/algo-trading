/**
 * The edge builder (ADR 0053 amendment, ED8): six steps in one scroll behind a SectionNav, one
 * draft. The edge is the user's own: a new one, a copy of a site edge, or a new version of a
 * followed edge. It starts from what the server resolved for the edge (`Edge.settings`), is kept
 * while the user edits a screen in the Screen Builder and comes back, and is saved whole through
 * `PUT /edges/{id}`; the server checks it as the harness will read it and its refusal is shown.
 */
import {
  Banner,
  Box,
  Button,
  Heading,
  Panel,
  SectionNav,
  Skeleton,
  Stack,
  StatusBadge,
  Text,
} from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import { useEdges, type Edge } from '@/entities/edge';
import { useScreeners } from '@/entities/screen';
import { errorDetail } from '@/shared/api';

import { useSaveEdge } from '../api/hooks';
import { useEdgeSettings, type EdgeSettings } from '../api/settings';
import {
  blankDraft,
  draftOf,
  incomplete,
  isDirty,
  isEdgeId,
  STEPS,
  toDocument,
  type EdgeDraft,
  type Mode,
  type Step,
} from '../model/draft';
import { useHelp } from '../model/help';
import { STEP_LABELS } from '../model/options';
import { clearStash, NEW_KEY, stash, unstash } from '../model/stash';
import { CompareStep } from './CompareStep';
import { IdeaStep } from './IdeaStep';
import { PicksStep } from './PicksStep';
import { ScreensStep } from './ScreensStep';
import { TestStep } from './TestStep';
import { TradeStep } from './TradeStep';

export interface EdgeBuilderProps {
  /** The edge to build or change (the user's own); null: a new edge. */
  id: string | null;
  /** Saved: open it, and run the backtest when asked. */
  onSaved: (id: string, run: boolean) => void;
  onCancel: () => void;
  /** Open the Screen Builder on a screen (null: a new one); the draft is kept meanwhile. */
  onOpenScreen: (id: string | null) => void;
}

export function EdgeBuilder({ id, ...rest }: EdgeBuilderProps) {
  const edges = useEdges();
  const settings = useEdgeSettings(id);
  if (id === null) return <Builder {...rest} edge={null} served={null} id={null} />;
  const edge = edges.data?.find((e) => e.id === id);
  if (edges.isError || settings.isError) {
    return <Banner tone="negative">The edge could not be loaded.</Banner>;
  }
  if (edges.isPending || settings.isPending)
    return <Skeleton lines={8} label="Loading the edge…" />;
  if (!edge || !settings.data?.settings || !edge.mine) {
    return <Banner tone="warning">You have no edge of this name to change.</Banner>;
  }
  return <Builder {...rest} edge={edge} served={settings.data} id={id} />;
}

const modeOf = (edge: Edge | null): Mode =>
  edge === null || edge.extends === null ? 'new' : edge.state === 'trial' ? 'version' : 'clone';

const HEADINGS: Record<Mode, string> = {
  new: 'New edge',
  clone: 'Your copy of an edge',
  version: 'New version of an edge',
};

interface BuilderProps extends Omit<EdgeBuilderProps, 'id'> {
  id: string | null;
  edge: Edge | null;
  served: EdgeSettings | null;
}

function Builder({ id, edge, served, onSaved, onCancel, onOpenScreen }: BuilderProps) {
  const key = id ?? NEW_KEY;
  const mode = modeOf(edge);
  const [initial] = useState<EdgeDraft>(() =>
    edge && served ? draftOf(edge, served) : blankDraft(),
  );
  const [left] = useState(() => unstash(key));
  const [merged, setMerged] = useState(false);
  const [draft, setDraft] = useState<EdgeDraft>(() => left?.draft ?? initial);
  const screeners = useScreeners();
  const ids = (screeners.data ?? []).map((s) => s.configId);
  // Back from the Screen Builder: the screens made there since the user left join the draft.
  if (left && !merged && screeners.data && !screeners.isFetching) {
    setMerged(true);
    const added = ids.filter((s) => !left.known.includes(s));
    if (added.length > 0) {
      setDraft((d) => ({ ...d, screeners: [...new Set([...d.screeners, ...added])] }));
    }
  }
  const save = useSaveEdge();
  const help = useHelp();
  const blocked = incomplete(draft, mode);
  const own = served?.settings?.own ?? {};
  const trials = Math.max(0, ...(edge?.runs.map((r) => r.trialsCounted ?? 0) ?? []));
  const change = (patch: Partial<EdgeDraft>) => {
    setDraft((d) => ({ ...d, ...patch }));
  };
  const submit = (run: boolean) => {
    const target = id ?? draft.id;
    save.mutate(
      { id: target, document: toDocument(draft, own, edge?.extends ?? null) },
      {
        onSuccess: () => {
          clearStash(key);
          onSaved(target, run);
        },
      },
    );
  };
  const section = (step: Step, body: ReactNode) => (
    <Box id={step} key={step}>
      <Panel
        title={STEP_LABELS[step]}
        actions={help(`edge_builder_${step}`)}
        description={blocked.includes(step) ? 'Needs an answer' : undefined}
      >
        {body}
      </Panel>
    </Box>
  );
  return (
    <Stack gap={3}>
      <Stack direction="row" gap={3} align="center" justify="between" wrap>
        <Stack gap={1}>
          <Text size="sm" tone="muted">
            {HEADINGS[mode]}
          </Text>
          <Stack direction="row" gap={2} align="baseline" wrap>
            <Heading level={1}>{draft.name || 'Untitled edge'}</Heading>
            <StatusBadge tone={isDirty(draft, initial) ? 'warning' : 'neutral'}>
              {isDirty(draft, initial) ? 'Draft · unsaved changes' : 'Draft'}
            </StatusBadge>
          </Stack>
        </Stack>
        <Button
          variant="ghost"
          onClick={() => {
            clearStash(key);
            onCancel();
          }}
        >
          Cancel
        </Button>
      </Stack>
      <SectionNav
        aria-label="Edge builder steps"
        items={STEPS.map((step) => ({ id: step, label: STEP_LABELS[step] }))}
      />
      {save.error && (
        <Banner tone="negative" title="The edge was not saved">
          {errorDetail(save.error)}
        </Banner>
      )}
      {section(
        'idea',
        <IdeaStep
          draft={draft}
          onChange={change}
          chooseId={id === null}
          idError={
            draft.id !== '' && !isEdgeId(draft.id) ? 'Use 1-64 of a-z, 0-9, _ and -.' : undefined
          }
        />,
      )}
      {section(
        'screens',
        <ScreensStep
          draft={draft}
          onChange={change}
          onOpenScreen={(screen) => {
            stash(key, draft, ids);
            onOpenScreen(screen);
          }}
        />,
      )}
      {section('picks', <PicksStep draft={draft} onChange={change} />)}
      {section('trade', <TradeStep draft={draft} onChange={change} />)}
      {section('compare', <CompareStep draft={draft} onChange={change} />)}
      {section(
        'test',
        <TestStep
          draft={draft}
          onChange={change}
          trials={trials}
          ready={blocked.length === 0}
          saving={save.isPending}
          onSave={submit}
        />,
      )}
    </Stack>
  );
}
