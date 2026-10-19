/**
 * The Screeners section's documents: the lead page, a family's page and a screener's page
 * (`Query.guideScreenerIndex`, `guideScreenerCategory`, `guideScreener`), kept apart from `hooks.ts` and loaded on
 * first use, as the Edges section's are (ADR 0051): only the Screeners pages carry them.
 */
import { graphql } from '@/shared/api';

export const GuideScreenerIndexQuery = graphql(`
  query GuideScreenerIndex {
    guideScreenerIndex {
      what
      versusEdge
      count
      categories {
        id
        title
        purpose
        count
      }
    }
  }
`);

export const GuideScreenerCategoryQuery = graphql(`
  query GuideScreenerCategory($id: String!) {
    guideScreenerCategory(id: $id) {
      id
      title
      purpose
      intro
      screeners {
        id
        name
        line
        edges {
          id
          name
          status
        }
      }
    }
  }
`);

export const GuideScreenerQuery = graphql(`
  query GuideScreener($id: String!) {
    guideScreener(id: $id) {
      id
      name
      family
      familyTitle
      version
      prose {
        summary {
          segments {
            text
            field
            source
          }
        }
        hit {
          segments {
            text
            field
            source
          }
        }
        notChecked {
          segments {
            text
            field
            source
          }
        }
        beforeActing {
          segments {
            text
            field
            source
          }
        }
        sources {
          title
          url
          note
        }
      }
      criteria {
        name
        asks
        field
        rule
        mode
        onMiss
      }
      tieBreak
      tieBreakDescending
      related {
        id
        name
        reason
      }
      situations {
        slug
        name
        fields
      }
    }
  }
`);
