/**
 * User Settings Preferences — local storage for all Category A settings.
 *
 * All preferences are stored on-device in AsyncStorage.
 * Nothing here requires a network call.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

const PREFS_KEY = 'myndlens_user_settings_v1';

export type DelegationMode = 'advisory' | 'assisted' | 'delegated';
export type NotificationMode = 'proactive' | 'silent' | 'escalation';
export type VoiceVerbosity = 'low' | 'medium' | 'high';

export interface DataSources {
  contacts: boolean;
  calendar: boolean;
  email_gmail: boolean;
  email_outlook: boolean;
  email_imap: boolean;
  messaging_whatsapp: boolean;
  messaging_imessage: boolean;
  messaging_telegram: boolean;
  social_linkedin: boolean;
  social_other: boolean;
  financial_payment: boolean;
  financial_corporate: boolean;
}

export interface TravelScope {
  flights: boolean;
  hotels: boolean;
  ground: boolean;
}

export interface AutoActionPolicy {
  low_risk: boolean;    // default ON
  medium_risk: boolean; // default OFF (confirm once per trip)
  high_risk: boolean;   // default OFF (always ask)
}

export interface UserSettings {
  // Section 1: Travel Monitoring
  travel_monitoring_enabled: boolean;
  travel_scope: TravelScope;
  auto_action: AutoActionPolicy;

  // Section 2: Digital Self Data Sources
  data_sources: DataSources;
  ds_paused: boolean;

  // Section 3: Automation & Consent
  delegation_mode: DelegationMode;

  // Section 4: Privacy & Storage
  data_residency: 'on_device' | 'cloud_backup';

  // Section 5: Notifications & Voice
  notification_mode: NotificationMode;
  voice_verbosity: VoiceVerbosity;
}

export const DEFAULT_SETTINGS: UserSettings = {
  travel_monitoring_enabled: false,
  travel_scope: { flights: true, hotels: true, ground: true },
  auto_action: { low_risk: true, medium_risk: false, high_risk: false },
  data_sources: {
    contacts: false,
    calendar: false,
    email_gmail: false,
    email_outlook: false,
    email_imap: false,
    messaging_whatsapp: false,
    messaging_imessage: false,
    messaging_telegram: false,
    social_linkedin: false,
    social_other: false,
    financial_payment: false,
    financial_corporate: false,
  },
  ds_paused: false,
  delegation_mode: 'assisted',
  data_residency: 'on_device',
  notification_mode: 'proactive',
  voice_verbosity: 'medium',
};

export async function loadSettings(): Promise<UserSettings> {
  try {
    const raw = await AsyncStorage.getItem(PREFS_KEY);
    if (raw) {
      const stored = JSON.parse(raw) as Partial<UserSettings>;
      // Deep merge nested objects to preserve defaults not present in stored data
      return {
        ...DEFAULT_SETTINGS,
        ...stored,
        travel_scope: { ...DEFAULT_SETTINGS.travel_scope, ...(stored.travel_scope ?? {}) },
        auto_action: { ...DEFAULT_SETTINGS.auto_action, ...(stored.auto_action ?? {}) },
        data_sources: { ...DEFAULT_SETTINGS.data_sources, ...(stored.data_sources ?? {}) },
      };
    }
  } catch { /* return defaults */ }
  return { ...DEFAULT_SETTINGS };
}

export async function saveSettings(settings: UserSettings): Promise<void> {
  await AsyncStorage.setItem(PREFS_KEY, JSON.stringify(settings));
}

export async function updateSetting<K extends keyof UserSettings>(
  key: K,
  value: UserSettings[K],
): Promise<void> {
  const current = await loadSettings();
  current[key] = value;
  await saveSettings(current);
}
