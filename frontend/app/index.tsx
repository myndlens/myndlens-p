import React, { useEffect } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { getStoredToken, getStoredUserId } from '../src/ws/auth';
import { useSessionStore } from '../src/state/session-store';

/**
 * Splash / Boot — brand + fast bootstrap.
 * Auto-advances. No buttons. Silent token check.
 * Failure → Login (no error shown).
 */
export default function SplashScreen() {
  const router = useRouter();
  const setAuth = useSessionStore((s) => s.setAuth);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const token = await getStoredToken();
        const userId = await getStoredUserId();
        if (token && userId) {
          setAuth(userId, '');
          router.replace('/loading');
        } else {
          router.replace('/login');
        }
      } catch {
        router.replace('/login');
      }
    }, 600);
    return () => clearTimeout(timer);
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.logo}>MyndLens</Text>
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
  logo: {
    fontSize: 42,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 3,
  },
});
