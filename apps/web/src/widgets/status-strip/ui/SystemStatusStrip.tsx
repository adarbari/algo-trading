/**
 * The status strip of every page: the open system issues (entities/system-status) minus the
 * ones the viewer snoozed (features/issue-snooze), in the design system's StatusStrip. A clear
 * system shows nothing (the quieter choice; the strip appears only when there is something to
 * act on). Each issue's links go through the app's router link.
 */
import { StatusStrip, TextLink, type StatusIssue } from '@algotrade/ui';

import { useSystemIssues, type SystemIssue } from '@/entities/system-status';
import { useSnooze } from '@/features/issue-snooze';

export interface SystemStatusStripProps {
  /** The viewer may read the nightly run (an admin). */
  admin: boolean;
}

const toIssue = (issue: SystemIssue): StatusIssue => ({
  id: issue.id,
  severity: issue.severity,
  title: issue.title,
  ...(issue.detail !== undefined ? { detail: issue.detail } : {}),
  actions: (
    <>
      {issue.links.map((link) => (
        <TextLink key={link.href} href={link.href} size="sm">
          {link.label}
        </TextLink>
      ))}
    </>
  ),
});

export function SystemStatusStrip({ admin }: SystemStatusStripProps) {
  const { visible, snooze } = useSnooze();
  const issues = visible(useSystemIssues(admin));
  return <StatusStrip issues={issues.map(toIssue)} onSnooze={snooze} />;
}
