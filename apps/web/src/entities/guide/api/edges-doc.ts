/**
 * The Edges section's documents: the index, a mechanism and a site edge (`Query.guideEdgeIndex`,
 * `guideMechanism`, `guideEdge`): kept apart from `batch.ts` and loaded on its first use, so the entry's shared chunk
 * does not carry the Edges section's long selection (ADR 0051).
 */
import { graphql } from '@/shared/api';

export const GuideMechanismQuery = graphql(`
  query GuideMechanism($id: String!) {
    guideMechanism(id: $id) {
      id
      title
      question
      examples
      short
      howItWorks {
        segments {
          text
          field
        }
      }
      whyItSurvives {
        segments {
          text
          field
        }
      }
      research {
        segments {
          text
          field
        }
      }
      realVsDecoy {
        segments {
          text
          field
        }
      }
      dont {
        segments {
          text
          field
        }
      }
      seeAlso
      stats {
        title
        value
        reading
        source
      }
      sources {
        title
        url
        reading
      }
      edges {
        id
        name
        thesis
        mechanism
        asset
        assetText
        side
        sideTerm
        holdingSessions
        holdingText
        holdingBand
        status
      }
      notBuilt {
        id
        title
        mechanism
        verdict
        verdictText
        feasibilityText
        feasibilityTerm
        whyNotBuilt
      }
    }
  }
`);

export const GuideEdgeQuery = graphql(`
  query GuideEdge($id: String!) {
    guideEdge(id: $id) {
      summary {
        id
        name
        thesis
        mechanism
        asset
        assetText
        side
        sideTerm
        holdingSessions
        holdingText
        holdingBand
        status
      }
      mechanism {
        id
        title
      }
      thesis {
        segments {
          text
          field
        }
      }
      otherSide {
        segments {
          text
          field
        }
      }
      lasts {
        segments {
          text
          field
        }
      }
      research {
        measure
        figure
        expect
        haircut
        horizonText
        leg
        sample
        source
        terms
      }
      tests {
        key
        title
        text
        term
      }
      screeners {
        id
        name
        family
      }
      fields
      failureModes {
        segments {
          text
          field
        }
      }
      decoys {
        segments {
          text
          field
        }
      }
      rejection {
        segments {
          text
          field
        }
      }
      capacity {
        segments {
          text
          field
        }
      }
      sources {
        title
        url
        form
      }
      related {
        id
        name
        thesis
        mechanism
        asset
        assetText
        side
        sideTerm
        holdingSessions
        holdingText
        holdingBand
        status
      }
      seeAlso
    }
  }
`);

export const GuideEdgeIndexQuery = graphql(`
  query GuideEdgeIndex {
    guideEdgeIndex {
      mechanisms {
        id
        title
        question
        short
        examples
        count
        ideas
        statuses {
          status
          count
        }
        edges {
          id
          name
          thesis
          mechanism
          asset
          assetText
          side
          sideTerm
          holdingSessions
          holdingText
          holdingBand
          status
        }
      }
      filters {
        assets {
          id
          text
          count
        }
        sides {
          id
          text
          count
        }
        holdings {
          id
          text
          count
        }
      }
      setAsideTitle
      setAsidePurpose
      setAside {
        edge {
          id
          name
          thesis
          mechanism
          asset
          assetText
          side
          sideTerm
          holdingSessions
          holdingText
          holdingBand
          status
        }
        why {
          segments {
            text
            field
          }
        }
      }
      notBuiltTitle
      notBuiltPurpose
      notBuilt {
        id
        title
        mechanism
        verdict
        verdictText
        feasibilityText
        feasibilityTerm
        whyNotBuilt
      }
    }
  }
`);

export const GuideMechanismsQuery = graphql(`
  query GuideMechanisms {
    guideIndex {
      mechanisms {
        id
        title
        count
      }
    }
  }
`);

export const GuideScreenerEdgesQuery = graphql(`
  query GuideScreenerEdges($id: String!) {
    guideScreener(id: $id) {
      edges {
        id
        name
        thesis
        status
      }
    }
  }
`);
