/**
 * "Onboard a user": id, email and name declare a trader. On success the form shows the one step
 * left at the identity provider as a Guide reference with the address to add; a refusal (invalid
 * input, a taken id or email, not an admin) shows the server's detail on the form.
 */
import { Banner, Button, Field, Input, Mono, Panel, Stack } from '@algotrade/ui';
import { useState } from 'react';

import {
  isUserId,
  PROVIDER_STEP_TERMS,
  useOnboardUser,
  TERM_OF_ONBOARD,
  TERM_OF_PENDING_PROVIDER,
} from '@/entities/user-registry';
import { termHelp } from '@/features/guide-help';
import { errorDetail } from '@/shared/api';

export function OnboardUserForm() {
  const [userId, setUserId] = useState('');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const onboard = useOnboardUser();
  const idError = userId !== '' && !isUserId(userId) ? 'Use 1-64 of a-z, 0-9, _ and -.' : undefined;
  const result = onboard.data;
  const stepTerm = result ? PROVIDER_STEP_TERMS[result.provider_step.instruction] : undefined;
  return (
    <Panel title="Onboard a user" actions={termHelp(TERM_OF_ONBOARD)}>
      <Stack gap={3}>
        <Field label="User id" {...(idError ? { error: idError } : {})}>
          <Input
            value={userId}
            onValueChange={setUserId}
            mono
            autoComplete="off"
            spellCheck={false}
          />
        </Field>
        <Field label="Email">
          <Input type="email" value={email} onValueChange={setEmail} autoComplete="off" />
        </Field>
        <Field label="Name">
          <Input value={name} onValueChange={setName} autoComplete="off" />
        </Field>
        {onboard.error && <Banner tone="negative">{errorDetail(onboard.error)}</Banner>}
        {result && (
          <Banner
            tone="info"
            title={
              <>
                <Mono>{result.user_id}</Mono> is declared
              </>
            }
            actions={
              <>
                {termHelp(TERM_OF_PENDING_PROVIDER)}
                {stepTerm && termHelp(stepTerm)}
              </>
            }
          >
            <Mono>{result.provider_step.email}</Mono>
          </Banner>
        )}
        <Button
          variant="primary"
          disabled={!isUserId(userId) || email.trim() === ''}
          loading={onboard.isPending}
          onClick={() => {
            onboard.mutate(
              { userId, email: email.trim(), name: name.trim() },
              {
                onSuccess: () => {
                  setUserId('');
                  setEmail('');
                  setName('');
                },
              },
            );
          }}
        >
          Onboard
        </Button>
      </Stack>
    </Panel>
  );
}
