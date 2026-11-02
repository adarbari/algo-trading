/**
 * The Test flow's route components after the start (Guided, a new draft, Expert, Result, Setup),
 * loaded on first visit so the `returnTo` handling stays out of the entry chunk. Opened from the
 * setup builder, a new draft, Expert and Result carry `returnTo=<edge id>` (`.new`: a new edge)
 * and Expert's "Save and return" then goes back in history.
 */
import { useNavigate, useParams, useRouter, useSearch } from '@tanstack/react-router';

import { compareSearch } from '@/features/idea-compare';
import {
  TestExpertPage,
  TestGuidedPage,
  TestNewPage,
  TestResultPage,
  TestSetupPage,
} from '@/pages/test';

/** What each route preloads with the glue: the heavy page's own chunk (it then renders unsuspended). */
export const preloadExpert = TestExpertPage.preload;
export const preloadResult = TestResultPage.preload;
export const preloadSetup = TestSetupPage.preload;

/** A new edge has no id yet: "Save and return to edge" goes back to its builder as `.new`. */
const NEW_EDGE = '.new';

export function Guided() {
  const navigate = useNavigate();
  return (
    <TestGuidedPage onPick={(id) => void navigate({ to: '/test/expert/$id', params: { id } })} />
  );
}

function NewDraft({ way }: { way: 'expert' | 'describe' }) {
  const navigate = useNavigate();
  return (
    <TestNewPage
      way={way}
      onCancel={() => void navigate({ to: '/test' })}
      onCreated={(id) =>
        void navigate({ to: '/test/expert/$id', params: { id }, search: (prev) => prev })
      }
    />
  );
}

export const NewExpert = () => <NewDraft way="expert" />;
export const NewDescribe = () => <NewDraft way="describe" />;

export function Expert() {
  const { id } = useParams({ strict: false });
  const search: Record<string, unknown> = useSearch({ strict: false });
  const navigate = useNavigate();
  const router = useRouter();
  return (
    <TestExpertPage
      id={id ?? ''}
      onReturn={
        search['returnTo']
          ? () => {
              router.history.back();
            }
          : undefined
      }
      onDeleted={() => void navigate({ to: '/test' })}
      onOpenTicker={(symbol) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })
      }
      onOpenRegime={() => void navigate({ to: '/regime' })}
    />
  );
}

export function Result() {
  const { id = '' } = useParams({ strict: false });
  const { f }: { f?: string } = useSearch({ strict: false });
  const navigate = useNavigate();
  return (
    <TestResultPage
      id={id}
      f={f}
      onFilterChange={(next) =>
        void navigate({
          to: '/test/result/$id',
          params: { id },
          search: next ? { f: next } : {},
          replace: true,
        })
      }
      onEdit={() => void navigate({ to: '/test/expert/$id', params: { id } })}
      onBuildSetup={() => void navigate({ to: '/test/setup' })}
      onOpenTicker={(symbol) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })
      }
      onCompare={(symbols) => {
        const search = compareSearch(symbols);
        if (search) void navigate({ to: '/explore', search });
      }}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
    />
  );
}

export function Setup() {
  const { id } = useParams({ strict: false });
  const navigate = useNavigate();
  const router = useRouter();
  return (
    <TestSetupPage
      id={id ?? null}
      onCancel={() => {
        router.history.back();
      }}
      onOpenEdge={(edge) => void navigate({ to: '/edges', search: { edge } })}
      onOpenScreen={(screenId, from) => {
        const search = { returnTo: from ?? NEW_EDGE };
        if (screenId === null) void navigate({ to: '/test/expert', search });
        else void navigate({ to: '/test/expert/$id', params: { id: screenId }, search });
      }}
    />
  );
}
