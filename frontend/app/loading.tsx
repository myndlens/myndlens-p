import React, { useEffect, useState, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
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
 * Human-only status text.
 */
export default function LoadingScreen() {
  const router = useRouter();
  const { setConnectionStatus } = useSessionStore();
  const [statusIdx, setStatusIdx] = useState(0);
  const fadeAnim = useRef(new Animated.Value(1)).current;
  const retryCount = useRef(0);
  const MAX_RETRIES = 8;

  useEffect(() => {
    // Rotate status text
    const interval = setInterval(() => {
      Animated.timing(fadeAnim, { toValue: 0, duration: 200, useNativeDriver: true }).start(() => {
        setStatusIdx((i) => (i + 1) % STATUS_MESSAGES.length);
        Animated.timing(fadeAnim, { toValue: 1, duration: 200, useNativeDriver: true }).start();
      });
    }, 2000);

    activate();
    return () => clearInterval(interval);
  }, []);

  async function activate() {
    try {
      setConnectionStatus('connecting');
      await wsClient.connect();
      setConnectionStatus('authenticated');
      setSessionId(wsClient.currentSessionId);
      setPresenceOk(true);

      // Check if first-time setup is needed
      const { getItem } = require('../src/utils/storage');
      const setupDone = await getItem('setup_wizard_complete');
      if (setupDone === 'true') {
        router.replace('/talk');
      } else {
        router.replace('/setup');
      }
    } catch (err: any) {
      const msg = err?.message || '';

      // SUBSCRIPTION issue — soft block screen
      if (msg.includes('SUSPENDED')) {
        router.replace('/softblock');
        return;
      }

      // HARD auth failure — token is genuinely invalid, clear it and re-pair
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

      // SOFT failure — network error, timeout, backend unavailable
      // Token is still valid. Retry with backoff up to MAX_RETRIES.
      setConnectionStatus('disconnected');
      retryCount.current += 1;
      if (retryCount.current >= MAX_RETRIES) {
        // Give up — send to login so user can re-pair
        const { clearAuth } = require('../src/ws/auth');
        await clearAuth();
        router.replace('/login');
        return;
      }
      setTimeout(() => activate(), 3000);
    }
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
});
