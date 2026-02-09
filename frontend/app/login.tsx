import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { getOrCreateDeviceId } from '../src/ws/auth';
import { setItem } from '../src/utils/storage';
import { useSessionStore } from '../src/state/session-store';
import { ENV } from '../src/config/env';

/**
 * Login — SSO via ObeGee.
 * One button only: "Continue with ObeGee".
 * No input fields. No tech jargon.
 */
export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const setAuth = useSessionStore((s) => s.setAuth);
  const [loading, setLoading] = useState(false);

  async function handleContinue() {
    setLoading(true);
    try {
      const deviceId = await getOrCreateDeviceId();

      // Mock SSO: server auto-creates user from device
      const res = await fetch(`${ENV.API_URL}/sso/myndlens/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: `user_${deviceId.slice(-8)}`,
          password: 'sso',
          device_id: deviceId,
        }),
      });

      if (!res.ok) throw new Error('Sign-in failed');

      const data = await res.json();
      await setItem('myndlens_auth_token', data.token);
      await setItem('myndlens_user_id', data.obegee_user_id);
      setAuth(data.obegee_user_id, deviceId);
      router.replace('/loading');
    } catch {
      // Silent failure — button re-enables
      setLoading(false);
    }
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top + 80, paddingBottom: insets.bottom + 40 }]}>
      <View style={styles.brand}>
        <Text style={styles.logo}>MyndLens</Text>
        <Text style={styles.subtitle}>Your personal cognitive proxy</Text>
      </View>

      <View style={styles.bottom}>
        <TouchableOpacity
          style={[styles.button, loading && styles.buttonLoading]}
          onPress={handleContinue}
          disabled={loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.buttonText}>Continue with OpenClaw</Text>
          )}
        </TouchableOpacity>
        <Text style={styles.hint}>Secure sign-in via ObeGee</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0F',
    paddingHorizontal: 32,
    justifyContent: 'space-between',
  },
  brand: {
    alignItems: 'center',
    marginTop: 80,
  },
  logo: {
    fontSize: 44,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 3,
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 16,
    color: '#8B8B9E',
  },
  bottom: {
    alignItems: 'center',
  },
  button: {
    backgroundColor: '#6C5CE7',
    borderRadius: 16,
    paddingVertical: 18,
    paddingHorizontal: 48,
    width: '100%',
    alignItems: 'center',
  },
  buttonLoading: {
    opacity: 0.7,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
  },
  hint: {
    color: '#555568',
    fontSize: 13,
    marginTop: 12,
  },
});
