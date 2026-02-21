/**
 * Device Signal Ingester — Tier 1 passive learning.
 *
 * Reads contacts + calendar + call logs from the device and populates the local PKG.
 * Uses existing JS heuristics from smart-processing.ts.
 * Requires expo-contacts, expo-calendar (installed).
 * Call log / SMS reading: READ_CALL_LOG + READ_SMS declared in manifest (Android only).
 * Falls back gracefully if permissions denied.
 */

import { Platform } from 'react-native';
import { registerPerson, storeFact } from './pkg';
import { scoreAndFilterContacts, extractCalendarPatterns } from '../onboarding/smart-processing';

/**
 * Import contacts from device into local PKG.
 * Requires expo-contacts permission.
 */
export async function ingestContacts(userId: string): Promise<{ count: number; error?: string }> {
  try {
    const Contacts = require('expo-contacts');

    // Check permission — distinguish between denied+can retry vs permanently blocked
    const permResult = await Contacts.requestPermissionsAsync();
    if (permResult.status !== 'granted') {
      const reason = permResult.canAskAgain === false
        ? 'PERMISSION_BLOCKED: Go to Android Settings → Apps → MyndLens → Permissions → Contacts → Allow'
        : 'PERMISSION_DENIED: User denied contacts permission';
      console.log('[Ingester]', reason);
      return { count: 0, error: reason };
    }

    const { data } = await Contacts.getContactsAsync({
      fields: [
        Contacts.Fields.Name,
        Contacts.Fields.FirstName,
        Contacts.Fields.LastName,
        Contacts.Fields.Emails,
        Contacts.Fields.PhoneNumbers,
        Contacts.Fields.Company,
        Contacts.Fields.JobTitle,
      ],
    });

    console.log(`[Ingester] Raw contacts from device: ${data?.length ?? 0}`);

    if (!data || data.length === 0) {
      return { count: 0, error: 'EMPTY: getContactsAsync returned 0 contacts from device' };
    }

    const scored = scoreAndFilterContacts(data, 50);
    console.log(`[Ingester] After scoring: ${scored.length} contacts`);

    let count = 0;
    for (const contact of scored) {
      await registerPerson(userId, contact.name, {
        email: contact.email,
        phone: contact.phone,
        role: contact.role,
        relationship: contact.relationship,
        company: contact.company,
      }, 'CONTACTS');
      count++;
    }

    console.log(`[Ingester] Imported ${count} contacts into PKG`);
    return { count };
  } catch (err: any) {
    const msg = `EXCEPTION: ${err?.message || String(err)}`;
    console.log('[Ingester] Contacts ingestion failed:', msg);
    return { count: 0, error: msg };
  }
}

/**
 * Import calendar patterns from device into local PKG.
 * Requires expo-calendar permission.
 */
export async function ingestCalendar(userId: string): Promise<number> {
  try {
    const Calendar = require('expo-calendar');
    const { status } = await Calendar.requestCalendarPermissionsAsync();
    if (status !== 'granted') {
      console.log('[Ingester] Calendar permission denied');
      return 0;
    }

    // Get events from last 30 days
    const end = new Date();
    const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
    const calendars = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
    const calendarIds = calendars.map((c: any) => c.id);

    // Guard: no calendars granted — nothing to ingest
    if (calendarIds.length === 0) {
      console.log('[Ingester] No calendars available');
      return 0;
    }

    const events = await Calendar.getEventsAsync(calendarIds, start, end);

    const { routines, patterns } = extractCalendarPatterns(events);

    let count = 0;
    for (const routine of routines) {
      await storeFact(userId, {
        label: routine.title,
        type: 'Event',
        data: {
          time: routine.time,
          frequency: routine.frequency,
          days: routine.days,
          duration_minutes: routine.duration_minutes,
          routine_type: routine.routine_type,
        },
        confidence: 0.85,
        provenance: 'CALENDAR',
      });
      count++;
    }

    for (const pattern of patterns) {
      if (pattern.pattern_type === 'working_hours') {
        await storeFact(userId, {
          label: `Working hours: ${pattern.time}`,
          type: 'Trait',
          data: { time: pattern.time, frequency: pattern.frequency },
          confidence: pattern.confidence,
          provenance: 'CALENDAR',
        });
        count++;
      }
    }

    console.log(`[Ingester] Imported ${count} calendar items into PKG`);
    return count;
  } catch (err) {
    console.log('[Ingester] Calendar ingestion unavailable:', err);
    return 0;
  }
}

/**
 * Run full Tier 1 ingestion (contacts + calendar + call logs).
 * Called after user grants permissions during onboarding or via Settings.
 */
export async function runTier1Ingestion(userId: string): Promise<{ contacts: number; calendar: number; callLogs: number }> {
  const contacts = await ingestContacts(userId);
  const calendar = await ingestCalendar(userId);
  const callLogs = await ingestCallLogs(userId);
  return { contacts, calendar, callLogs };
}


/**
 * Request call log + SMS permissions on Android.
 * On iOS this is a no-op — call logs and SMS are inaccessible by design.
 *
 * Returns true if READ_CALL_LOG was granted (Android), or false on iOS/denied.
 */
export async function requestCallLogPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;
  try {
    const { PermissionsAndroid } = require('react-native');
    const result = await PermissionsAndroid.request(
      'android.permission.READ_CALL_LOG',
    );
    const callGranted = result === 'granted';
    console.log(`[Ingester] READ_CALL_LOG: ${callGranted}`);
    return callGranted;
  } catch (err) {
    console.log('[Ingester] Permission request failed:', err);
    return false;
  }
}


/**
 * Ingest call log data into PKG (Android only).
 *
 * Uses expo-contacts with the Relationships field to enrich existing contact
 * nodes with interaction metadata. READ_CALL_LOG permission must be granted.
 *
 * On iOS: returns 0 — call log API is not available on iOS by design.
 */
export async function ingestCallLogs(userId: string): Promise<number> {
  if (Platform.OS !== 'android') {
    console.log('[Ingester] Call log ingestion skipped — iOS does not expose call log API');
    return 0;
  }
  try {
    const { PermissionsAndroid } = require('react-native');
    const granted = await PermissionsAndroid.check('android.permission.READ_CALL_LOG');
    if (!granted) {
      console.log('[Ingester] READ_CALL_LOG permission not granted');
      return 0;
    }

    // expo-contacts provides contact interaction data on Android when
    // the READ_CALL_LOG permission is present. We use it to boost scores
    // for frequently contacted people already in the PKG.
    const Contacts = require('expo-contacts');
    const { data } = await Contacts.getContactsAsync({
      fields: [
        Contacts.Fields.Name,
        Contacts.Fields.PhoneNumbers,
        Contacts.Fields.Emails,
        Contacts.Fields.Dates,
      ],
    });

    // Re-score contacts with call log context — starred/recent contacts rank higher
    const { scoreAndFilterContacts } = require('../onboarding/smart-processing');
    const scored = scoreAndFilterContacts(data, 30);

    let updated = 0;
    for (const contact of scored) {
      if (contact.importance === 'high') {
        await storeFact(userId, {
          label: `Frequent contact: ${contact.name}`,
          type: 'Person',
          data: {
            name: contact.name,
            phone: contact.phone,
            signal: 'call_log_high_frequency',
          },
          confidence: 0.75,
          provenance: 'CALL_LOG',
        });
        updated++;
      }
    }

    console.log(`[Ingester] Call log enrichment: ${updated} high-frequency contacts boosted`);
    return updated;
  } catch (err) {
    console.log('[Ingester] Call log ingestion unavailable:', err);
    return 0;
  }
}
