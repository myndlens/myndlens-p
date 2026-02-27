import React, { useEffect } from 'react';
import { View, StyleSheet, Image } from 'react-native';
import { useRouter } from 'expo-router';
import * as Linking from 'expo-linking';
import { getStoredToken, getStoredUserId } from '../src/ws/auth';
import { useSessionStore } from '../src/state/session-store';
import { setItem } from '../src/utils/storage';
import { getOrCreateDeviceId } from '../src/ws/auth';
import { Platform } from 'react-native';

export default function SplashScreen() {
  const router = useRouter();
  const setAuth = useSessionStore((s) => s.setAuth);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        // Check for auto-pair deep link: myndlens://pair/{token}
        const url = await Linking.getInitialURL();
        if (url) {
          const token = extractPairToken(url);
          if (token) {
            const success = await autoPair(token);
            if (success) {
              router.replace('/loading');
              return;
            }
          }
        }

        // Normal flow: check stored auth
        const storedToken = await getStoredToken();
        const userId = await getStoredUserId();
        if (storedToken && userId) {
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

  function extractPairToken(url: string): string | null {
    // myndlens://pair/abc123 or https://obegee.co.uk/app/pair/abc123
    const match = url.match(/pair\/([a-f0-9]+)/i);
    return match ? match[1] : null;
  }

  async function autoPair(token: string): Promise<boolean> {
    try {
      const OBEGEE_URL = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';
      const deviceId = await getOrCreateDeviceId();
      const res = await fetch(`${OBEGEE_URL}/api/myndlens/auto-pair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, device_id: deviceId, device_name: `${Platform.OS} Device` }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      await setItem('myndlens_auth_token', data.access_token);
      await setItem('myndlens_user_id', data.user_id);
      await setItem('myndlens_tenant_id', data.tenant_id);
      await setItem('myndlens_user_name', data.user_name || '');
      setAuth(data.user_id, '');
      return true;
    } catch {
      return false;
    }
  }

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
