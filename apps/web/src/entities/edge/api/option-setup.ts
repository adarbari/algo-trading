/**
 * An option setup's page read (ADR 0088): `Query.edgeOptionSetup`, the declared position (legs,
 * collateral, schedule, exits) and the setup's own history on the cash it sets aside. One read
 * per setup; a share setup answers with its `positionKind` and neither. Every value is the
 * server's, and history-derived evidence is gated there (an `unknown` stands where a viewer may
 * not see it); the browser derives nothing from it.
 */
import { useQuery } from '@tanstack/react-query';

import { gql, graphql, queryKeys } from '@/shared/api';

const OptionSetup = graphql(`
  query OptionSetup($id: String!) {
    edgeOptionSetup(id: $id) {
      edgeId
      positionKind
      rulesUnknown {
        code
        kind
        guideTerm
        kindText
      }
      rules {
        template
        collateral
        schedule
        startOffsetSessions
        tenorDays
        expiryCycle
        skipReportInLife
        takeProfit
        stopLoss
        exitDte
        exitConditionFields
        caseValued
        horizons
        legs {
          kind
          qty
          right
          strike
          delta
          otmPct
          tenorDays
        }
      }
      evidence {
        unknown {
          code
          kind
          guideTerm
          kindText
        }
        basisScreener
        basisHorizon
        trades
        typical
        typicalLo
        typicalHi
        badMean
        badTrades
        kept
        inSampleOnly
        costs {
          state
          assumedBp
          levels {
            period
            bp
            assumed
            level
            meanRoc
            winRate
          }
        }
        byYear {
          year
          trades
          typical
          kept
        }
        stress {
          key
          name
          start
          end
          trades
          worst
        }
        stressUnknown {
          code
          kind
          guideTerm
          kindText
        }
      }
    }
  }
`);

/** The option setup page of an edge (null: no such edge). */
export function useOptionSetup(id: string) {
  return useQuery({
    queryKey: queryKeys.gql('OptionSetup', { id }),
    queryFn: ({ queryKey }) => gql(OptionSetup, { id }, queryKey),
    select: (data) => data.edgeOptionSetup,
  });
}
