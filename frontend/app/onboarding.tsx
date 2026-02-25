import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  KeyboardAvoidingView, Platform, ActivityIndicator, Alert, Keyboard,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSessionStore } from '../src/state/session-store';
import { ENV } from '../src/config/env';
import { getStoredToken } from '../src/ws/auth';

const OBEGEE_URL = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';

const STEPS = ['Profile', 'Name', 'Style', 'Contacts', 'Routines', 'Confirm'];

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const userId = useSessionStore((s) => s.userId);

  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(true);

  // Step 0 — ObeGee profile fields
  const [profileName, setProfileName]         = useState('');
  const [phoneNumber, setPhoneNumber]         = useState('');
  const [whatsappNumber, setWhatsappNumber]   = useState('');
  const [sameAsPhone, setSameAsPhone]         = useState(true);
  const [picture, setPicture]                 = useState('');

  // Step 1 — MyndLens nickname / timezone
  const [displayName, setDisplayName] = useState('');
  const [timezone, setTimezone]       = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');

  // Step 2 — Communication style
  const [commStyle, setCommStyle] = useState('');

  // Step 3 — Key contacts
  const [contacts, setContacts] = useState([{ name: '', relationship: '' }]);

  // Step 4 — Daily routines
  const [routines, setRoutines] = useState(['']);

  // Pre-load existing ObeGee profile on mount
  // IMPORTANT: guard all setState calls with isMounted — if the user presses
  // back before the fetch completes, calling setState on an unmounted component
  // crashes React Native.
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    (async () => {
      try {
        const token = await getStoredToken();
        if (!token || !isMounted) return;
        const res = await fetch(`${OBEGEE_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok || !isMounted) return;
        const u = await res.json();
        if (!isMounted) return;
        if (u.name)             setProfileName(u.name);
        if (u.name)             setDisplayName(u.name);
        if (u.phone_number)     setPhoneNumber(u.phone_number);
        if (u.whatsapp_number)  {
          setWhatsappNumber(u.whatsapp_number);
          setSameAsPhone(u.whatsapp_number === u.phone_number);
        }
        if (u.picture)          setPicture(u.picture);
      } catch (e: any) {
        if (e?.name === 'AbortError') return; // cancelled on unmount — expected
      }
      if (isMounted) setLoadingProfile(false);
    })();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, []);

  async function saveObeGeeProfile() {
    try {
      const token = await getStoredToken();
      if (!token) return;
      const body: any = {};
      if (profileName.trim())  body.name           = profileName.trim();
      if (phoneNumber.trim())  body.phone_number   = phoneNumber.trim();
      body.whatsapp_number = sameAsPhone ? (phoneNumber.trim() || null) : (whatsappNumber.trim() || null);
      if (picture.trim())      body.picture        = picture.trim();
      if (Object.keys(body).length === 0) return;
      await fetch(`${OBEGEE_URL}/api/auth/me/profile`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
    } catch {}
  }

  async function handleSubmit() {
    setLoading(true);
    try {
      // Save ObeGee profile fields
      await saveObeGeeProfile();

      // Save MyndLens onboarding profile (memory/context)
      const body = {
        user_id: userId || 'anon',
        display_name: displayName.trim() || profileName.trim() || 'User',
        timezone,
        communication_style: commStyle,
        contacts: contacts.filter((c) => c.name.trim()),
        routines: routines.filter((r) => r.trim()),
        preferences: {},
      };
      await fetch(`${ENV.API_URL}/onboarding/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch {}
    setLoading(false);
    router.replace('/talk');
  }

  async function handleSkip() {
    try {
      await fetch(`${ENV.API_URL}/onboarding/skip/${userId || 'anon'}`, { method: 'POST' });
    } catch {}
    router.replace('/talk');
  }

  function addContact() { setContacts([...contacts, { name: '', relationship: '' }]); }
  function updateContact(i: number, field: string, val: string) {
    const c = [...contacts]; (c[i] as any)[field] = val; setContacts(c);
  }
  function addRoutine() { setRoutines([...routines, '']); }
  function updateRoutine(i: number, val: string) {
    const r = [...routines]; r[i] = val; setRoutines(r);
  }

  const renderStep = () => {
    switch (step) {
      case 0:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>Your Profile</Text>
            <Text style={styles.stepDesc}>Basic details used across ObeGee and MyndLens.</Text>

            <Text style={styles.fieldLabel}>Display Name</Text>
            <TextInput
              style={styles.input}
              placeholder="Your full name"
              placeholderTextColor="#555"
              value={profileName}
              onChangeText={setProfileName}
              autoFocus
            />

            <Text style={styles.fieldLabel}>Phone Number</Text>
            <TextInput
              style={styles.input}
              placeholder="+919898089931"
              placeholderTextColor="#555"
              value={phoneNumber}
              onChangeText={v => { setPhoneNumber(v); if (sameAsPhone) setWhatsappNumber(v); }}
              keyboardType="phone-pad"
            />
            <Text style={styles.hint}>Include country code e.g. +91 India, +44 UK</Text>

            <TouchableOpacity style={styles.checkRow} onPress={() => setSameAsPhone(!sameAsPhone)}>
              <View style={[styles.checkbox, sameAsPhone && styles.checkboxOn]}>
                {sameAsPhone && <Text style={styles.checkmark}>✓</Text>}
              </View>
              <Text style={styles.checkLabel}>WhatsApp is same number</Text>
            </TouchableOpacity>

            {!sameAsPhone && (
              <>
                <Text style={styles.fieldLabel}>WhatsApp Number</Text>
                <TextInput
                  style={styles.input}
                  placeholder="+919898089931"
                  placeholderTextColor="#555"
                  value={whatsappNumber}
                  onChangeText={setWhatsappNumber}
                  keyboardType="phone-pad"
                />
              </>
            )}

            <Text style={styles.fieldLabel}>Profile Photo URL <Text style={styles.optional}>(optional)</Text></Text>
            <TextInput
              style={styles.input}
              placeholder="https://..."
              placeholderTextColor="#555"
              value={picture}
              onChangeText={setPicture}
              autoCapitalize="none"
              keyboardType="url"
            />
          </View>
        );

      case 1:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>What should I call you?</Text>
            <Text style={styles.stepDesc}>This helps me personalize our conversations.</Text>
            <TextInput
              style={styles.input}
              placeholder="Your name or nickname"
              placeholderTextColor="#555"
              value={displayName || profileName}
              onChangeText={setDisplayName}
              autoFocus
            />
            <Text style={styles.fieldLabel}>Your timezone</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. Asia/Kolkata"
              placeholderTextColor="#555"
              value={timezone}
              onChangeText={setTimezone}
            />
          </View>
        );

      case 2:
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

      case 3:
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

      case 4:
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

      case 5:
        return (
          <View style={styles.stepContainer}>
            <Text style={styles.stepTitle}>All set!</Text>
            <Text style={styles.stepDesc}>
              I'll use this to personalize your experience. You can update these any time via Edit Profile.
            </Text>
            <View style={styles.summaryBox}>
              {profileName  ? <Text style={styles.summaryItem}>👤 {profileName}</Text> : null}
              {phoneNumber  ? <Text style={styles.summaryItem}>📱 {phoneNumber}</Text> : null}
              {commStyle    ? <Text style={styles.summaryItem}>💬 {commStyle}</Text> : null}
              {contacts.filter(c => c.name).map((c, i) => (
                <Text key={i} style={styles.summaryItem}>🤝 {c.name} ({c.relationship || 'contact'})</Text>
              ))}
              {routines.filter(r => r).map((r, i) => (
                <Text key={i} style={styles.summaryItem}>🕐 {r}</Text>
              ))}
            </View>
          </View>
        );

      default:
        return null;
    }
  };

  if (loadingProfile) {
    return (
      <View style={[styles.container, { justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator color="#6C5CE7" size="large" />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        style={[styles.container, { paddingTop: insets.top }]}
        contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}
        keyboardShouldPersistTaps="handled"
      >
        {/* Progress */}
        <View style={styles.progressRow}>
          {STEPS.map((_, i) => (
            <View key={i} style={[styles.dot, i <= step && styles.dotActive]} />
          ))}
        </View>
        <Text style={styles.stepCount}>{step + 1} of {STEPS.length}</Text>

        {renderStep()}

        {/* Navigation */}
        <View style={styles.navRow}>
          {step > 0 && (
            <TouchableOpacity style={styles.backBtn} onPress={() => setStep(step - 1)}>
              <Text style={styles.backText}>← Back</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity
            style={[styles.nextBtn, loading && { opacity: 0.6 }]}
            onPress={isLastStep ? handleSubmit : () => setStep(step + 1)}
            disabled={loading}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.nextText}>{isLastStep ? 'Save & Done' : 'Next →'}</Text>}
          </TouchableOpacity>
        </View>

        {step === 0 && (
          <TouchableOpacity onPress={handleSkip} style={styles.skipBtn}>
            <Text style={styles.skipText}>Skip for now</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: '#0A0A14', paddingHorizontal: 20 },
  progressRow:     { flexDirection: 'row', gap: 6, marginTop: 16, marginBottom: 4 },
  dot:             { flex: 1, height: 3, borderRadius: 2, backgroundColor: '#2A2A3E' },
  dotActive:       { backgroundColor: '#6C5CE7' },
  stepCount:       { color: '#666', fontSize: 12, marginBottom: 24, textAlign: 'right' },
  stepContainer:   { gap: 4 },
  stepTitle:       { fontSize: 22, fontWeight: '700', color: '#fff', marginBottom: 4 },
  stepDesc:        { fontSize: 14, color: '#888', marginBottom: 16 },
  fieldLabel:      { fontSize: 13, color: '#aaa', marginTop: 12, marginBottom: 4 },
  optional:        { color: '#555', fontStyle: 'italic' },
  hint:            { fontSize: 11, color: '#555', marginTop: -8, marginBottom: 8 },
  input:           { backgroundColor: '#111', borderWidth: 1, borderColor: '#2A2A3E', borderRadius: 10, color: '#fff', paddingHorizontal: 14, paddingVertical: 12, fontSize: 15 },
  checkRow:        { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 10, marginBottom: 4 },
  checkbox:        { width: 20, height: 20, borderRadius: 4, borderWidth: 1.5, borderColor: '#444', alignItems: 'center', justifyContent: 'center' },
  checkboxOn:      { backgroundColor: '#6C5CE7', borderColor: '#6C5CE7' },
  checkmark:       { color: '#fff', fontSize: 12 },
  checkLabel:      { color: '#ccc', fontSize: 14 },
  optionBtn:       { borderWidth: 1, borderColor: '#2A2A3E', borderRadius: 10, padding: 14, marginBottom: 8 },
  optionBtnActive: { borderColor: '#6C5CE7', backgroundColor: '#1A0F3A' },
  optionText:      { color: '#888', fontSize: 15, textAlign: 'center' },
  optionTextActive:{ color: '#fff' },
  contactRow:      { flexDirection: 'row', marginBottom: 8 },
  addBtn:          { marginTop: 8, alignSelf: 'flex-start' },
  addBtnText:      { color: '#6C5CE7', fontSize: 14 },
  summaryBox:      { backgroundColor: '#111', borderRadius: 12, padding: 16, gap: 8, marginTop: 8 },
  summaryItem:     { color: '#ccc', fontSize: 14 },
  navRow:          { flexDirection: 'row', justifyContent: 'flex-end', gap: 12, marginTop: 32 },
  backBtn:         { paddingVertical: 14, paddingHorizontal: 20 },
  backText:        { color: '#888', fontSize: 15 },
  nextBtn:         { backgroundColor: '#6C5CE7', borderRadius: 12, paddingVertical: 14, paddingHorizontal: 28 },
  nextText:        { color: '#fff', fontSize: 15, fontWeight: '600' },
  skipBtn:         { alignSelf: 'center', marginTop: 16 },
  skipText:        { color: '#555', fontSize: 13 },
});
