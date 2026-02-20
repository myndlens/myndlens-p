/**
 * Notification Manager — expo-notifications wrapper.
 *
 * Handles permission requests, channel setup, and local notification dispatch.
 * Called from settings when the user enables 'Proactive' mode, and from the
 * WS pipeline when a mandate completes.
 */

import { Platform } from 'react-native';

// Dynamic require — graceful if expo-notifications not installed in dev build
let Notifications: any = null;
try {
  Notifications = require('expo-notifications');
} catch {
  console.log('[Notifications] expo-notifications not available in this build');
}

export type NotificationPermissionStatus = 'granted' | 'denied' | 'undetermined';

/**
 * Request notification permission from the OS.
 * Returns the resulting status.
 */
export async function requestNotificationPermission(): Promise<NotificationPermissionStatus> {
  if (!Notifications) return 'undetermined';
  try {
    const { status: existing } = await Notifications.getPermissionsAsync();
    if (existing === 'granted') return 'granted';

    const { status } = await Notifications.requestPermissionsAsync({
      ios: {
        allowAlert: true,
        allowBadge: true,
        allowSound: true,
      },
    });
    return status as NotificationPermissionStatus;
  } catch (err) {
    console.log('[Notifications] Permission request failed:', err);
    return 'undetermined';
  }
}

/**
 * Check current notification permission status without prompting.
 */
export async function getNotificationPermissionStatus(): Promise<NotificationPermissionStatus> {
  if (!Notifications) return 'undetermined';
  try {
    const { status } = await Notifications.getPermissionsAsync();
    return status as NotificationPermissionStatus;
  } catch {
    return 'undetermined';
  }
}

/**
 * Configure notification handler — called once at app startup.
 * Controls how notifications appear when the app is foregrounded.
 */
export function setupNotificationHandler(): void {
  if (!Notifications) return;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
}

/**
 * Set up Android notification channel for mandate updates.
 * No-op on iOS.
 */
export async function setupAndroidChannels(): Promise<void> {
  if (!Notifications || Platform.OS !== 'android') return;
  try {
    await Notifications.setNotificationChannelAsync('mandate_updates', {
      name: 'Mandate Updates',
      importance: Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#6C5CE7',
    });
    await Notifications.setNotificationChannelAsync('alerts', {
      name: 'Alerts',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 500],
      lightColor: '#E74C3C',
    });
  } catch (err) {
    console.log('[Notifications] Channel setup failed:', err);
  }
}

/**
 * Send a local notification immediately.
 */
export async function sendLocalNotification(
  title: string,
  body: string,
  channel: 'mandate_updates' | 'alerts' = 'mandate_updates',
  data?: Record<string, unknown>,
): Promise<void> {
  if (!Notifications) return;
  try {
    const status = await getNotificationPermissionStatus();
    if (status !== 'granted') return;

    await Notifications.scheduleNotificationAsync({
      content: {
        title,
        body,
        data: data ?? {},
        ...(Platform.OS === 'android' && { channelId: channel }),
      },
      trigger: null, // fire immediately
    });
  } catch (err) {
    console.log('[Notifications] Send failed:', err);
  }
}

/**
 * Send a mandate completion notification.
 * Called from the WS client when a pipeline_stage COMPLETED event arrives.
 */
export async function notifyMandateComplete(summary: string): Promise<void> {
  await sendLocalNotification('Done', summary, 'mandate_updates');
}

/**
 * Send a mandate blocked/error notification.
 */
export async function notifyMandateBlocked(reason: string): Promise<void> {
  await sendLocalNotification('Action blocked', reason, 'alerts');
}
