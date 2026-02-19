/**
 * Credential Vault — secure storage for Category B data source credentials.
 *
 * All credentials stored in expo-secure-store (hardware-backed).
 * Never transmitted in plaintext. Never stored on the backend.
 * Used transiently for the duration of a sync request only.
 */

import * as SecureStore from 'expo-secure-store';

const STORE_OPTS = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export interface IMAPCredentials {
  host: string;
  port: number;
  email: string;
  password: string;
}

export interface TelegramCredentials {
  phone: string;        // User's phone number for Telegram login
  api_id?: string;      // Optional: Telegram API ID for user-mode
  api_hash?: string;
}

export interface LinkedInCredentials {
  access_token: string; // OAuth2 access token from LinkedIn
}

export interface FinancialCredentials {
  provider: 'plaid' | 'truelayer' | 'custom';
  access_token: string;
}

// ── Generic helpers ──────────────────────────────────────────────────────────

async function storeCredential(key: string, value: object): Promise<void> {
  await SecureStore.setItemAsync(key, JSON.stringify(value), STORE_OPTS);
}

async function loadCredential<T>(key: string): Promise<T | null> {
  try {
    const raw = await SecureStore.getItemAsync(key, STORE_OPTS);
    if (raw) return JSON.parse(raw) as T;
  } catch { /* not found or corrupted */ }
  return null;
}

async function deleteCredential(key: string): Promise<void> {
  try { await SecureStore.deleteItemAsync(key); } catch { /* already gone */ }
}

// ── IMAP ─────────────────────────────────────────────────────────────────────

const IMAP_KEY = 'myndlens_cred_imap';
export const saveIMAPCredentials = (c: IMAPCredentials) => storeCredential(IMAP_KEY, c);
export const loadIMAPCredentials = () => loadCredential<IMAPCredentials>(IMAP_KEY);
export const deleteIMAPCredentials = () => deleteCredential(IMAP_KEY);

// ── Gmail OAuth token ────────────────────────────────────────────────────────

const GMAIL_KEY = 'myndlens_cred_gmail';
export const saveGmailToken = (token: string) => storeCredential(GMAIL_KEY, { token });
export const loadGmailToken = async () => { const d = await loadCredential<{ token: string }>(GMAIL_KEY); return d?.token ?? null; };
export const deleteGmailToken = () => deleteCredential(GMAIL_KEY);

// ── Outlook OAuth token ──────────────────────────────────────────────────────

const OUTLOOK_KEY = 'myndlens_cred_outlook';
export const saveOutlookToken = (token: string) => storeCredential(OUTLOOK_KEY, { token });
export const loadOutlookToken = async () => { const d = await loadCredential<{ token: string }>(OUTLOOK_KEY); return d?.token ?? null; };
export const deleteOutlookToken = () => deleteCredential(OUTLOOK_KEY);

// ── Telegram ─────────────────────────────────────────────────────────────────

const TELEGRAM_KEY = 'myndlens_cred_telegram';
export const saveTelegramCredentials = (c: TelegramCredentials) => storeCredential(TELEGRAM_KEY, c);
export const loadTelegramCredentials = () => loadCredential<TelegramCredentials>(TELEGRAM_KEY);
export const deleteTelegramCredentials = () => deleteCredential(TELEGRAM_KEY);

// ── LinkedIn ─────────────────────────────────────────────────────────────────

const LINKEDIN_KEY = 'myndlens_cred_linkedin';
export const saveLinkedInCredentials = (c: LinkedInCredentials) => storeCredential(LINKEDIN_KEY, c);
export const loadLinkedInCredentials = () => loadCredential<LinkedInCredentials>(LINKEDIN_KEY);
export const deleteLinkedInCredentials = () => deleteCredential(LINKEDIN_KEY);

// ── Financial ────────────────────────────────────────────────────────────────

const FINANCIAL_KEY = 'myndlens_cred_financial';
export const saveFinancialCredentials = (c: FinancialCredentials) => storeCredential(FINANCIAL_KEY, c);
export const loadFinancialCredentials = () => loadCredential<FinancialCredentials>(FINANCIAL_KEY);
export const deleteFinancialCredentials = () => deleteCredential(FINANCIAL_KEY);

// ── Revoke all ───────────────────────────────────────────────────────────────

export async function revokeAllCredentials(): Promise<void> {
  await Promise.all([
    deleteIMAPCredentials(),
    deleteGmailToken(),
    deleteOutlookToken(),
    deleteTelegramCredentials(),
    deleteLinkedInCredentials(),
    deleteFinancialCredentials(),
  ]);
}
