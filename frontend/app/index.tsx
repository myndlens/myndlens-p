import React, { useEffect } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { useSessionStore } from '../src/state/session-store';
import { getStoredToken, getStoredUserId } from '../src/ws/auth';

/**
 * Entry screen — checks auth state and redirects.
 * If paired → go to /talk
 * If not paired → go to /pairing
 */
export default function IndexScreen() {
  const router = useRouter();
  const setAuth = useSessionStore((s) => s.setAuth);

  useEffect(() => {
    checkAuthState();
  }, []);

  async function checkAuthState() {
    try {
      const token = await getStoredToken();
      const userId = await getStoredUserId();

      if (token && userId) {
        setAuth(userId, '');
        router.replace('/talk');
      } else {
        router.replace('/login');
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      router.replace('/login');
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.loadingBox}>
        <Text style={styles.logo}>MyndLens</Text>
        <Text style={styles.subtitle}>Sovereign Voice Assistant</Text>
        <ActivityIndicator size="large" color="#6C5CE7" style={styles.spinner} />
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
  loadingBox: {
    alignItems: 'center',
    gap: 16,
  },
  logo: {
    fontSize: 40,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 2,
  },
  subtitle: {
    fontSize: 14,
    color: '#8B8B9E',
    letterSpacing: 1,
  },
  spinner: {
    marginTop: 24,
  },
});
