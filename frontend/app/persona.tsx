/**
 * Persona Summary Screen — Digital Self MVP
 *
 * Shows the user's on-device PKG as a readable persona summary.
 * All data is local. No network call made from this screen.
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator,
  TouchableOpacity, Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { loadPKG, PKG } from '../src/digital-self/pkg';
import { generatePersonaSummary, getPKGStats } from '../src/digital-self/onnx-ai';
import { deleteDigitalSelf } from '../src/digital-self/kill-switch';
import { runTier1Ingestion } from '../src/digital-self/ingester';
import { getStoredUserId } from '../src/ws/auth';

export default function PersonaScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [pkg, setPkg] = useState<PKG | null>(null);
  const [summary, setSummary] = useState('');
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const userId = await getStoredUserId();
      if (!userId) {
        // Not authenticated — don't load someone else's PKG under 'local'
        setSummary('Please log in to access your Digital Self.');
        setLoading(false);
        return;
      }
      const p = await loadPKG(userId);
      setPkg(p);
      setSummary(await generatePersonaSummary(p));
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }

  async function handleImport() {
    setImporting(true);
    try {
      const userId = await getStoredUserId();
      if (!userId) { Alert.alert('Not logged in', 'Please log in first.'); return; }
      const result = await runTier1Ingestion(userId);
      Alert.alert(
        'Import Complete',
        `Imported ${result.contacts} contacts and ${result.calendar} calendar items.`,
      );
      await load();
    } catch (e: any) {
      Alert.alert('Import Error', e.message);
    }
    setImporting(false);
  }

  async function handleDelete() {
    Alert.alert(
      'Delete Digital Self',
      'This permanently wipes your entire local Digital Self. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete Everything',
          style: 'destructive',
          onPress: async () => {
            const userId = await getStoredUserId() ?? 'local';
            await deleteDigitalSelf(userId);
            await load();
            Alert.alert('Done', 'Your Digital Self has been deleted.');
          },
        },
      ],
    );
  }

  const stats = pkg ? getPKGStats(pkg) : null;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Your Digital Self</Text>
        <View style={styles.lockBadge}>
          <Text style={styles.lockText}>🔒 On-Device</Text>
        </View>
      </View>

      {loading ? (
        <ActivityIndicator color="#6C5CE7" style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={styles.content}>

          {/* Stats row */}
          {stats && stats.total > 0 ? (
            <View style={styles.statsRow}>
              {[
                { label: 'People', value: stats.people },
                { label: 'Places', value: stats.places },
                { label: 'Traits', value: stats.traits },
                { label: 'Events', value: stats.events },
              ].map(s => (
                <View key={s.label} style={styles.statBox}>
                  <Text style={styles.statNum}>{s.value}</Text>
                  <Text style={styles.statLabel}>{s.label}</Text>
                </View>
              ))}
            </View>
          ) : (
            <View style={styles.emptyBox}>
              <Text style={styles.emptyText}>Your Digital Self is empty.</Text>
              <Text style={styles.emptySubtext}>Import from your device to get started.</Text>
            </View>
          )}

          {/* Summary card */}
          {summary ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Persona Summary</Text>
              <Text style={styles.summaryText}>{summary}</Text>
            </View>
          ) : null}

          {/* People list */}
          {pkg && Object.values(pkg.nodes).filter(n => n.type === 'Person').length > 0 && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Inner Circle</Text>
              {Object.values(pkg.nodes)
                .filter(n => n.type === 'Person')
                .slice(0, 10)
                .map(p => (
                  <View key={p.id} style={styles.personRow}>
                    <View style={styles.avatar}>
                      <Text style={styles.avatarText}>{(p.label[0] ?? '?').toUpperCase()}</Text>
                    </View>
                    <View>
                      <Text style={styles.personName}>{p.label}</Text>
                      {p.data.relationship ? <Text style={styles.personRel}>{p.data.relationship}</Text> : null}
                    </View>
                  </View>
                ))}
            </View>
          )}

          {/* Actions */}
          <TouchableOpacity
            style={[styles.actionBtn, importing && styles.actionBtnDisabled]}
            onPress={handleImport}
            disabled={importing}
          >
            {importing
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.actionBtnText}>Import from Device (Contacts + Calendar)</Text>
            }
          </TouchableOpacity>

          <TouchableOpacity style={styles.deleteBtn} onPress={handleDelete}>
            <Text style={styles.deleteBtnText}>Delete my Digital Self</Text>
          </TouchableOpacity>

          <Text style={styles.footer}>
            All data is encrypted on this device.{`\n`}Nothing is stored on any server.
          </Text>

        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A14' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: '#1A1A2E' },
  backBtn: { marginRight: 12 },
  backText: { color: '#6C5CE7', fontSize: 17 },
  title: { flex: 1, color: '#fff', fontSize: 18, fontWeight: '600' },
  lockBadge: { backgroundColor: '#1A1A2E', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
  lockText: { color: '#00D68F', fontSize: 11 },
  content: { padding: 16, gap: 16 },
  statsRow: { flexDirection: 'row', gap: 8 },
  statBox: { flex: 1, backgroundColor: '#1A1A2E', borderRadius: 12, padding: 12, alignItems: 'center' },
  statNum: { color: '#6C5CE7', fontSize: 24, fontWeight: '700' },
  statLabel: { color: '#888', fontSize: 11, marginTop: 2 },
  emptyBox: { backgroundColor: '#1A1A2E', borderRadius: 12, padding: 24, alignItems: 'center' },
  emptyText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  emptySubtext: { color: '#888', fontSize: 13, marginTop: 6, textAlign: 'center' },
  card: { backgroundColor: '#1A1A2E', borderRadius: 12, padding: 16 },
  cardTitle: { color: '#888', fontSize: 12, letterSpacing: 0.8, marginBottom: 12, textTransform: 'uppercase' },
  summaryText: { color: '#E0E0E0', fontSize: 14, lineHeight: 22 },
  personRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 10 },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#6C5CE7', alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  personName: { color: '#fff', fontSize: 14, fontWeight: '500' },
  personRel: { color: '#888', fontSize: 12 },
  actionBtn: { backgroundColor: '#6C5CE7', borderRadius: 12, padding: 14, alignItems: 'center' },
  actionBtnDisabled: { opacity: 0.5 },
  actionBtnText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  deleteBtn: { borderWidth: 1, borderColor: '#E74C3C', borderRadius: 12, padding: 14, alignItems: 'center' },
  deleteBtnText: { color: '#E74C3C', fontSize: 15, fontWeight: '500' },
  footer: { color: '#444', fontSize: 11, textAlign: 'center', lineHeight: 16 },
});
