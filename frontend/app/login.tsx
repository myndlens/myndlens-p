import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, KeyboardAvoidingView, Platform, Keyboard, Image, ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { getOrCreateDeviceId } from '../src/ws/auth';
import { setItem } from '../src/utils/storage';
import { useSessionStore } from '../src/state/session-store';

const OBEGEE_URL = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';

export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const setAuth = useSessionStore((s) => s.setAuth);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !trimmedEmail.includes('@')) {
      setError('Please enter a valid email');
      return;
    }
    if (!password) {
      setError('Please enter your password');
      return;
    }

    Keyboard.dismiss();
    setLoading(true);
    setError(null);

    try {
      const deviceId = await getOrCreateDeviceId();
      const res = await fetch(`${OBEGEE_URL}/api/myndlens/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: trimmedEmail,
          password,
          device_id: deviceId,
          device_name: `${Platform.OS} Device`,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        if (res.status === 402) {
          setError('Payment incomplete. Complete setup at obegee.co.uk');
        } else if (res.status === 404) {
          setError('No workspace found. Tap "New User" below to set up.');
        } else {
          setError(data.detail || 'Login failed');
        }
        return;
      }

      // Store auth
      await Promise.all([
        setItem('myndlens_auth_token', data.access_token),
        setItem('myndlens_user_id', data.user_id),
        setItem('myndlens_tenant_id', data.tenant_id),
        setItem('myndlens_user_name', data.user_name || ''),
      ]);
      setAuth(data.user_id, '');
      router.replace('/loading');
    } catch (e: any) {
      setError(e.message || 'Connection error. Check your internet.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        contentContainerStyle={[styles.container, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 40 }]}
        keyboardShouldPersistTaps="handled"
        bounces={false}
      >
        <View style={styles.brand}>
          <Image
            source={require('../assets/images/myndlens-logo.png')}
            style={styles.logoImage}
            resizeMode="contain"
          />
          <Text style={styles.subtitle}>Your Personal Cognitive Proxy</Text>
        </View>

        <View style={styles.middle}>
          <Text style={styles.instruction}>Sign in</Text>

          <TextInput
            style={styles.input}
            value={email}
            onChangeText={t => { setEmail(t); setError(null); }}
            placeholder="Email"
            placeholderTextColor="#333340"
            keyboardType="email-address"
            autoCapitalize="none"
            autoComplete="email"
            editable={!loading}
            returnKeyType="next"
            data-testid="login-email-input"
          />

          <View style={styles.passwordRow}>
            <TextInput
              style={[styles.input, { flex: 1, borderTopRightRadius: 0, borderBottomRightRadius: 0, borderRightWidth: 0 }]}
              value={password}
              onChangeText={t => { setPassword(t); setError(null); }}
              placeholder="Password"
              placeholderTextColor="#333340"
              secureTextEntry={!showPassword}
              autoComplete="password"
              editable={!loading}
              returnKeyType="done"
              onSubmitEditing={handleLogin}
              data-testid="login-password-input"
            />
            <TouchableOpacity
              style={styles.eyeBtn}
              onPress={() => setShowPassword(!showPassword)}
              data-testid="toggle-password-visibility"
            >
              <Text style={styles.eyeIcon}>{showPassword ? '🙈' : '👁'}</Text>
            </TouchableOpacity>
          </View>

          {error && <Text style={styles.error}>{error}</Text>}
        </View>

        <View style={styles.bottom}>
          <TouchableOpacity
            style={[styles.button, (loading || !email.includes('@') || !password) && styles.buttonDisabled]}
            onPress={handleLogin}
            disabled={loading || !email.includes('@') || !password}
            activeOpacity={0.8}
            data-testid="login-submit-btn"
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>Sign In</Text>
            )}
          </TouchableOpacity>

          <Text style={styles.footerHint}>Same credentials as ObeGee dashboard</Text>

          <TouchableOpacity
            onPress={() => router.push('/setup')}
            style={{ marginTop: 16, paddingVertical: 8 }}
            data-testid="new-user-setup-btn"
          >
            <Text style={{ color: '#6C63FF', fontSize: 15, textAlign: 'center' }}>
              New User? Set up your workspace
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0A0A0F' },
  container: {
    flexGrow: 1, paddingHorizontal: 32, justifyContent: 'space-between',
  },
  brand: { alignItems: 'center' },
  logoImage: { width: 180, height: 180, marginBottom: 12 },
  subtitle: {
    fontSize: 15, color: '#666680', fontWeight: '400', textAlign: 'center',
  },
  middle: { gap: 12 },
  instruction: {
    fontSize: 20, fontWeight: '700', color: '#E0E0F0', textAlign: 'center', marginBottom: 4,
  },
  input: {
    borderWidth: 1, borderColor: '#1E1E30', borderRadius: 12,
    paddingHorizontal: 16, paddingVertical: 14,
    fontSize: 16, color: '#E0E0F0', backgroundColor: '#12121F',
  },
  error: {
    color: '#E74C3C', fontSize: 13, textAlign: 'center', marginTop: 4,
  },
  bottom: { alignItems: 'center' },
  button: {
    backgroundColor: '#6C5CE7', borderRadius: 14, paddingVertical: 16,
    width: '100%', alignItems: 'center',
  },
  buttonDisabled: { opacity: 0.4 },
  buttonText: {
    color: '#FFFFFF', fontSize: 17, fontWeight: '700', letterSpacing: 0.5,
  },
  footerHint: {
    color: '#444460', fontSize: 12, marginTop: 12, textAlign: 'center',
  },
  passwordRow: {
    flexDirection: 'row', alignItems: 'center',
  },
  eyeBtn: {
    backgroundColor: '#12121F', borderWidth: 1, borderColor: '#1E1E30',
    borderTopRightRadius: 12, borderBottomRightRadius: 12,
    paddingHorizontal: 14, paddingVertical: 14, justifyContent: 'center',
  },
  eyeIcon: { fontSize: 18 },
});
