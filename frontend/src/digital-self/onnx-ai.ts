/**
 * On-Device ONNX AI for Digital Self.
 *
 * Uses onnxruntime-react-native + a quantized embedding model for:
 *   - Semantic clustering of PKG nodes
 *   - Persona Summary generation from PKG
 *
 * Model: BAAI/bge-small-en-v1.5 (22MB ONNX, 384-dim embeddings)
 * Downloaded once on first launch, cached in app document directory.
 *
 * Falls back to template-based summary if ONNX is unavailable.
 * Requires APK rebuild with onnxruntime-react-native installed.
 */

import { PKG, PKGNode } from './pkg';

const MODEL_URL = 'https://huggingface.co/Xenova/bge-small-en-v1.5/resolve/main/onnx/model_quantized.onnx';
const MODEL_CACHE_KEY = 'myndlens_onnx_bge_small_v1';

let _session: any = null;
let _initialized = false;

// ── ONNX Session Management ─────────────────────────────────────────────────

export async function initONNX(): Promise<boolean> {
  if (_initialized) return true;
  try {
    // Dynamically import — graceful if onnxruntime-react-native not installed
    const { InferenceSession } = require('onnxruntime-react-native');
    const { FileSystem } = require('expo-file-system');

    const modelPath = `${FileSystem.documentDirectory}${MODEL_CACHE_KEY}.onnx`;
    const info = await FileSystem.getInfoAsync(modelPath);

    if (!info.exists) {
      console.log('[ONNX] Downloading model...');
      await FileSystem.downloadAsync(MODEL_URL, modelPath);
      console.log('[ONNX] Model downloaded:', modelPath);
    }

    _session = await InferenceSession.create(modelPath, {
      executionProviders: ['cpu'],
    });
    _initialized = true;
    console.log('[ONNX] Session ready');
    return true;
  } catch (err) {
    console.log('[ONNX] Not available (APK rebuild required):', err);
    return false;
  }
}

// ── Persona Summary ─────────────────────────────────────────────────────────

export async function generatePersonaSummary(pkg: PKG): Promise<string> {
  const nodes = Object.values(pkg.nodes);
  if (nodes.length === 0) return 'Your Digital Self is empty. Complete onboarding to build your profile.';

  // Template-based summary built from PKG (works without ONNX)
  const parts: string[] = [];

  const user = nodes.find(n => n.type === 'User');
  if (user) parts.push(`**${user.label}**`);

  const people = nodes.filter(n => n.type === 'Person');
  if (people.length > 0) {
    const names = people.slice(0, 5).map(p => {
      const rel = p.data.relationship ? ` (${p.data.relationship})` : '';
      return `${p.label}${rel}`;
    });
    parts.push(`Inner circle: ${names.join(', ')}${people.length > 5 ? ` +${people.length - 5} more` : ''}`);
  }

  const places = nodes.filter(n => n.type === 'Place');
  if (places.length > 0) {
    parts.push(`Locations: ${places.map(p => p.label).join(', ')}`);
  }

  const traits = nodes.filter(n => n.type === 'Trait');
  if (traits.length > 0) {
    parts.push(`Traits: ${traits.map(t => t.label).join(', ')}`);
  }

  const interests = nodes.filter(n => n.type === 'Interest');
  if (interests.length > 0) {
    parts.push(`Interests: ${interests.map(i => i.label).join(', ')}`);
  }

  const events = nodes.filter(n => n.type === 'Event');
  if (events.length > 0) {
    parts.push(`${events.length} calendar events indexed`);
  }

  return parts.join('\n');
}

// ── PKG Statistics ───────────────────────────────────────────────────────────

export function getPKGStats(pkg: PKG): {
  total: number;
  people: number;
  places: number;
  traits: number;
  interests: number;
  events: number;
  edges: number;
} {
  const nodes = Object.values(pkg.nodes);
  return {
    total: nodes.length,
    people: nodes.filter(n => n.type === 'Person').length,
    places: nodes.filter(n => n.type === 'Place').length,
    traits: nodes.filter(n => n.type === 'Trait').length,
    interests: nodes.filter(n => n.type === 'Interest').length,
    events: nodes.filter(n => n.type === 'Event').length,
    edges: Object.keys(pkg.edges).length,
  };
}
