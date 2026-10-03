/**
 * SearchInput: a search box (tickers, names, sectors) with a search icon, a clear button once
 * there is text, and Escape to clear. Sunken (canvas-coloured) as in the mockups' top bar and
 * ticker list. `loading` shows a spinner while results are being fetched. Named "Search" unless
 * given a label or placed in a Field.
 */
import { useRef, useState, type KeyboardEvent } from 'react';

import { useFieldControl } from '../Field';
import { Icon } from '../Icon';
import { IconButton } from '../IconButton';
import { Input } from '../Input';
import styles from './SearchInput.module.css';

export interface SearchInputProps {
  /** The query (controlled). */
  value?: string;
  /** The initial query (uncontrolled). */
  defaultValue?: string;
  /** Called with the query on every edit and with '' when cleared. */
  onValueChange?: (value: string) => void;
  /** Called on Enter with the current query. */
  onSubmit?: (value: string) => void;
  placeholder?: string;
  /** Accessible name; "Search" by default (ignored inside a Field, whose label names it). */
  'aria-label'?: string;
  /** Results are being fetched. */
  loading?: boolean;
  /** `full` (default) or `fixed` (the top bar's compact search width). */
  width?: 'full' | 'fixed';
  /** `md` (default) or `sm`. */
  size?: 'sm' | 'md';
  disabled?: boolean;
  name?: string;
}

export function SearchInput({
  value,
  defaultValue = '',
  onValueChange,
  onSubmit,
  placeholder,
  'aria-label': ariaLabel = 'Search',
  loading = false,
  width = 'full',
  size = 'md',
  disabled = false,
  name,
}: SearchInputProps) {
  const field = useFieldControl();
  const [internal, setInternal] = useState(defaultValue);
  const query = value ?? internal;
  const ref = useRef<HTMLInputElement>(null);

  const change = (next: string) => {
    if (value === undefined) setInternal(next);
    onValueChange?.(next);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape' && query) {
      event.preventDefault();
      change('');
    } else if (event.key === 'Enter') {
      onSubmit?.(query);
    }
  };

  const end = loading ? (
    <Icon name="spinner" spin label="Searching" />
  ) : query && !disabled ? (
    <IconButton
      icon="close"
      label="Clear search"
      size="sm"
      tabIndex={-1}
      onClick={() => {
        change('');
        ref.current?.focus();
      }}
    />
  ) : null;

  return (
    <div className={styles.searchInput} data-width={width}>
      <Input
        ref={ref}
        type="search"
        value={query}
        onValueChange={change}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        aria-label={field ? undefined : ariaLabel}
        start={<Icon name="search" />}
        end={end}
        size={size}
        sunken
        disabled={disabled}
        autoComplete="off"
        spellCheck={false}
        {...(name ? { name } : {})}
      />
    </div>
  );
}
