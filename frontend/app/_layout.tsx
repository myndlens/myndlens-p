import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View, StyleSheet, AppState } from 'react-native';
import { setupNotificationHandler, setupAndroidChannels } from '../src/notifications/manager';
import { syncPKGToBackend, isSyncDue } from '../src/digital-self/sync';
import { getItem } from '../src/utils/storage';

export default function RootLayout() {
  useEffect(() => {
    // Register notification handler so foreground notifications render correctly
    setupNotificationHandler();
    setupAndroidChannels();

    // Delta sync when app comes to foreground (if sync is due)
    const subscription = AppState.addEventListener('change', async (state) => {
      if (state === 'active') {
        try {
          const due = await isSyncDue();
          if (due) {
            const userId = await getItem('myndlens_user_id');
            if (userId) {
              await syncPKGToBackend(userId);
            }
          }
        } catch { /* non-critical */ }
      }
    });

    return () => subscription.remove();
  }, []);
  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: '#0A0A0F' },
          animation: 'fade',
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="login" options={{ animation: 'fade' }} />
        <Stack.Screen name="setup" options={{ animation: 'fade' }} />
        <Stack.Screen name="onboarding" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen name="loading" options={{ animation: 'fade' }} />
        <Stack.Screen name="talk" options={{ animation: 'fade' }} />
        <Stack.Screen name="dashboard" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen name="persona" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen name="audit-log" options={{ animation: 'slide_from_right' }} />
        <Stack.Screen name="softblock" options={{ animation: 'fade', presentation: 'modal' }} />
        <Stack.Screen name="settings" options={{ animation: 'slide_from_bottom', presentation: 'modal' }} />
      </Stack>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0F',
  },
});
