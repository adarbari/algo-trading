/** The out-of-sample start the builder accepts: a real calendar day as ISO text (2026-04-01). Pure. */

const ISO = /^\d{4}-\d{2}-\d{2}$/;

/** Whether `text` is a real calendar day written yyyy-mm-dd (2026-02-30 is not). */
export function isIsoDate(text: string): boolean {
  if (!ISO.test(text)) return false;
  const parsed = new Date(`${text}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(text);
}
