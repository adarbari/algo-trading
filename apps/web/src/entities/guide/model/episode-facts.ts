/**
 * The facts of a reference market fall as rows of a `KeyValue` list (the Guide's episode page and
 * its help drawer show the same ones): the S&P 500's peak, trough and recovery, how far the S&P 500
 * and the Nasdaq fell, and whether the NBER dated a recession in it.
 */
import { formatValue, type KeyValueItem } from '@algotrade/ui';

/** The episode's own fields, as `Query.guideEpisode` returns them. */
export interface EpisodeFacts {
  peak: string;
  trough: string;
  recovered?: string | null | undefined;
  spxDrawdown: number;
  nasdaqDrawdown: number;
  recession: boolean;
  nberStart?: string | null | undefined;
  nberEnd?: string | null | undefined;
}

const date = (value: string) => formatValue(value, { kind: 'date' }).text;

export function episodeFacts(episode: EpisodeFacts): KeyValueItem[] {
  return [
    { label: 'S&P 500 peak', value: date(episode.peak) },
    { label: 'S&P 500 trough', value: date(episode.trough) },
    { label: 'Recovered', value: episode.recovered ? date(episode.recovered) : 'Not yet' },
    { label: 'S&P 500 fall', value: episode.spxDrawdown, format: { kind: 'percent', digits: 0 } },
    { label: 'Nasdaq fall', value: episode.nasdaqDrawdown, format: { kind: 'percent', digits: 0 } },
    {
      label: 'NBER recession',
      value:
        episode.recession && episode.nberStart && episode.nberEnd
          ? `${date(episode.nberStart)} to ${date(episode.nberEnd)}`
          : episode.recession
            ? 'Yes'
            : 'No',
    },
  ];
}
