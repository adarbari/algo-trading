/** What a preview panel shows while the preview is idle, loading, failed or ready. Pure. */

export type PreviewPanelState = 'ready' | 'loading' | 'empty' | 'error';

export function previewPanelState(preview: {
  data: unknown;
  error: string | null;
  idle: boolean;
}): PreviewPanelState {
  if (preview.idle) return 'empty';
  if (preview.data) return 'ready';
  return preview.error ? 'error' : 'loading';
}
