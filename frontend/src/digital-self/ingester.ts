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
export async function ingestContacts(userId: string): Promise<number> {
  try {
    // Dynamically import expo-contacts (graceful fallback if not installed)
    const Contacts = require('expo-contacts');
    const { status } = await Contacts.requestPermissionsAsync();
    if (status !== 'granted') {
      console.log('[Ingester] Contacts permission denied');
      return 0;
    }

    const { data } = await Contacts.getContactsAsync({
      fields: [
        Contacts.Fields.Name,
        Contacts.Fields.Emails,
        Contacts.Fields.PhoneNumbers,
        Contacts.Fields.Company,
        Contacts.Fields.JobTitle,
      ],
    });

    // Score and filter using existing heuristics
    const scored = scoreAndFilterContacts(data, 50);

    let count = 0;
    for (const contact of scored) {
      await registerPerson(
        userId,
        contact.name,
        {
          email: contact.email,
          phone: contact.phone,
          role: contact.role,
          relationship: contact.relationship,
          company: contact.company,
        },
        'CONTACTS',
      );
      count++;
    }

    console.log(`[Ingester] Imported ${count} contacts into PKG`);
    return count;
  } catch (err) {
    console.log('[Ingester] Contacts ingestion unavailable:', err);
    return 0;
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
 * Run full Tier 1 ingestion (contacts + calendar).
 * Called after user grants permissions during onboarding.
 */
export async function runTier1Ingestion(userId: string): Promise<{ contacts: number; calendar: number }> {
  const contacts = await ingestContacts(userId);
  const calendar = await ingestCalendar(userId);
  return { contacts, calendar };
}
