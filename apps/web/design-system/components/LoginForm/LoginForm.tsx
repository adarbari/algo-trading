/**
 * LoginForm: sign in with an email and a password. Presentational: it holds the two typed
 * values and hands them to `onSubmit`; the page does the request and passes back `pending`
 * (the button shows a spinner and the fields lock) and `error` (one message for the whole
 * attempt, shown above the fields and announced as an alert; both fields are marked invalid
 * and described by it). Enter submits from either field, and the browser checks that the
 * email is filled and shaped like one. `onEdit` tells the page the user is typing again.
 */
import { useId, useState, type SyntheticEvent } from 'react';

import { Heading } from '../../primitives/Heading';
import { Stack } from '../../primitives/Stack';
import { Surface } from '../../primitives/Surface';
import { Text } from '../../primitives/Text';
import { Button } from '../Button';
import { Field } from '../Field';
import { Icon } from '../Icon';
import { Input } from '../Input';
import styles from './LoginForm.module.css';

/** What the form hands to `onSubmit`. */
export interface LoginCredentials {
  /** The email as typed, without surrounding spaces. */
  email: string;
  /** The password exactly as typed. */
  password: string;
}

export interface LoginFormProps {
  /** Called with the credentials when the form is submitted (never while `pending`). */
  onSubmit: (credentials: LoginCredentials) => void;
  /** A sign-in request is running: the button shows a spinner and the fields are disabled. */
  pending?: boolean;
  /** Why the last attempt failed ("Wrong email or password"); shown until the page clears it. */
  error?: string | undefined;
  /** The form's heading (an h1: the form is the page's one task); "Sign in" by default. */
  title?: string;
  /** An email to start with (the one used last time). */
  defaultEmail?: string;
  /** Called when either field is edited, so the page can clear a stale `error`. */
  onEdit?: () => void;
}

export function LoginForm({
  onSubmit,
  pending = false,
  error,
  title = 'Sign in',
  defaultEmail = '',
  onEdit,
}: LoginFormProps) {
  const ids = useId();
  const headingId = `${ids}heading`;
  const errorId = error ? `${ids}error` : undefined;
  const [email, setEmail] = useState(defaultEmail);
  const [password, setPassword] = useState('');

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;
    onSubmit({ email: email.trim(), password });
  };

  return (
    <form className={styles.form} onSubmit={submit} aria-labelledby={headingId}>
      <Surface padding={5}>
        <Stack gap={4}>
          <Heading level={1} id={headingId}>
            {title}
          </Heading>
          {error && (
            <span id={errorId} className={styles.error} role="alert">
              <Icon name="alert" size="sm" tone="negative" />
              <Text size="sm" tone="negative">
                {error}
              </Text>
            </span>
          )}
          <Field label="Email" required disabled={pending}>
            <Input
              type="email"
              inputMode="email"
              autoComplete="email"
              spellCheck={false}
              value={email}
              onValueChange={(value) => {
                setEmail(value);
                onEdit?.();
              }}
              invalid={Boolean(error)}
              aria-describedby={errorId}
            />
          </Field>
          <Field label="Password" required disabled={pending}>
            <Input
              type="password"
              autoComplete="current-password"
              value={password}
              onValueChange={(value) => {
                setPassword(value);
                onEdit?.();
              }}
              invalid={Boolean(error)}
              aria-describedby={errorId}
            />
          </Field>
          <Button type="submit" variant="primary" loading={pending} fullWidth>
            Sign in
          </Button>
        </Stack>
      </Surface>
    </form>
  );
}
