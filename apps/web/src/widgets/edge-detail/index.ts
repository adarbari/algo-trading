/**
 * Widget: the head of an edge's page (name, verdict, owner and status, the actions, the headline,
 * what would change the verdict) and the sections the page composes below it (how the edge is
 * defined, the live record, a copy's comparison, the details), the page loads them in one lazy chunk.
 */
export { EdgeHeader, type EdgeHeaderProps } from './ui/EdgeHeader';
export { EdgeCompare } from './ui/EdgeCompare';
export { EdgeDefinition } from './ui/EdgeDefinition';
export { EdgeDetails } from './ui/EdgeDetails';
export { EdgeLive } from './ui/EdgeLive';
