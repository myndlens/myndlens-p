/**
 * Kill Switch — "Delete my Digital Self."
 *
 * Wipes the entire on-device PKG and all associated local data.
 * Irreversible. User must re-onboard after this.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

const PKG_KEY_PREFIX = 'myndlens_digital_self_pkg';

export async function deleteDigitalSelf(userId: string): Promise<void> {
  // Remove this user's PKG
  await AsyncStorage.removeItem(`${PKG_KEY_PREFIX}_${userId}`);

  // Remove any other Digital Self keys for this user
  const allKeys = await AsyncStorage.getAllKeys();
  const dsKeys = allKeys.filter(k => k.startsWith('myndlens_ds_') && k.includes(userId));
  if (dsKeys.length > 0) {
    await AsyncStorage.multiRemove(dsKeys);
  }

  console.log(`[KillSwitch] Digital Self wiped for user: ${userId}`);
}

export async function getDigitalSelfSize(userId: string): Promise<number> {
  const raw = await AsyncStorage.getItem(`${PKG_KEY_PREFIX}_${userId}`);
  return raw ? new Blob([raw]).size : 0;
}
