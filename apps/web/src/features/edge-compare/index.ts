/**
 * Feature: a user's copy of an edge compared with the edge it extends and the baselines
 * (`Edge.compare`): one read per copy, only when its page shows the comparison. The document is
 * written here, not through `graphql()`, so it stays out of the generated operation map every
 * route loads; the rows are the server's (the out-of-sample figures are withheld until shown).
 */
export { useEdgeCompare, type CompareRow, type EdgeCompareResult } from './api/hooks';
