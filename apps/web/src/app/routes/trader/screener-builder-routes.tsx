/**
 * The Screen Builder's route components (a new screen, a screen's Builder), loaded on first visit
 * so the `returnTo` handling stays out of the entry chunk. Opened from an edge's builder they carry
 * `returnTo=<edge id>` and then go back in history (the new screen keeps it across the redirect
 * to its Builder).
 */
import { useNavigate, useParams, useRouter, useSearch } from '@tanstack/react-router';

import { NewScreenerPage, ScreenerBuilderPage } from '@/pages/screener-builder';

export function NewScreener() {
  const navigate = useNavigate();
  return (
    <NewScreenerPage
      onCancel={() => void navigate({ to: '/screeners' })}
      onCreated={(id) =>
        void navigate({ to: '/screeners/$id/edit', params: { id }, search: (prev) => prev })
      }
    />
  );
}

export function EditScreener() {
  const { id } = useParams({ strict: false });
  const search: Record<string, unknown> = useSearch({ strict: false });
  const navigate = useNavigate();
  const router = useRouter();
  return (
    <ScreenerBuilderPage
      id={id ?? ''}
      onReturn={
        search['returnTo']
          ? () => {
              router.history.back();
            }
          : undefined
      }
      onDeleted={() => void navigate({ to: '/screeners' })}
      onOpenTicker={(symbol) =>
        void navigate({ to: '/explore', search: { sel: symbol, focus: symbol } })
      }
      onOpenRegime={() => void navigate({ to: '/regime' })}
    />
  );
}
