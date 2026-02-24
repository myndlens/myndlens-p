/**
 * Device Signal Ingester — Tier 1 passive learning.
 *
 * Reads contacts + calendar + call logs from the device and populates the local PKG.
 * Uses existing JS heuristics from smart-processing.ts.
 * Requires expo-contacts, expo-calendar (installed).
 * Call log reading: READ_CALL_LOG declared in manifest (Android only).
 * Falls back gracefully if permissions denied.
 */

import { Platform } from 'react-native';
import { registerPerson, storeFact } from './pkg';
import { scoreAndFilterContacts, extractCalendarPatterns, normalizePhone, CallLogEntry } from '../onboarding/smart-processing';

// ---- Call Log Pre-loading ----

/**
 * Build a phone → {count, lastDate} map from the last 90 days of call history.
 * Used to enrich contact scoring BEFORE the top-200 slice is made.
 *
 * Requires READ_CALL_LOG permission (Android only).
 * Returns an empty Map on iOS or if permission is denied.
 */
async function loadCallLogMap(): Promise<Map<string, CallLogEntry>> {
  const result = new Map<string, CallLogEntry>();

  if (Platform.OS !== 'android') return result;

  try {
    const { PermissionsAndroid } = require('react-native');
    const granted = await PermissionsAndroid.check('android.permission.READ_CALL_LOG');
    if (!granted) {
      console.log('[Ingester] READ_CALL_LOG not granted — scoring without call signals');
      return result;
    }

    const CallLogs = require('react-native-call-log').default;

    // Load calls from last 90 days (call-log entries include dateTime as epoch ms string)
    const ninetyDaysAgo = Date.now() - 90 * 24 * 60 * 60 * 1000;
    const logs: Array<{
      phoneNumber: string;
      dateTime: string; // epoch ms as string
      callType: string;
    }> = await CallLogs.loadAll();

    for (const log of logs) {
      if (!log.phoneNumber) continue;
      const ts = parseInt(log.dateTime, 10);
      if (isNaN(ts) || ts < ninetyDaysAgo) continue;

      const key = normalizePhone(log.phoneNumber);
      if (!key) continue;

      const existing = result.get(key);
      const callDate = new Date(ts);

      if (existing) {
        existing.count++;
        if (callDate > existing.lastDate) existing.lastDate = callDate;
      } else {
        result.set(key, { count: 1, lastDate: callDate });
      }
    }

    console.log(`[Ingester] Call log map: ${result.size} unique numbers in last 90 days`);
  } catch (err) {
    console.log('[Ingester] Call log loading failed (non-fatal):', err);
  }

  return result;
}

// ---- Contacts ----

/**
 * Import contacts from device into local PKG.
 * Pre-loads call log data first so call frequency and recency are part of the ranking.
 */
export async function ingestContacts(userId: string): Promise<{ count: number; error?: string }> {
  try {
    const Contacts = require('expo-contacts');

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
        Contacts.Fields.Image,      // has photo signal (+2)
        Contacts.Fields.Dates,      // birthday/anniversary signal (+1)
      ],
    });

    console.log(`[Ingester] Raw contacts from device: ${data?.length ?? 0}`);

    if (!data || data.length === 0) {
      return { count: 0, error: 'EMPTY: getContactsAsync returned 0 contacts from device' };
    }

    // Pre-load call log data — must happen BEFORE scoring so call signals
    // influence which contacts make the top 200 cut.
    const callLogMap = await loadCallLogMap();
    console.log(`[Ingester] Scoring ${data.length} contacts with ${callLogMap.size} call-log entries`);

    const scored = scoreAndFilterContacts(data, 50, callLogMap);  // top 50 with real interaction signals
    console.log(`[Ingester] After scoring+ranking: ${scored.length} contacts selected`);

    let count = 0;
    for (const contact of scored) {
      // Use same name resolution as scoreAndFilterContacts
      const resolvedName = contact.name;
      if (!resolvedName) continue;
      await registerPerson(userId, resolvedName, {
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

// ---- Calendar ----

export async function ingestCalendar(userId: string): Promise<number> {
  try {
    const Calendar = require('expo-calendar');
    const { status } = await Calendar.requestCalendarPermissionsAsync();
    if (status !== 'granted') {
      console.log('[Ingester] Calendar permission denied');
      return 0;
    }

    const end = new Date();
    const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
    console.log(`[Ingester] Fetching calendar events from ${start.toISOString()} to ${end.toISOString()}`);

    const calendars = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
    console.log(`[Ingester] Found ${calendars.length} calendars on device`);
    const calendarIds = calendars.map((c: any) => c.id);

    if (calendarIds.length === 0) {
      console.log('[Ingester] No calendars available');
      return 0;
    }

    const events = await Calendar.getEventsAsync(calendarIds, start, end);
    console.log(`[Ingester] Fetched ${events.length} raw calendar events`);

    const { routines, patterns } = extractCalendarPatterns(events);
    console.log(`[Ingester] Extracted ${routines.length} routines, ${patterns.length} patterns`);

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

// ---- Tier 1 Runner ----

export async function runTier1Ingestion(userId: string): Promise<{ contacts: number; calendar: number; callLogs: number; contactsError?: string }> {
  const contactsResult = await ingestContacts(userId);
  const calendar = await ingestCalendar(userId);
  const callLogs = await ingestCallLogs(userId);
  return {
    contacts: contactsResult.count,
    calendar,
    callLogs,
    contactsError: contactsResult.error,
  };
}

// ---- Call Log Permission Request ----

export async function requestCallLogPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;
  try {
    const { PermissionsAndroid } = require('react-native');
    const result = await PermissionsAndroid.request('android.permission.READ_CALL_LOG');
    const granted = result === 'granted';
    console.log(`[Ingester] READ_CALL_LOG: ${granted}`);
    return granted;
  } catch (err) {
    console.log('[Ingester] Permission request failed:', err);
    return false;
  }
}

// ---- Call Log Ingestion (metadata enrichment of existing PKG nodes) ----

/**
 * After contacts are already imported, enrich high-frequency contacts with
 * a CALL_LOG provenance signal so the PKG knows these are active relationships.
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

    // Re-use the same call log map
    const callLogMap = await loadCallLogMap();
    if (callLogMap.size === 0) return 0;

    let enriched = 0;
    for (const [phone, data] of callLogMap.entries()) {
      if (data.count >= 5) {
        // Only write enrichment for contacts with meaningful call frequency
        await storeFact(userId, {
          label: `Frequent call contact: ${phone}`,
          type: 'Person',
          data: {
            phone,
            call_count_90d: data.count,
            last_call: data.lastDate.toISOString(),
            signal: 'call_log_high_frequency',
          },
          confidence: 0.75,
          provenance: 'CALL_LOG',
        });
        enriched++;
      }
    }

    console.log(`[Ingester] Call log enrichment: ${enriched} high-frequency numbers recorded`);
    return enriched;
  } catch (err) {
    console.log('[Ingester] Call log ingestion unavailable:', err);
    return 0;
  }
}
