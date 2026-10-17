/** Page: Admin › LLM usage & cost (spend against the budget, breakdowns, recent calls). */
import { prefetchLlmUsage } from '@/entities/llm-usage';

export { AdminLlmUsagePage, type AdminLlmUsagePageProps } from './ui/AdminLlmUsagePage';

/** Start the page's reads before it mounts (the route's loader); the widgets' hooks join them. */
export function prefetchLlmUsageReads(client: Parameters<typeof prefetchLlmUsage>[0]): void {
  prefetchLlmUsage(client);
}
