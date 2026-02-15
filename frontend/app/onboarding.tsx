import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSessionStore } from '../src/state/session-store';
import { ENV } from '../src/config/env';

const STEPS = ['Name', 'Style', 'Contacts', 'Routines', 'Confirm'];

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const userId = useSessionStore((s) => s.userId);

  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  const [commStyle, setCommStyle] = useState('');
  const [contacts, setContacts] = useState([{ name: '', relationship: '' }]);
  const [routines, setRoutines] = useState(['']);

  async function handleSubmit() {
    setLoading(true);
    try {
      const body = {
        user_id: userId || 'anon',
        display_name: displayName.trim() || 'User',
        timezone,
        communication_style: commStyle,
        contacts: contacts.filter((c) => c.name.trim()),
        routines: routines.filter((r) => r.trim()),
        preferences: {},
      };
      const res = await fetch(`${ENV.API_URL}/onboarding/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        router.replace('/talk');
      }
    } catch {
      router.replace('/talk');
    } finally {
      setLoading(false);
    }
  }

  async function handleSkip() {
    try {
      await fetch(`${ENV.API_URL}/onboarding/skip/${userId || 'anon'}`, { method: 'POST' });
    } catch {}
    router.replace('/talk');
  }

  function addContact() {
    setContacts([...contacts, { name: '', relationship: '' }]);
  }
  function updateContact(i: number, field: string, val: string) {
    const c = [...contacts];
    (c[i] as any)[field] = val;
    setContacts(c);
  }
  function addRoutine() {
    setRoutines([...routines, '']);
  }
  function updateRoutine(i: number, val: string) {
    const r = [...routines];
    r[i] = val;
    setRoutines(r);
  }

  const renderStep = () => {
    switch (step) {
      case 0:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>What should I call you?</Text>
            <Text style={styles.stepDesc}>This helps me personalize our conversations.</Text>
            <TextInput
              style={styles.input}
              placeholder="Your name"
              placeholderTextColor="#555"
              value={displayName}
              onChangeText={setDisplayName}
              autoFocus
            />
            <Text style={styles.stepDesc}>Your timezone</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. America/New_York"
              placeholderTextColor="#555"
              value={timezone}
              onChangeText={setTimezone}
            />
          </View>
        );
      case 1:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>How do you like to communicate?</Text>
            <Text style={styles.stepDesc}>Choose your preferred style so I match your energy.</Text>
            {['Concise and direct', 'Detailed and thorough', 'Casual and friendly', 'Professional and formal'].map((s) => (
              <TouchableOpacity
                key={s}
                style={[styles.optionBtn, commStyle === s && styles.optionBtnActive]}
                onPress={() => setCommStyle(s)}
              >
                <Text style={[styles.optionText, commStyle === s && styles.optionTextActive]}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>
        );
      case 2:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>Key people in your life</Text>
            <Text style={styles.stepDesc}>Add contacts so I can help you communicate with them.</Text>
            {contacts.map((c, i) => (
              <View key={i} style={styles.contactRow}>
                <TextInput
                  style={[styles.input, { flex: 1, marginRight: 8 }]}
                  placeholder="Name"
                  placeholderTextColor="#555"
                  value={c.name}
                  onChangeText={(v) => updateContact(i, 'name', v)}
                />
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  placeholder="Relationship"
                  placeholderTextColor="#555"
                  value={c.relationship}
                  onChangeText={(v) => updateContact(i, 'relationship', v)}
                />
              </View>
            ))}
            <TouchableOpacity onPress={addContact} style={styles.addBtn}>
              <Text style={styles.addBtnText}>+ Add another</Text>
            </TouchableOpacity>
          </View>
        );
      case 3:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>Daily routines</Text>
            <Text style={styles.stepDesc}>Tell me about your typical day so I can better assist you.</Text>
            {routines.map((r, i) => (
              <TextInput
                key={i}
                style={styles.input}
                placeholder="e.g. Morning standup at 9am"
                placeholderTextColor="#555"
                value={r}
                onChangeText={(v) => updateRoutine(i, v)}
              />
            ))}
            <TouchableOpacity onPress={addRoutine} style={styles.addBtn}>
              <Text style={styles.addBtnText}>+ Add another</Text>
            </TouchableOpacity>
          </View>
        );
      case 4:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>All set!</Text>
            <Text style={styles.stepDesc}>
              I'll use this information to personalize your experience. You can always update these later.
            </Text>
            <View style={styles.summaryBox}>
              <Text style={styles.summaryItem}>Name: {displayName || 'Not set'}</Text>
              <Text style={styles.summaryItem}>Style: {commStyle || 'Not set'}</Text>
              <Text style={styles.summaryItem}>Contacts: {contacts.filter((c) => c.name).length}</Text>
              <Text style={styles.summaryItem}>Routines: {routines.filter((r) => r.trim()).length}</Text>
            </View>
          </View>
        );
      default:
        return null;
    }
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { paddingTop: insets.top + 20 }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.header}>Welcome to MyndLens</Text>
        <Text style={styles.subheader}>Let's get to know you</Text>

        <View style={styles.progressRow}>
          {STEPS.map((s, i) => (
            <View key={s} style={[styles.progressDot, i <= step && styles.progressDotActive]} />
          ))}
        </View>
        <Text style={styles.progressLabel}>Step {step + 1} of {STEPS.length} - {STEPS[step]}</Text>

        {renderStep()}

        <View style={styles.navRow}>
          {step > 0 && (
            <TouchableOpacity style={styles.backBtn} onPress={() => setStep(step - 1)}>
              <Text style={styles.backBtnText}>Back</Text>
            </TouchableOpacity>
          )}
          <View style={{ flex: 1 }} />
          {step < STEPS.length - 1 ? (
            <TouchableOpacity style={styles.nextBtn} onPress={() => setStep(step + 1)}>
              <Text style={styles.nextBtnText}>Next</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={styles.nextBtn} onPress={handleSubmit} disabled={loading}>
              {loading ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.nextBtnText}>Finish</Text>
              )}
            </TouchableOpacity>
          )}
        </View>

        <TouchableOpacity onPress={handleSkip} style={styles.skipBtn}>
          <Text style={styles.skipText}>Skip for now</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0F' },
  scroll: { paddingHorizontal: 24, paddingBottom: 40 },
  header: { fontSize: 28, fontWeight: '700', color: '#F0F0F5', textAlign: 'center', marginBottom: 4 },
  subheader: { fontSize: 15, color: '#888', textAlign: 'center', marginBottom: 24 },
  progressRow: { flexDirection: 'row', justifyContent: 'center', gap: 8, marginBottom: 8 },
  progressDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#222' },
  progressDotActive: { backgroundColor: '#6C63FF' },
  progressLabel: { fontSize: 13, color: '#666', textAlign: 'center', marginBottom: 24 },
  stepContainer: { marginBottom: 24 },
  stepTitle: { fontSize: 20, fontWeight: '600', color: '#E0E0E8', marginBottom: 8 },
  stepDesc: { fontSize: 14, color: '#777', marginBottom: 16 },
  input: {
    backgroundColor: '#14141E',
    borderWidth: 1,
    borderColor: '#2A2A3A',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: '#F0F0F5',
    marginBottom: 12,
  },
  optionBtn: {
    backgroundColor: '#14141E',
    borderWidth: 1,
    borderColor: '#2A2A3A',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
  },
  optionBtnActive: { borderColor: '#6C63FF', backgroundColor: '#1A1A2E' },
  optionText: { fontSize: 15, color: '#999' },
  optionTextActive: { color: '#F0F0F5' },
  contactRow: { flexDirection: 'row', marginBottom: 4 },
  addBtn: { paddingVertical: 8 },
  addBtnText: { color: '#6C63FF', fontSize: 14 },
  summaryBox: { backgroundColor: '#14141E', borderRadius: 12, padding: 16, marginTop: 8 },
  summaryItem: { fontSize: 15, color: '#CCC', marginBottom: 8 },
  navRow: { flexDirection: 'row', alignItems: 'center', marginTop: 16 },
  backBtn: { paddingVertical: 14, paddingHorizontal: 24, borderRadius: 12, backgroundColor: '#1A1A2A' },
  backBtnText: { color: '#999', fontSize: 16 },
  nextBtn: { paddingVertical: 14, paddingHorizontal: 32, borderRadius: 12, backgroundColor: '#6C63FF' },
  nextBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  skipBtn: { marginTop: 20, alignSelf: 'center', paddingVertical: 10 },
  skipText: { color: '#555', fontSize: 14 },
});
