/**
 * Feature: the six-step edge builder (ADR 0053 amendment, ED8). New edge, a copy of an edge or a
 * new version of a followed edge: idea, screens, picks, trade, compare against, test and run, one
 * draft saved whole through `PUT /edges/{id}`. Loaded lazily with its page: the settings it reads
 * (`Query.edge(id).settings`) stay out of the entry chunk.
 */
export { EdgeBuilder, type EdgeBuilderProps } from './ui/EdgeBuilder';
export { HelpProvider, type HelpFor } from './model/help';
