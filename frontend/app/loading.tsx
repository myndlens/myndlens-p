import React, { useEffect, useState, useRef } from 'react';
import { View, Text, StyleSheet, Animated, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { wsClient } from '../src/ws/client';
import { useSessionStore } from '../src/state/session-store';

const STATUS_MESSAGES = [
  'Securing your workspace\u2026',
  'Preparing your assistant\u2026',
  'Almost ready\u2026',
];

/**
 * Loading / Activation — masks all backend complexity.
 * Validates SSO, connects WS, starts heartbeat.
 *
 * Auth clearing rules:
 *   HARD failures (auth_fail, Device ID mismatch) → clearAuth + /login (re-pair)
 *   SOFT failures (network, timeout, backend down) → show retry UI, NEVER wipe token
 */
export default function LoadingScreen() {
  const router = useRouter();
  const { setConnectionStatus } = useSessionStore();
  const [statusIdx, setStatusIdx] = useState(0);
  const [softError, setSoftError] = useState<string | null>(null);
  const fadeAnim = useRef(new Animated.Value(1)).current;
  const retryCount = useRef(0);
  const MAX_RETRIES = 8;
  const activating = useRef(false);

  useEffect(() => {
    const interval = setInterval(() => {
      if (softError) return; // stop rotating when showing error
      Animated.timing(fadeAnim, { toValue: 0, duration: 200, useNativeDriver: true }).start(() => {
        setStatusIdx((i) => (i + 1) % STATUS_MESSAGES.length);
        Animated.timing(fadeAnim, { toValue: 1, duration: 200, useNativeDriver: true }).start();
      });
    }, 2000);

    activate();
    return () => clearInterval(interval);
  }, []);

  async function activate() {
    if (activating.current) return; // prevent concurrent activate() calls
    activating.current = true;
    setSoftError(null);
    try {
      setConnectionStatus('connecting');
      await wsClient.connect();
      setConnectionStatus('authenticated');

      // Request notification permission once after first successful connect.
      // Uses a storage flag so it only fires on first pairing, not every launch.
      try {
        const { getItem, setItem: saveItem } = require('../src/utils/storage');
        const notifAsked = await getItem('myndlens_notif_permission_asked');
        if (!notifAsked) {
          const { requestNotificationPermission, setupAndroidChannels } = require('../src/notifications/manager');
          await requestNotificationPermission();
          await setupAndroidChannels();
          await saveItem('myndlens_notif_permission_asked', 'true');
        }
      } catch { /* non-critical — never block the main flow */ }

      // Sync stored user_id to match wsClient.userId (JWT sub).
      // login.tsx stores tenant_id, but WS auth sets userId from JWT sub — they differ.
      // PKG is keyed by this userId, so they must match or DS check always sees empty PKG.
      if (wsClient.userId) {
        const { setItem: saveItem2, getItem: readItem } = require('../src/utils/storage');
        const storedUid = await readItem('myndlens_user_id');
        if (storedUid !== wsClient.userId) {
          await saveItem2('myndlens_user_id', wsClient.userId);
        }
      }

      // Send Digital Self context immediately after auth
      try {
        const userId = wsClient.userId ?? '';
        if (userId) {
          const { buildContextCapsule } = require('../src/digital-self');
          const capsule = await buildContextCapsule(userId, '');
          if (capsule.summary) {
            wsClient.send('context_sync' as any, { summary: capsule.summary });
          }
        }
      } catch { /* context sync is best-effort — never blocks auth */ }

      // Resume any in-progress WhatsApp DS sync job (started during setup, may still be running)
      // Runs in background — does NOT block loading or navigation.
      try {
        const { getItem, setItem } = require('../src/utils/storage');
        const jobId   = await getItem('whatsapp_sync_job_id');
        const alreadyDone = await getItem('whatsapp_ds_imported');
        if (jobId && !alreadyDone) {
          const obegeeUrl = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';
          const token    = await getItem('myndlens_auth_token');
          const tenantId = await getItem('myndlens_tenant_id');
          const userId2  = wsClient.userId ?? '';

          if (token && tenantId && userId2) {
            // Poll every 30s until done, max 2 hours
            const maxTries = 240;
            let   tries    = 0;

            const pollWA = async () => {
              tries++;
              if (tries > maxTries) return;
              try {
                const r = await fetch(`${obegeeUrl}/api/whatsapp/sync-progress/${tenantId}`, {
                  headers: { 'Authorization': `Bearer ${token}` },
                });
                if (!r.ok) return;
                const d = await r.json();

                if (d.status === 'done' && d.contacts?.length > 0) {
                  // Import completed contacts into PKG
                  const { registerPerson } = require('../src/digital-self/pkg');
                  for (const c of d.contacts.filter((x: any) => x.importance !== 'low').slice(0, 200)) {
                    await registerPerson(userId2, {
                      name: c.name, phone: c.phone || '', company: '', role: '',
                      relationship: 'personal', importance: c.importance,
                      preferred_channel: 'whatsapp', score: c.score, import_source: 'whatsapp_live',
                    });
                  }
                  await setItem('whatsapp_ds_imported', 'true');
                  // Re-sync DS capsule to backend now that it's enriched
                  const { buildContextCapsule } = require('../src/digital-self');
                  const capsule2 = await buildContextCapsule(userId2, '');
                  if (capsule2.summary) {
                    wsClient.send('context_sync' as any, { summary: capsule2.summary });
                  }
                  console.log(`[WA-BG] Imported ${d.contacts.length} WhatsApp contacts into PKG`);
                } else if (d.status === 'running') {
                  // Still running — poll again in 30s
                  setTimeout(pollWA, 30_000);
                }
              } catch { /* non-critical */ }
            };

            // Start polling after 10s (give setup wizard time to complete)
            setTimeout(pollWA, 10_000);
          }
        }
      } catch { /* non-critical — never block the main flow */ }

      const { getItem } = require('../src/utils/storage');
      const setupDone = await getItem('setup_wizard_complete');
      const dsStatus = await getItem('myndlens_ds_setup_done');

      if (setupDone === 'true' && dsStatus !== 'empty') {
        router.replace('/talk');
      } else {
        // First launch OR DS was empty last run — go to setup (lands on Step 9)
        router.replace('/setup');
      }
    } catch (err: any) {
      const msg = err?.message || '';

      // SUBSCRIPTION issue — soft block screen
      if (msg.includes('SUSPENDED')) {
        router.replace('/softblock');
        return;
      }

      // HARD auth failure — token genuinely rejected by server (wrong device, revoked, mismatched)
      // Only in this case do we clear the token and force re-pairing.
      if (
        msg.includes('auth_fail') ||
        msg.includes('AUTH_ERROR') ||
        msg.includes('No auth token') ||
        msg.includes('Device ID mismatch')
      ) {
        const { clearAuth } = require('../src/ws/auth');
        await clearAuth();
        router.replace('/login');
        return;
      }

      // SOFT failure — network error, timeout, backend temporarily unavailable.
      // Token is still valid. Retry with backoff. NEVER wipe the token.
      setConnectionStatus('disconnected');
      retryCount.current += 1;

      if (retryCount.current < MAX_RETRIES) {
        // Auto-retry silently
        activating.current = false; // release lock before retry
        setTimeout(() => activate(), 3000);
      } else {
        // Give up auto-retrying — show manual retry UI.
        // Token is preserved. User taps "Try Again" to re-attempt.
        activating.current = false;
        setSoftError('Could not connect. Check your internet connection.');
      }
    }
  }

  // Soft error state — show retry without losing the pairing
  if (softError) {
    return (
      <View style={styles.container}>
        <View style={styles.spinnerBox}>
          <Text style={styles.errorText}>{softError}</Text>
          <TouchableOpacity
            style={styles.retryBtn}
            onPress={() => {
              retryCount.current = 0;
              activate();
            }}
          >
            <Text style={styles.retryText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.spinnerBox}>
        <View style={styles.spinner} />
        <Animated.Text style={[styles.status, { opacity: fadeAnim }]}>
          {STATUS_MESSAGES[statusIdx]}
        </Animated.Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0F',
    alignItems: 'center',
    justifyContent: 'center',
  },
  spinnerBox: {
    alignItems: 'center',
    gap: 24,
  },
  spinner: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 3,
    borderColor: '#6C5CE733',
    borderTopColor: '#6C5CE7',
  },
  status: {
    fontSize: 16,
    color: '#8B8B9E',
  },
  errorText: {
    fontSize: 15,
    color: '#8B8B9E',
    textAlign: 'center',
    paddingHorizontal: 32,
    lineHeight: 22,
  },
  retryBtn: {
    backgroundColor: '#6C5CE7',
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 40,
    marginTop: 8,
  },
  retryText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
  },
});
