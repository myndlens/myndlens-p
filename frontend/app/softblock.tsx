import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSessionStore } from '../src/state/session-store';

/**
 * Soft Block — contextual block screen.
 * Used for: subscription paused, presence inactive, policy refusal.
 * One message. One action. No technical reasons.
 */
export default function SoftBlockScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { lastExecuteBlockReason } = useSessionStore();

  // Derive human-friendly message
  const reason = lastExecuteBlockReason || '';
  const isSub = reason.toLowerCase().includes('subscription');

  const title = isSub
    ? 'Your subscription is paused'
    : 'Please reopen the app to continue';

  const actionLabel = isSub ? 'Manage subscription' : 'Try again';

  function handleAction() {
    router.replace('/loading');
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top + 60, paddingBottom: insets.bottom + 40 }]}>
      <View style={styles.content}>
        <Text style={styles.icon}>\u26A0\uFE0F</Text>
        <Text style={styles.title}>{title}</Text>
      </View>

      <TouchableOpacity style={styles.button} onPress={handleAction} activeOpacity={0.8}>
        <Text style={styles.buttonText}>{actionLabel}</Text>
      </TouchableOpacity>
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
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  icon: {
    fontSize: 48,
    marginBottom: 24,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFFFFF',
    textAlign: 'center',
    lineHeight: 28,
  },
  button: {
    backgroundColor: '#6C5CE7',
    borderRadius: 16,
    paddingVertical: 18,
    alignItems: 'center',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '700',
  },
});
