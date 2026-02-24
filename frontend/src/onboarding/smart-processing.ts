/**
 * Smart Processing — on-device algorithmic contact scoring and pattern extraction.
 * No LLM required. Runs entirely in JavaScript on the device.
 *
 * Signal weights (max ~20):
 *   Has photo          +2   (you care enough to add one)
 *   Starred            +3   (explicit favourite)
 *   Calls 11+/90d      +4   call frequency
 *   Calls 6-10/90d     +3
 *   Calls 3-5/90d      +2
 *   Calls 1-2/90d      +1
 *   Last call <14d     +4   recency
 *   Last call <30d     +3
 *   Last call <90d     +1
 *   Both email+phone   +2   contact richness
 *   Multiple emails    +1
 *   Multiple phones    +1
 *   Has company        +1
 *   Has job title      +1
 *   Has dates          +1   (birthday/anniversary → personal relationship)
 */

// ---- Types ----

interface RawContact {
  name?: string;
  firstName?: string;
  lastName?: string;
  emails?: Array<{ email: string; label?: string }>;
  phoneNumbers?: Array<{ number: string; label?: string }>;
  company?: string;
  jobTitle?: string;
  starred?: boolean;
  contactType?: string;
  imageAvailable?: boolean;
  dates?: Array<{ value?: string; label?: string }>;
}

export interface CallLogEntry {
  /** Total calls in the scoring window (90 days). */
  count: number;
  /** Most recent call timestamp. */
  lastDate: Date;
}

export interface ScoredContact {
  name: string;
  email: string;
  phone: string;
  company: string;
  role: string;
  relationship: string;
  importance: 'high' | 'medium' | 'low';
  preferred_channel: string;
  starred: boolean;
  score: number;
  aliases: string[];
  import_source: string;
}

// ---- Phone normalisation (last 10 digits, digits only) ----

export function normalizePhone(raw: string): string {
  const digits = raw.replace(/\D/g, '');
  return digits.length >= 10 ? digits.slice(-10) : digits;
}

// ---- Contact Scoring ----

/**
 * Score, rank, and return the top `maxResults` contacts.
 *
 * @param callLogMap  Optional map normalizedPhone → CallLogEntry.
 *                    Built from Android call logs before this is called.
 *                    When present, adds up to +8 points per contact.
 */
export function scoreAndFilterContacts(
  contacts: RawContact[],
  maxResults: number = 15,
  callLogMap?: Map<string, CallLogEntry>,
): ScoredContact[] {
  const now = Date.now();
  const scored: ScoredContact[] = [];

  for (const c of contacts) {
    const name = c.name || [c.firstName, c.lastName].filter(Boolean).join(' ');
    if (!name) continue;

    const email = c.emails?.[0]?.email || '';
    const phone = c.phoneNumbers?.[0]?.number || '';

    // ── HARD GATE: must have actual interaction signal ─────────────────────
    // Only applied when call log data is available (permission granted, calls exist).
    // When call log is unavailable (permission denied or no calls in 90d),
    // skip the gate and score all contacts by richness only.
    const normalised = phone ? normalizePhone(phone) : '';
    const callData = (callLogMap && normalised) ? callLogMap.get(normalised) : undefined;
    const hasCallLogData = callLogMap && callLogMap.size > 0;
    if (hasCallLogData) {
      const hasInteraction = c.starred || (callData !== undefined);
      if (!hasInteraction) continue;
    }

    let score = 0;

    // ── Richness signals (context only — NOT relationship strength) ────────
    if (email && phone) score += 2;
    if (c.emails && c.emails.length > 1) score += 1;
    if (c.phoneNumbers && c.phoneNumbers.length > 1) score += 1;
    if (c.starred) score += 4;                // explicit favourite — strong signal

    // ── Photo signal (+2) ─────────────────────────────────────────────────
    if (c.imageAvailable) score += 2;

    // ── Personal relationship signal (+2) ─────────────────────────────────
    // Has a birthday or anniversary → genuine personal relationship
    if (c.dates && c.dates.length > 0) score += 2;

    // ── Call log signals (up to +8) ───────────────────────────────────────
    if (callData) {
      // Frequency (calls in last 90 days)
      const count = callData.count;
      if (count >= 11) score += 4;
      else if (count >= 6) score += 3;
      else if (count >= 3) score += 2;
      else if (count >= 1) score += 1;

      // Recency (days since last call)
      const daysSince = (now - callData.lastDate.getTime()) / 86_400_000;
      if (daysSince < 14) score += 4;
      else if (daysSince < 30) score += 3;
      else if (daysSince < 90) score += 1;
    }

    const relationship = inferRelationship(c);
    // Raised thresholds — brief contacts must NOT appear as high importance
    // high (Inner Circle): must have accumulated strong multi-signal score
    // medium: meaningful but not core circle
    // low:  peripheral — rarely shown in UI
    const importance = score >= 12 ? 'high' : score >= 6 ? 'medium' : 'low';
    const preferred_channel = email && phone ? 'whatsapp' : phone ? 'call' : 'email';

    const aliases: string[] = [];
    if (c.firstName && c.lastName && c.name !== c.firstName) aliases.push(c.firstName);

    scored.push({
      name,
      email,
      phone,
      company: c.company || '',
      role: c.jobTitle || '',
      relationship,
      importance,
      preferred_channel,
      starred: c.starred || false,
      score,
      aliases,
      import_source: 'auto',
    });
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, maxResults);
}

function inferRelationship(contact: RawContact): string {
  const email = (contact.emails?.[0]?.email || '').toLowerCase();
  const job = (contact.jobTitle || '').toLowerCase();
  const company = (contact.company || '').toLowerCase();

  if (['manager', 'director', 'vp', 'chief', 'head', 'lead'].some(k => job.includes(k))) return 'work';
  if (company) return 'work';
  const personalDomains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com'];
  if (personalDomains.some(d => email.endsWith(d))) return 'personal';
  if (email && email.includes('@')) return 'work';
  return 'other';
}


// ---- Calendar Pattern Extraction ----

interface RawCalendarEvent {
  title?: string;
  startDate?: string;
  endDate?: string;
  recurrenceRule?: { frequency?: string; interval?: number };
  attendees?: Array<{ name?: string }>;
  location?: string;
  notes?: string;
}

export interface ExtractedRoutine {
  title: string;
  time: string;
  frequency: string;
  days: string[];
  duration_minutes: number;
  attendees: number;
  routine_type: string;
  import_source: string;
}

export interface ExtractedPattern {
  pattern_type: string;
  description: string;
  time: string;
  frequency: string;
  days: string[];
  confidence: number;
}

export function extractCalendarPatterns(events: RawCalendarEvent[]): {
  routines: ExtractedRoutine[];
  patterns: ExtractedPattern[];
} {
  const routines: ExtractedRoutine[] = [];
  const patterns: ExtractedPattern[] = [];
  const titleCounts: Record<string, { count: number; times: string[]; days: Set<string>; durations: number[]; attendees: number[] }> = {};

  for (const event of events) {
    if (!event.title) continue;
    const title = event.title.trim();
    const startTime = event.startDate ? extractTime(event.startDate) : '';
    const day = event.startDate ? extractDay(event.startDate) : '';
    const duration = calcDuration(event.startDate, event.endDate);
    const attendeeCount = event.attendees?.length || 0;

    if (!titleCounts[title]) {
      titleCounts[title] = { count: 0, times: [], days: new Set(), durations: [], attendees: [] };
    }
    titleCounts[title].count++;
    if (startTime) titleCounts[title].times.push(startTime);
    if (day) titleCounts[title].days.add(day);
    titleCounts[title].durations.push(duration);
    titleCounts[title].attendees.push(attendeeCount);

    if (event.recurrenceRule) {
      routines.push({
        title,
        time: startTime,
        frequency: event.recurrenceRule.frequency || 'weekly',
        days: day ? [day] : [],
        duration_minutes: duration,
        attendees: attendeeCount,
        routine_type: categorizeEvent(title),
        import_source: 'auto',
      });
    }
  }

  for (const [title, data] of Object.entries(titleCounts)) {
    if (data.count >= 2) {
      const modeTime = mode(data.times);
      const freq = data.count >= 5 ? 'daily' : data.count >= 2 ? 'weekly' : 'monthly';
      patterns.push({
        pattern_type: 'recurring_event',
        description: `${title} (${data.count} occurrences)`,
        time: modeTime,
        frequency: freq,
        days: Array.from(data.days),
        confidence: Math.min(0.5 + data.count * 0.1, 0.95),
      });
    }
  }

  const allTimes = events
    .filter(e => e.startDate)
    .map(e => extractHour(e.startDate!))
    .filter(h => h >= 0);

  if (allTimes.length >= 5) {
    const sorted = [...allTimes].sort((a, b) => a - b);
    const start = sorted[Math.floor(sorted.length * 0.1)];
    const end = sorted[Math.floor(sorted.length * 0.9)];
    patterns.push({
      pattern_type: 'working_hours',
      description: `Typical working hours: ${start}:00 - ${end}:00`,
      time: `${start}:00-${end}:00`,
      frequency: 'daily',
      days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
      confidence: 0.8,
    });
  }

  return { routines, patterns };
}

function extractTime(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  } catch { return ''; }
}

function extractDay(dateStr: string): string {
  try {
    return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][new Date(dateStr).getDay()];
  } catch { return ''; }
}

function extractHour(dateStr: string): number {
  try { return new Date(dateStr).getHours(); } catch { return -1; }
}

function calcDuration(start?: string, end?: string): number {
  if (!start || !end) return 30;
  try {
    return Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60000);
  } catch { return 30; }
}

function categorizeEvent(title: string): string {
  const t = title.toLowerCase();
  if (['standup', 'sync', 'check-in', 'huddle'].some(k => t.includes(k))) return 'standup';
  if (['1:1', '1-on-1', 'one on one'].some(k => t.includes(k))) return '1on1';
  if (['planning', 'sprint', 'retro'].some(k => t.includes(k))) return 'planning';
  if (['review', 'demo'].some(k => t.includes(k))) return 'review';
  if (['lunch', 'break', 'gym', 'workout'].some(k => t.includes(k))) return 'personal';
  return 'meeting';
}

function mode(arr: string[]): string {
  if (!arr.length) return '';
  const counts: Record<string, number> = {};
  for (const v of arr) counts[v] = (counts[v] || 0) + 1;
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
}
