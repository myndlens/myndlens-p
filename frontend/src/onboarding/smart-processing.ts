/**
 * Smart Processing — on-device algorithmic contact scoring and pattern extraction.
 * No LLM required. Runs entirely in JavaScript on the device.
 * 
 * Hybrid approach: heuristics on-device, Gemini fallback on server for complex analysis.
 */

// ---- Contact Scoring ----

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

export function scoreAndFilterContacts(contacts: RawContact[], maxResults: number = 15): ScoredContact[] {
  const scored: ScoredContact[] = [];

  for (const c of contacts) {
    const name = c.name || [c.firstName, c.lastName].filter(Boolean).join(' ');
    if (!name) continue;

    const email = c.emails?.[0]?.email || '';
    const phone = c.phoneNumbers?.[0]?.number || '';
    // Do NOT filter out name-only contacts — they are valid Digital Self nodes.
    // Many Android contacts (WhatsApp sync, SIM imports, Google contacts) return
    // empty phoneNumbers/emails arrays even when numbers exist on the device.
    // A name-only contact is still useful for relationship inference.

    let score = 0;
    if (email && phone) score += 2;
    if (c.emails && c.emails.length > 1) score += 1;
    if (c.phoneNumbers && c.phoneNumbers.length > 1) score += 1;
    if (c.starred) score += 3;
    if (c.company) score += 1;
    if (c.jobTitle) score += 1;

    const relationship = inferRelationship(c);
    const importance = score >= 5 ? 'high' : score >= 2 ? 'medium' : 'low';
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

  // Detect recurring patterns from non-recurrence events appearing 2+ times
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

  // Working hours pattern
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
