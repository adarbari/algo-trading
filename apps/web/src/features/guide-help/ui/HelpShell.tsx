/**
 * The button and drawer around one Guide entry, whatever its kind: the `InfoButton` (its hover
 * is the entry's first sentence when it has one), the `HelpDrawer` with the title block and
 * "Open full page", and the loading, error and no-entry states. The kind's own sections arrive as
 * children once the read is ready; a function child gets `close` (a button that changes the page
 * behind the drawer closes it so the change is seen).
 */
import {
  Button,
  ErrorState,
  HelpDrawer,
  InfoButton,
  Skeleton,
  Text,
  type InfoButtonProps,
} from '@algotrade/ui';
import { useState, type ReactNode } from 'react';

import { guidePath, type GuideEntry } from '../model/entry';
import { useGuideNavigate } from '../model/navigation';

export interface HelpShellProps {
  entry: GuideEntry;
  /** The button's accessible name ("What is X?"). */
  label: InfoButtonProps['label'];
  /** The drawer's title. */
  title: string;
  /** The small line above the title (a catalogue name, the kind). */
  eyebrow: ReactNode;
  /** The muted line under the title. */
  meta?: string;
  /** The entry's first sentence (the button's hover), once read. */
  summary?: string | undefined;
  /** The read's state: the children render only when `ready`. */
  state: 'pending' | 'error' | 'missing' | 'ready';
  /** What `missing` says. */
  missingText: string;
  onRetry: () => void;
  retrying: boolean;
  children: ReactNode | ((close: () => void) => ReactNode);
}

export function HelpShell({
  entry,
  label,
  title,
  eyebrow,
  meta,
  summary,
  state,
  missingText,
  onRetry,
  retrying,
  children,
}: HelpShellProps) {
  const [open, setOpen] = useState(false);
  const navigate = useGuideNavigate();
  const close = () => {
    setOpen(false);
  };
  return (
    <>
      <InfoButton
        label={label}
        {...(summary ? { summary } : {})}
        expanded={open}
        onClick={() => {
          setOpen(true);
        }}
      />
      <HelpDrawer
        open={open}
        onOpenChange={setOpen}
        eyebrow={eyebrow}
        title={title}
        {...(meta ? { meta } : {})}
        fullPage={
          <Button
            variant="ghost"
            size="sm"
            iconEnd="chevron-right"
            onClick={() => {
              close();
              navigate(guidePath(entry));
            }}
          >
            Open full page
          </Button>
        }
      >
        {state === 'pending' ? (
          <Skeleton label={`Loading ${title}`} />
        ) : state === 'error' ? (
          <ErrorState
            title={`${title} could not be loaded.`}
            onRetry={onRetry}
            retrying={retrying}
            compact
          />
        ) : state === 'missing' ? (
          <Text tone="muted">{missingText}</Text>
        ) : typeof children === 'function' ? (
          children(close)
        ) : (
          children
        )}
      </HelpDrawer>
    </>
  );
}
