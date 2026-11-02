/**
 * The idea-detail model: the `IdeaDetail` response as the idea page shows it. Pure: it renames
 * served values and never ranks, derives or fills a gap (docs/api/read-model.md "Presentation is
 * not derivation"); each section keeps the server's `unknown` when an input was missing.
 */
import type { ServedUnknown } from '@/entities/availability';
import type { gqlTypes } from '@/shared/api';

export type IdeaDetailResponse = gqlTypes.IdeaDetailQuery;
type Served = NonNullable<IdeaDetailResponse['idea']>;

export interface IdeaSetupRef {
  edgeId: string;
  edgeName: string;
  /** `stocks` or `premium`. */
  tab: string;
  /** The stored verdict level: `works` or `promising`. */
  level: string;
  /** Its place among the setup's own picks. */
  place: number;
}

export interface IdeaDetail {
  session: string;
  instrumentId: string;
  symbol: string | null;
  name: string | null;
  tab: string;
  setup: IdeaSetupRef;
  /** Every qualifying setup that picked the name, strongest first. */
  setups: IdeaSetupRef[];
  why: {
    thesis: string;
    mechanism: string;
    basisScreener: string;
    decision: string | null;
    criteria: {
      id: string;
      field: string;
      outcome: string;
      value: unknown;
      distance: number | null;
    }[];
    unknown: ServedUnknown | null;
  };
  exitRule: Served['exitRule'];
  evidence: Served['evidence'];
  risks: {
    persistence: string;
    holdEnds: string | null;
    watchOut: string[];
    events: { date: string; label: string; name: string }[];
    unknown: ServedUnknown | null;
  };
  /** The setup's id: the key of its Guide entry. */
  learn: string;
}

const setupRef = (s: Served['setup']): IdeaSetupRef => ({
  edgeId: s.edgeId,
  edgeName: s.edgeName,
  tab: s.tab === 'PREMIUM' ? 'premium' : 'stocks',
  level: s.level,
  place: s.place,
});

export function toIdeaDetail(response: IdeaDetailResponse): IdeaDetail | null {
  const found = response.idea;
  if (!found) return null;
  return {
    session: found.session,
    instrumentId: found.instrumentId,
    symbol: found.instrument?.symbol ?? null,
    name: found.instrument?.name ?? null,
    tab: found.tab === 'PREMIUM' ? 'premium' : 'stocks',
    setup: setupRef(found.setup),
    setups: found.setups.map(setupRef),
    why: {
      thesis: found.why.thesis,
      mechanism: found.why.mechanism,
      basisScreener: found.why.basisScreener,
      decision: found.why.decision ?? null,
      criteria: found.why.criteria.map((c) => ({
        id: c.id,
        field: c.field,
        outcome: c.outcome,
        value: c.value,
        distance: c.distance ?? null,
      })),
      unknown: found.why.unknown ?? null,
    },
    exitRule: found.exitRule,
    evidence: found.evidence,
    risks: {
      persistence: found.risks.persistence,
      holdEnds: found.risks.holdEnds ?? null,
      watchOut: found.risks.watchOut,
      events: found.risks.events.map((e) => ({ date: e.date, label: e.label, name: e.name })),
      unknown: found.risks.unknown ?? null,
    },
    learn: found.learn,
  };
}
