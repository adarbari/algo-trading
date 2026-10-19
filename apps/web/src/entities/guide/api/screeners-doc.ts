/**
 * The Screeners section's two own documents: the lead page and a family's page
 * (`Query.guideScreenerIndex`, `guideScreenerCategory`), kept apart from `hooks.ts` and loaded on
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
