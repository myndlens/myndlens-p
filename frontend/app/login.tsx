import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Keyboard,
  Image,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { getOrCreateDeviceId } from '../src/ws/auth';
import { setItem } from '../src/utils/storage';
import { useSessionStore } from '../src/state/session-store';
import { ENV } from '../src/config/env';

/**
 * Login — ObeGee 6-digit pairing code.
 * User gets the code from ObeGee Dashboard → Settings → Generate Pairing Code.
 * Code is single-use, valid for 10 minutes.
 */
export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const setAuth = useSessionStore((s) => s.setAuth);

  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect() {
    const trimmed = code.replace(/\s/g, '');
    if (trimmed.length !== 6 || !/^\d{6}$/.test(trimmed)) {
      setError('Please enter a valid 6-digit code');
      return;
    }

    Keyboard.dismiss();
    setLoading(true);
    setError(null);

    try {
      const deviceId = await getOrCreateDeviceId();
      const deviceName = Platform.OS === 'web' ? 'Web Browser' : `${Platform.OS} Device`;

      // Call ObeGee pairing endpoint (or dev mock)
      const pairUrl = ENV.API_URL ? `${ENV.API_URL}/sso/myndlens/pair` : OBEGEE_PAIR_URL;

      const res = await fetch(pairUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: trimmed,
          device_id: deviceId,
          device_name: deviceName,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || 'Invalid or expired code');
      }

      const data = await res.json();

      // Store all pairing response fields securely
      await setItem('myndlens_auth_token', data.access_token);
      await setItem('myndlens_tenant_id', data.tenant_id);
      await setItem('myndlens_workspace_slug', data.workspace_slug || '');
      await setItem('myndlens_runtime_endpoint', data.runtime_endpoint || '');
      await setItem('myndlens_dispatch_endpoint', data.dispatch_endpoint || '');
      await setItem('myndlens_session_id', data.session_id || '');
      await setItem('myndlens_user_id', data.tenant_id);

      setAuth(data.tenant_id, deviceId);
      router.replace('/loading');
    } catch (err: any) {
      setError(err.message || 'Connection failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={[styles.container, { paddingTop: insets.top + 80, paddingBottom: insets.bottom + 40 }]}>
        <View style={styles.brand}>
          <Image
            source={require('../assets/images/myndlens-logo.png')}
            style={styles.logoImage}
            resizeMode="contain"
          />
          <Text style={styles.subtitle}>Your Personal Cognitive Proxy</Text>
        </View>

        <View style={styles.middle}>
          <Text style={styles.instruction}>Enter your pairing code</Text>
          <Text style={styles.hint}>
            Find it in your OpenClaw Dashboard under Settings
          </Text>

          <TextInput
            style={styles.codeInput}
            value={code}
            onChangeText={(t) => {
              setCode(t.replace(/[^0-9]/g, '').slice(0, 6));
              setError(null);
            }}
            placeholder="000000"
            placeholderTextColor="#333340"
            keyboardType="number-pad"
            maxLength={6}
            textAlign="center"
            editable={!loading}
            returnKeyType="done"
            onSubmitEditing={handleConnect}
          />

          {error && (
            <Text style={styles.error}>{error}</Text>
          )}
        </View>

        <View style={styles.bottom}>
          <TouchableOpacity
            style={[styles.button, (loading || code.length !== 6) && styles.buttonDisabled]}
            onPress={handleConnect}
            disabled={loading || code.length !== 6}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>Connect</Text>
            )}
          </TouchableOpacity>
          <Text style={styles.footerHint}>Secure sign-in via ObeGee</Text>
          <TouchableOpacity onPress={() => router.push('/setup')} style={{ marginTop: 16, paddingVertical: 8 }} data-testid="new-user-setup-btn">
            <Text style={{ color: '#6C63FF', fontSize: 15, textAlign: 'center' }}>New User? Set up your workspace</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0A0A0F' },
  container: {
    flex: 1,
    paddingHorizontal: 32,
    justifyContent: 'space-between',
  },
  brand: {
    alignItems: 'center',
  },
  logoImage: {
    width: 180,
    height: 180,
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 16,
    color: '#8B8B9E',
  },
  middle: {
    alignItems: 'center',
  },
  instruction: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  hint: {
    fontSize: 14,
    color: '#555568',
    marginBottom: 24,
    textAlign: 'center',
  },
  codeInput: {
    backgroundColor: '#12121E',
    borderRadius: 16,
    paddingVertical: 20,
    paddingHorizontal: 32,
    fontSize: 32,
    fontWeight: '700',
    color: '#FFFFFF',
    letterSpacing: 12,
    width: '100%',
    borderWidth: 1,
    borderColor: '#2A2A3E',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  error: {
    color: '#E74C3C',
    fontSize: 13,
    marginTop: 12,
  },
  bottom: {
    alignItems: 'center',
  },
  button: {
    backgroundColor: '#6C5CE7',
    borderRadius: 16,
    paddingVertical: 18,
    width: '100%',
    alignItems: 'center',
  },
  buttonDisabled: {
    opacity: 0.4,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
  },
  footerHint: {
    color: '#555568',
    fontSize: 13,
    marginTop: 12,
  },
});
