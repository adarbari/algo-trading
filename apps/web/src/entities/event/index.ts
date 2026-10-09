/**
 * Entity: what is coming for a name and what it filed (`Instrument.eventStudy`) and the
 * cross-name event calendar (`Query.eventCalendar`), as the design system's event components
 * and the price chart's markers take them (ADR 0050).
 */
export { prefetchCalendar, useEventCalendar, type EventCalendarResponse } from './api/calendar';
export { useInstrumentEventStudy, type EventStudyResponse } from './api/study';
export {
  aheadItems,
  calendarDays,
  filingItem,
  gapLines,
  ladderRows,
  studyChartEvents,
  type StudyFiling,
} from './model/items';
export { CALENDAR_FIXTURE, STUDY_FIXTURE } from './model/fixtures';
