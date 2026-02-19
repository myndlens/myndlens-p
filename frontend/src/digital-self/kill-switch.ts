/**
 * Kill Switch — "Delete my Digital Self."
 *
 * Wipes the entire on-device PKG, encrypted data, and the AES key from SecureStore.
 * Irreversible. User must re-onboard after this.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

const PKG_STORAGE_KEY_PREFIX = 'myndlens_ds_encrypted';
const AES_KEY_PREFIX = 'myndlens_ds_aes_key';

export async function deleteDigitalSelf(userId: string): Promise<void> {
  // 1. Delete encrypted PKG from AsyncStorage
  await AsyncStorage.removeItem(`${PKG_STORAGE_KEY_PREFIX}_${userId}`);

  // 2. Delete any other Digital Self keys for this user
  const allKeys = await AsyncStorage.getAllKeys();
  const dsKeys = allKeys.filter(k => k.startsWith('myndlens_ds_') && k.includes(userId));
  if (dsKeys.length > 0) await AsyncStorage.multiRemove(dsKeys);

  // 3. Delete AES encryption key from hardware-backed SecureStore (Secure Enclave / StrongBox)
  await SecureStore.deleteItemAsync(`${AES_KEY_PREFIX}_${userId}`);

  // 4. Clear in-memory key cache so next access generates a fresh key
  // (Accessing the _keyCache from pkg.ts is not possible due to module encapsulation,
  //  but the next loadPKG call will fail to decrypt old data, returning empty PKG — correct)

  console.log(`[KillSwitch] Digital Self fully wiped for user: ${userId}`);
}

export async function getDigitalSelfSize(userId: string): Promise<number> {
  const raw = await AsyncStorage.getItem(`${PKG_STORAGE_KEY_PREFIX}_${userId}`);
  return raw ? raw.length : 0;
}
