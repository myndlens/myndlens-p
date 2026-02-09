/**
 * Cross-platform secure storage wrapper.
 * Uses expo-secure-store on native, localStorage on web.
 */
import { Platform } from 'react-native';

let SecureStore: any = null;

// Only import SecureStore on native platforms
if (Platform.OS !== 'web') {
  try {
    SecureStore = require('expo-secure-store');
  } catch (e) {
    console.warn('expo-secure-store not available, using fallback');
  }
}

export async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }
  if (SecureStore) {
    return SecureStore.getItemAsync(key);
  }
  return null;
}

export async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Silently fail on web storage issues
    }
    return;
  }
  if (SecureStore) {
    return SecureStore.setItemAsync(key, value);
  }
}

export async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      localStorage.removeItem(key);
    } catch {
      // Silently fail
    }
    return;
  }
  if (SecureStore) {
    return SecureStore.deleteItemAsync(key);
  }
}
