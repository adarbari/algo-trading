/**
 * ToastProvider + useToast: the app-wide toast queue. Mount the provider once (src/app); any
 * component then calls `useToast().show({ title, tone, ... })`. Toasts stack in the bottom-end
 * corner (newest last, at most three), each dismissed after `duration` ms (default 5 s; negative
 * toasts stay until dismissed), paused while hovered or focused.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { Toast, type ToastProps } from './Toast';
import styles from './Toast.module.css';

export interface ToastOptions extends Omit<ToastProps, 'onDismiss'> {
  /** Milliseconds before it closes by itself; 0 keeps it until dismissed. */
  duration?: number;
}

export interface ToastApi {
  /** Shows a toast; returns its id. */
  show: (options: ToastOptions) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);
const DEFAULT_DURATION_MS = 5000;
const MAX_TOASTS = 3;

/** The toast queue's API; throws outside a ToastProvider. */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error('useToast() needs a <ToastProvider> above it (mount it in src/app).');
  return api;
}

interface Entry extends ToastOptions {
  id: string;
}

function TimedToast({ entry, onDismiss }: { entry: Entry; onDismiss: (id: string) => void }) {
  const { id, duration: ms, ...props } = entry;
  const duration = ms ?? (entry.tone === 'negative' ? 0 : DEFAULT_DURATION_MS);
  const [paused, setPaused] = useState(false);
  const remaining = useRef(duration);
  const item = useRef<HTMLLIElement>(null);
  // Pause while the pointer or keyboard focus is on the toast (listeners, not JSX handlers: an
  // <li> is not interactive, its buttons are).
  useEffect(() => {
    const node = item.current;
    if (!node) return undefined;
    const pause = () => {
      setPaused(true);
    };
    const resume = (event: Event) => {
      const next = (event as FocusEvent).relatedTarget;
      if (next instanceof Node && node.contains(next)) return;
      setPaused(false);
    };
    node.addEventListener('pointerenter', pause);
    node.addEventListener('pointerleave', resume);
    node.addEventListener('focusin', pause);
    node.addEventListener('focusout', resume);
    return () => {
      node.removeEventListener('pointerenter', pause);
      node.removeEventListener('pointerleave', resume);
      node.removeEventListener('focusin', pause);
      node.removeEventListener('focusout', resume);
    };
  }, []);
  useEffect(() => {
    if (duration === 0 || paused) return undefined;
    const started = Date.now();
    const timer = setTimeout(() => {
      onDismiss(id);
    }, remaining.current);
    return () => {
      clearTimeout(timer);
      remaining.current -= Date.now() - started;
    };
  }, [duration, paused, id, onDismiss]);
  return (
    <li ref={item} className={styles.item}>
      <Toast
        {...props}
        onDismiss={() => {
          onDismiss(id);
        }}
      />
    </li>
  );
}

export interface ToastProviderProps {
  children?: ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<Entry[]>([]);
  const next = useRef(0);
  const dismiss = useCallback((id: string) => {
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);
  const show = useCallback((options: ToastOptions) => {
    next.current += 1;
    const id = `toast-${String(next.current)}`;
    setToasts((all) => [...all, { ...options, id }].slice(-MAX_TOASTS));
    return id;
  }, []);
  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <section className={styles.viewport} aria-label="Notifications">
        <ol className={styles.list}>
          {toasts.map((entry) => (
            <TimedToast key={entry.id} entry={entry} onDismiss={dismiss} />
          ))}
        </ol>
      </section>
    </ToastContext.Provider>
  );
}
