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
  ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { pairDevice, getOrCreateDeviceId } from '../src/ws/auth';
import { useSessionStore } from '../src/state/session-store';

/**
 * Pairing screen — device binding flow.
 * User enters their ID (simplified for Batch 1).
 * In production: OAuth/biometric flow.
 */
export default function PairingScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const setAuth = useSessionStore((s) => s.setAuth);

  const [userId, setUserId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deviceId, setDeviceId] = useState<string | null>(null);

  React.useEffect(() => {
    getOrCreateDeviceId().then(setDeviceId);
  }, []);

  async function handlePair() {
    if (!userId.trim()) {
      setError('Please enter a User ID');
      return;
    }

    Keyboard.dismiss();
    setLoading(true);
    setError(null);

    try {
      const result = await pairDevice(userId.trim());
      setAuth(result.user_id, result.device_id);
      router.replace('/talk');
    } catch (err: any) {
      setError(err.message || 'Pairing failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={[
          styles.container,
          { paddingTop: insets.top + 60, paddingBottom: insets.bottom + 24 },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.logo}>MyndLens</Text>
          <Text style={styles.title}>Device Pairing</Text>
          <Text style={styles.description}>
            Link your device to your MyndLens identity.{' '}
            This binds your session to this device for sovereign control.
          </Text>
        </View>

        {/* Form */}
        <View style={styles.form}>
          <Text style={styles.label}>User ID</Text>
          <TextInput
            style={styles.input}
            value={userId}
            onChangeText={setUserId}
            placeholder="Enter your User ID"
            placeholderTextColor="#555568"
            autoCapitalize="none"
            autoCorrect={false}
            editable={!loading}
            returnKeyType="done"
            onSubmitEditing={handlePair}
          />

          {deviceId && (
            <View style={styles.deviceInfo}>
              <Text style={styles.deviceLabel}>Device ID</Text>
              <Text style={styles.deviceValue} numberOfLines={1}>
                {deviceId}
              </Text>
            </View>
          )}

          {error && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          )}

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handlePair}
            disabled={loading}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>Pair Device</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* Info */}
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>How it works</Text>
          <Text style={styles.infoItem}>
            • Your device generates a unique key pair
          </Text>
          <Text style={styles.infoItem}>
            • Session is bound to User + Device + Environment
          </Text>
          <Text style={styles.infoItem}>
            • Heartbeat every 5s verifies your presence
          </Text>
          <Text style={styles.infoItem}>
            • Execute commands require active presence
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0A0A0F' },
  container: {
    flexGrow: 1,
    paddingHorizontal: 24,
  },
  header: {
    marginBottom: 40,
  },
  logo: {
    fontSize: 32,
    fontWeight: '800',
    color: '#6C5CE7',
    letterSpacing: 2,
    marginBottom: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 8,
  },
  description: {
    fontSize: 15,
    color: '#8B8B9E',
    lineHeight: 22,
  },
  form: {
    marginBottom: 32,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    color: '#A0A0B8',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  input: {
    backgroundColor: '#1A1A2E',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#2A2A3E',
    marginBottom: 16,
  },
  deviceInfo: {
    backgroundColor: '#1A1A2E',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  deviceLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#6C5CE7',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 4,
  },
  deviceValue: {
    fontSize: 12,
    color: '#555568',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  errorBox: {
    backgroundColor: '#2D1B1B',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E74C3C44',
  },
  errorText: {
    color: '#E74C3C',
    fontSize: 13,
  },
  button: {
    backgroundColor: '#6C5CE7',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  infoBox: {
    backgroundColor: '#12121E',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#1A1A2E',
  },
  infoTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  infoItem: {
    fontSize: 13,
    color: '#8B8B9E',
    lineHeight: 22,
  },
});
