import React, { useEffect } from 'react';
import { View, StyleSheet, Image } from 'react-native';
import { useRouter } from 'expo-router';
import { getStoredToken, getStoredUserId } from '../src/ws/auth';
import { useSessionStore } from '../src/state/session-store';

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
      <Image
        source={require('../assets/images/myndlens-logo.png')}
        style={styles.logo}
        resizeMode="contain"
      />
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
    width: 200,
    height: 200,
  },
});
