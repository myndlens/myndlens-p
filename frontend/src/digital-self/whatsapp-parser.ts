/**
 * WhatsApp Chat Export Parser
 *
 * Parses the standard WhatsApp text export format produced by:
 *   WhatsApp → Settings → Chats → Export Chat → Without Media
 *
 * Export format (varies slightly by locale/version):
 *   [09/06/2023, 3:45 PM] Alice Smith: Hey, are you free tomorrow?
 *   [09/06/2023, 3:47:12 PM] You: Yes what time?
 *   09/06/2023, 3:45 PM - Alice Smith: Hey (older format, no brackets)
 *
 * Returns scored contacts ready for Digital Self PKG import.
 */

export interface WAContact {
  name: string;
  /** Messages sent by this contact (received by user) */
  messagesReceived: number;
  /** Messages sent by user to this contact */
  messagesSent: number;
  /** Total messages in the conversation */
  total: number;
  firstMessageAt: Date;
  lastMessageAt: Date;
  /** Days between first and last message */
  relationshipAgedays: number;
  /** Avg messages per week (both sides) */
  avgPerWeek: number;
  /** PKG importance score (0-20) */
  score: number;
  importance: 'high' | 'medium' | 'low';
}

export interface WAParseResult {
  contacts: WAContact[];
  totalMessages: number;
  exportDateRange: { from: Date; to: Date } | null;
  selfName: string | null;    // The user's own name as it appears in the export
  parseErrors: number;
}

// ── Line parsing ──────────────────────────────────────────────────────────────

// Pattern 1 (most common): [dd/mm/yyyy, hh:mm:ss AM] Name: message
// Pattern 2:               [mm/dd/yyyy, hh:mm AM/PM] Name: message
// Pattern 3 (no brackets): dd/mm/yyyy, hh:mm - Name: message
const LINE_PATTERNS = [
  /^\[(\d{1,2}\/\d{1,2}\/\d{2,4}),?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\]\s+(.+?):\s+(.+)$/i,
  /^(\d{1,2}\/\d{1,2}\/\d{2,4}),?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\s+-\s+(.+?):\s+(.+)$/i,
];

// System messages to skip (not real messages)
const SYSTEM_MSG_PATTERNS = [
  /messages and calls are end-to-end encrypted/i,
  /\+\d+ added/i,
  /\+\d+ left/i,
  /\+\d+ was added/i,
  /changed the subject/i,
  /changed this group/i,
  /changed the group/i,
  /you created group/i,
  /\u200e/,  // left-to-right mark (often in system msgs)
];

function isSystemMessage(text: string): boolean {
  return SYSTEM_MSG_PATTERNS.some(p => p.test(text));
}

// ── Self-name detection ───────────────────────────────────────────────────────

const SELF_NAMES = new Set(['you', 'me', 'i', 'myself']);

function detectSelfName(nameCounts: Map<string, number>): string | null {
  // The export often uses the user's saved name or "You"
  for (const [name] of nameCounts) {
    if (SELF_NAMES.has(name.toLowerCase())) return name;
  }
  return null;
}

// ── Scoring ───────────────────────────────────────────────────────────────────

function scoreContact(c: Omit<WAContact, 'score' | 'importance'>): { score: number; importance: 'high' | 'medium' | 'low' } {
  let score = 0;

  // Message volume (total in both directions)
  if (c.total >= 500)      score += 5;
  else if (c.total >= 100) score += 4;
  else if (c.total >= 30)  score += 3;
  else if (c.total >= 10)  score += 2;
  else if (c.total >= 3)   score += 1;

  // Recency (days since last message)
  const daysSinceLastMsg = (Date.now() - c.lastMessageAt.getTime()) / 86_400_000;
  if (daysSinceLastMsg < 7)   score += 5;
  else if (daysSinceLastMsg < 30)  score += 4;
  else if (daysSinceLastMsg < 90)  score += 3;
  else if (daysSinceLastMsg < 180) score += 1;

  // Relationship age (months)
  const months = c.relationshipAgedays / 30;
  if (months >= 24) score += 3;
  else if (months >= 6) score += 2;
  else if (months >= 1) score += 1;

  // Bidirectional conversation (both sides active)
  if (c.messagesReceived > 0 && c.messagesSent > 0) {
    const ratio = Math.min(c.messagesReceived, c.messagesSent) /
                  Math.max(c.messagesReceived, c.messagesSent);
    if (ratio > 0.5) score += 3;  // balanced conversation
    else if (ratio > 0.2) score += 1;
  }

  // Frequency
  if (c.avgPerWeek >= 10)    score += 3;
  else if (c.avgPerWeek >= 3) score += 2;
  else if (c.avgPerWeek >= 1) score += 1;

  const importance: 'high' | 'medium' | 'low' =
    score >= 12 ? 'high' : score >= 6 ? 'medium' : 'low';

  return { score, importance };
}

// ── Main parser ───────────────────────────────────────────────────────────────

export function parseWhatsAppExport(text: string): WAParseResult {
  const lines = text.split(/\r?\n/);

  // name → { received, sent, dates[] }
  const contactData = new Map<string, {
    received: number;
    sent: number;
    dates: Date[];
    firstAt: Date;
    lastAt: Date;
  }>();

  const nameCounts = new Map<string, number>();
  let parseErrors = 0;
  let selfName: string | null = null;
  let minDate: Date | null = null;
  let maxDate: Date | null = null;
  let totalMessages = 0;
  let currentSender = '';

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    let matched = false;
    for (const pattern of LINE_PATTERNS) {
      const m = trimmed.match(pattern);
      if (m) {
        const [, , name, message] = m;
        if (!name || !message) break;
        if (isSystemMessage(message)) break;

        currentSender = name.trim();
        nameCounts.set(currentSender, (nameCounts.get(currentSender) || 0) + 1);

        // Parse date from the matched line (reuse pattern group 1 for date)
        let msgDate: Date | null = null;
        try {
          const dateStr = m[1];
          const parts = dateStr.split('/');
          if (parts.length === 3) {
            let [a, b, yr] = parts.map(Number);
            if (yr < 100) yr += 2000;
            // Try dd/mm/yyyy first, then mm/dd/yyyy
            const d1 = new Date(yr, b - 1, a);
            const d2 = new Date(yr, a - 1, b);
            msgDate = (d1.getMonth() === b - 1) ? d1 : d2;
          }
        } catch { parseErrors++; }

        if (!contactData.has(currentSender)) {
          contactData.set(currentSender, {
            received: 0, sent: 0, dates: [],
            firstAt: msgDate || new Date(),
            lastAt: msgDate || new Date(),
          });
        }

        const cd = contactData.get(currentSender)!;
        cd.received++;  // will fix sent vs received after self-name detected
        if (msgDate) {
          cd.dates.push(msgDate);
          if (msgDate > cd.lastAt) cd.lastAt = msgDate;
          if (!minDate || msgDate < minDate) minDate = msgDate;
          if (!maxDate || msgDate > maxDate) maxDate = msgDate;
        }
        totalMessages++;
        matched = true;
        break;
      }
    }
    // continuation line (no timestamp — belongs to current sender, ignored for stats)
  }

  // Detect self name (the user's own display name in the export)
  selfName = detectSelfName(nameCounts);

  // Swap sent/received for contacts (self messages are "sent" to others)
  // In a single-chat export: there are only 2 participants (self + contact)
  // In a group export: many participants
  if (selfName) {
    const selfData = contactData.get(selfName);
    const selfSent = selfData?.received || 0;  // "received" was counted for self
    contactData.delete(selfName);

    // For single-chat exports: 1 other contact — assign sent count
    if (contactData.size === 1) {
      const [, other] = [...contactData.entries()][0];
      other.sent = selfSent;
      other.received = other.received;  // already correct
    }
  }

  // Build scored contacts
  const contacts: WAContact[] = [];

  for (const [name, cd] of contactData.entries()) {
    if (SELF_NAMES.has(name.toLowerCase())) continue;
    const total = cd.received + cd.sent;
    if (total < 2) continue;  // skip one-off contacts

    const agedays = Math.max(1,
      (cd.lastAt.getTime() - cd.firstAt.getTime()) / 86_400_000
    );
    const weeks = Math.max(1, agedays / 7);
    const avgPerWeek = total / weeks;

    const partial = {
      name,
      messagesReceived: cd.received,
      messagesSent: cd.sent,
      total,
      firstMessageAt: cd.firstAt,
      lastMessageAt: cd.lastAt,
      relationshipAgedays: agedays,
      avgPerWeek,
    };

    const { score, importance } = scoreContact(partial);
    contacts.push({ ...partial, score, importance });
  }

  // Sort by score descending
  contacts.sort((a, b) => b.score - a.score);

  return {
    contacts,
    totalMessages,
    exportDateRange: minDate && maxDate ? { from: minDate, to: maxDate } : null,
    selfName,
    parseErrors,
  };
}
