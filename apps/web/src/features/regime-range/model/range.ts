/**
 * The window the regime history charts share: a preset counted back from the session ("All",
 * "20y" ... "2y") or one named window (an episode's: a year before its peak to six months after
 * its recovery). One state for every chart of the page, so choosing an episode in the table moves
 * them all; the provider holds it, and a chart outside a provider keeps its own.
 */
import { createContext, useCallback, useContext, useState } from 'react';

import { presetWindow, type HistoryWindow, type RangePreset } from '@/entities/regime';

export type RangeSelection =
  { kind: 'preset'; preset: RangePreset } | { kind: 'window'; name: string; window: HistoryWindow };

export type RangeState = readonly [RangeSelection, (selection: RangeSelection) => void];

export const DEFAULT_SELECTION: RangeSelection = { kind: 'preset', preset: 'all' };

export const RangeContext = createContext<RangeState | null>(null);

export interface RegimeRange {
  /** The days the charts cover (a preset counted back from `session`). */
  window: HistoryWindow;
  /** The chosen preset, or null while a named window is shown. */
  preset: RangePreset | null;
  /** The named window's name ("Covid crash, early 2020"), or null. */
  windowName: string | null;
  setPreset: (preset: RangePreset) => void;
  setWindow: (name: string, window: HistoryWindow) => void;
}

/** The shared window, resolved against `session` (the regime's session date). */
export function useRegimeRange(session: string): RegimeRange {
  const local = useState<RangeSelection>(DEFAULT_SELECTION);
  const [selection, setSelection] = useContext(RangeContext) ?? local;
  const setPreset = useCallback(
    (preset: RangePreset) => {
      setSelection({ kind: 'preset', preset });
    },
    [setSelection],
  );
  const setWindow = useCallback(
    (name: string, window: HistoryWindow) => {
      setSelection({ kind: 'window', name, window });
    },
    [setSelection],
  );
  return selection.kind === 'preset'
    ? {
        window: presetWindow(selection.preset, session),
        preset: selection.preset,
        windowName: null,
        setPreset,
        setWindow,
      }
    : {
        window: selection.window,
        preset: null,
        windowName: selection.name,
        setPreset,
        setWindow,
      };
}
