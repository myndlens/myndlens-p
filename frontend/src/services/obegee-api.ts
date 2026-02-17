/**
 * ObeGee Dashboard API Client — handles all dashboard API calls.
 * Uses the extended pairing token for authentication.
 */
import { getItem, setItem } from '../utils/storage';
import { ENV } from '../config/env';

const OBEGEE_BASE = 'https://obegee.co.uk/api/myndlens-dashboard';

class ObeGeeAPI {
  private apiToken: string | null = null;

  async init() {
    this.apiToken = await getItem('obegee_api_token');
  }

  setToken(token: string) {
    this.apiToken = token;
    setItem('obegee_api_token', token);
  }

  async getWorkspaceConfig() {
    return this.request('/workspace/config');
  }

  async updateTools(tools: string[]) {
    return this.request('/workspace/tools', {
      method: 'PATCH',
      body: JSON.stringify({ enabled_tools: tools }),
    });
  }

  async updateModel(provider: string, apiKey: string) {
    return this.request('/workspace/model', {
      method: 'PATCH',
      body: JSON.stringify({ provider, api_key: apiKey }),
    });
  }

  async getAgents() {
    return this.request('/workspace/agents');
  }

  async getUsage() {
    return this.request('/workspace/usage');
  }

  async getDashboardUrl() {
    return this.request('/dashboard-url');
  }

  async extendPairing(code: string, deviceId: string) {
    const res = await fetch(`${OBEGEE_BASE}/auth/extend-pairing`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, device_id: deviceId }),
    });
    if (!res.ok) throw new Error(`Pairing failed: ${res.status}`);
    const data = await res.json();
    this.setToken(data.api_token);
    return data;
  }

  private async request(path: string, options: RequestInit = {}) {
    // In dev/mock mode, use local backend mock endpoints
    const baseUrl = this.apiToken ? OBEGEE_BASE : `${ENV.API_URL}/dashboard`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };
    if (this.apiToken) {
      headers['Authorization'] = `Bearer ${this.apiToken}`;
    }
    const res = await fetch(`${baseUrl}${path}`, { ...options, headers });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  }
}

export const obeGeeAPI = new ObeGeeAPI();
