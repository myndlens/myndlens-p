import React, { useState, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  ActivityIndicator, KeyboardAvoidingView, Platform, Alert, Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { setItem } from '../src/utils/storage';

const TOTAL_STEPS = 10;
const OBEGEE_BASE = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';

// ObeGee API helper — calls ObeGee directly, not the MyndLens backend
const obegee = (path: string, opts?: RequestInit, token?: string) =>
  fetch(`${OBEGEE_BASE}/api${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...opts,
  }).then(async r => {
    const text = await r.text();
    let data: any;
    try {
      data = JSON.parse(text);
    } catch {
      // ObeGee returned non-JSON (HTML error page, plain text)
      throw new Error(`Server error (${r.status}): ${text.slice(0, 120)}`);
    }
    if (!r.ok) throw new Error(data.detail || data.message || `HTTP ${r.status}`);
    return data;
  });

const DELIVERY_CHANNELS = [
  { id: 'whatsapp', label: 'WhatsApp', desc: 'Receive reports via WhatsApp messages' },
  { id: 'email', label: 'Email', desc: 'Reports delivered to your inbox' },
  { id: 'telegram', label: 'Telegram', desc: 'Get updates in Telegram chat' },
  { id: 'slack', label: 'Slack', desc: 'Post to a Slack channel' },
  { id: 'sms', label: 'SMS', desc: 'Text message notifications' },
  { id: 'in_app', label: 'In-App Only', desc: 'View results only within MyndLens' },
];

export default function SetupWizardScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  // Account
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authToken, setAuthToken] = useState('');
  // Slug
  const [slug, setSlug] = useState('');
  const [slugAvailable, setSlugAvailable] = useState<boolean | null>(null);
  const [slugSuggestions, setSlugSuggestions] = useState<string[]>([]);
  const [tenantId, setTenantId] = useState('');
  // Plan
  const [plans, setPlans] = useState<any[]>([]);
  const [selectedPlan, setSelectedPlan] = useState('');
  // Coupon
  const [couponCode, setCouponCode] = useState('');
  const [couponStatus, setCouponStatus] = useState<null | 'valid' | 'invalid'>(null);
  const [couponBenefit, setCouponBenefit] = useState('');
  // Activation
  const [activationStatus, setActivationStatus] = useState('');
  const [progress, setProgress] = useState(0);
  // Pairing
  const [pairingCode, setPairingCode] = useState('');
  // Preferences
  const [phone, setPhone] = useState('');
  const [tz, setTz] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
  const [notifs, setNotifs] = useState(true);
  // Delivery channel
  const [deliveryChannels, setDeliveryChannels] = useState<string[]>(['in_app']);
  const [channelDetails, setChannelDetails] = useState<Record<string, string>>({});
  // Digital Self ingestion
  const [dsImporting, setDsImporting] = useState(false);
  const [dsResult, setDsResult] = useState<{ contacts: number; calendar: number; callLogs: number } | null>(null);
  const [dsSkipped, setDsSkipped] = useState(false);

  async function handleRegister() {
    if (!name.trim() || !email.trim() || !password.trim()) return;
    setLoading(true);
    try {
      // Step 1: POST /auth/signup → ObeGee
      const res = await obegee('/auth/signup', {
        method: 'POST',
        body: JSON.stringify({ email, password, name }),
      });
      if (res.access_token) {
        setAuthToken(res.access_token);
        setStep(2);
      }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Registration failed');
    }
    setLoading(false);
  }

  async function checkSlug(s: string) {
    if (s.length < 3) { setSlugAvailable(null); return; }
    try {
      // Step 2: POST /tenants/validate-slug → ObeGee
      const res = await obegee('/tenants/validate-slug', {
        method: 'POST',
        body: JSON.stringify({ slug: s.toLowerCase() }),
      });
      setSlugAvailable(res.valid ?? res.available ?? false);
      if (!(res.valid ?? res.available) && res.suggestions) setSlugSuggestions(res.suggestions);
    } catch { setSlugAvailable(false); }
  }

  async function handleCreateTenant() {
    setLoading(true);
    try {
      // Step 3: POST /tenants/ → ObeGee
      const res = await obegee('/tenants/', {
        method: 'POST',
        body: JSON.stringify({ workspace_slug: slug.toLowerCase(), name: slug }),
      }, authToken);
      if (res.tenant_id) { setTenantId(res.tenant_id); setStep(3); }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Could not create workspace');
    }
    setLoading(false);
  }

  async function loadPlans() {
    try {
      const res = await obegee('/billing/plans', undefined, authToken);
      if (Array.isArray(res)) { setPlans(res); setSelectedPlan(res[1]?.plan_id || res[0]?.plan_id); }
    } catch { /* plans optional */ }
  }

  async function handlePayment() {
    setLoading(true);
    try {
      // Step 4: POST /billing/checkout → ObeGee — returns Stripe URL + session_id
      const res = await obegee('/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({
          plan_id: selectedPlan,
          origin_url: 'https://app.myndlens.com',
          tenant_id: tenantId,
          coupon_code: couponStatus === 'valid' ? couponCode.trim().toUpperCase() : undefined,
        }),
      }, authToken);
      if (res.url) {
        // Open Stripe checkout in browser
        Linking.openURL(res.url);
        setStep(5);
        // Poll for payment completion BEFORE activating — Stripe webhook may not have fired yet
        pollPaymentThenActivate(res.session_id);
      }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Payment failed');
    }
    setLoading(false);
  }

  async function validateCoupon() {
    if (!couponCode.trim()) return;
    try {
      const res = await obegee('/billing/validate-coupon', {
        method: 'POST',
        body: JSON.stringify({ code: couponCode.trim().toUpperCase() }),
      });
      setCouponStatus('valid');
      setCouponBenefit(res.benefit || '7 days free trial');
    } catch (err: any) {
      setCouponStatus('invalid');
      setCouponBenefit(err.message || 'Invalid coupon');
    }
  }

  async function pollPaymentThenActivate(sessionId: string) {
    setActivationStatus('activating');
    setProgress(0.1);
    const poll = setInterval(async () => {
      try {
        const status = await obegee(
          `/billing/checkout/status/${sessionId}`,
          undefined,
          authToken,
        );
        if (status.payment_status === 'paid') {
          clearInterval(poll);
          activateWorkspace();
        }
      } catch { /* keep polling — network hiccup */ }
    }, 3000);
    // 10 minute timeout — user has time to complete Stripe checkout
    setTimeout(() => clearInterval(poll), 600000);
  }

  async function activateWorkspace() {
    setActivationStatus('activating'); setProgress(0.2);
    try {
      // Step 5: POST /tenants/{tenant_id}/activate → ObeGee
      await obegee(`/tenants/${tenantId}/activate`, { method: 'POST' }, authToken);
      setProgress(0.6);
      // Step 6: Poll GET /tenants/my-tenant until status=READY
      const poll = setInterval(async () => {
        try {
          const res = await obegee('/tenants/my-tenant', undefined, authToken);
          if (res.status === 'READY') {
            clearInterval(poll);
            setProgress(1);
            setActivationStatus('ready');
            setTimeout(() => { setStep(6); }, 1500);
          }
        } catch { /* keep polling */ }
      }, 2000);
      setTimeout(() => clearInterval(poll), 120000);
    } catch (err: any) {
      Alert.alert('Activation Error', err.message || 'Workspace activation failed');
    }
  }

  async function generateCode() {
    try {
      // Step 7: POST /myndlens/generate-code → ObeGee
      const res = await obegee('/myndlens/generate-code', { method: 'POST' }, authToken);
      setPairingCode(res.code || '------');
      // Do NOT auto-advance — user must manually enter code in login screen
    } catch {
      setPairingCode('------');
    }
  }

  function isValidPhone(value: string): boolean {
    // E.164: starts with +, followed by 7–15 digits (total 8–16 chars)
    return /^\+[1-9]\d{6,14}$/.test(value.replace(/\s/g, ''));
  }

  async function handlePreferences() {
    const trimmedPhone = phone.replace(/\s/g, '');
    if (!isValidPhone(trimmedPhone)) {
      Alert.alert('Phone required', 'Enter your mobile number in international format, e.g. +44 7911 123456. This is needed to send your pairing code by SMS.');
      return;
    }
    try {
      await obegee('/tenants/preferences', {
        method: 'PATCH',
        body: JSON.stringify({ phone_number: trimmedPhone, timezone: tz, notifications_enabled: notifs, delivery_channels: deliveryChannels, channel_details: channelDetails }),
      }, authToken);
    } catch { /* preferences save failure is non-fatal — phone is the critical part */ }
    // Phone is now stored. Generate the pairing code (ObeGee can now SMS it).
    setStep(7);
    generateCode();
  }

  async function handleDigitalSelf() {
    setDsImporting(true);
    try {
      const { runTier1Ingestion, requestCallLogPermission } = require('../src/digital-self/ingester');
      await requestCallLogPermission();
      const userId = await getItem('myndlens_user_id') ?? 'local';
      const result = await runTier1Ingestion(userId);
      setDsResult(result);
    } catch (e: any) {
      // Import failed — non-fatal, continue to Complete
      setDsResult({ contacts: 0, calendar: 0, callLogs: 0 });
    } finally {
      setDsImporting(false);
    }
  }

  async function handleComplete() {
    await setItem('setup_wizard_complete', 'true');
    router.replace('/talk');
  }

  useEffect(() => { if (step === 3) loadPlans(); }, [step]);

  const STEP_LABELS = ['Welcome', 'Account', 'Workspace', 'Plan', 'Payment', 'Activating', 'Preferences', 'Pairing', 'Delivery', 'Digital Self', 'Complete'];

  return (
    <KeyboardAvoidingView style={[styles.container, { paddingTop: insets.top + 12 }]} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">

        {/* Progress */}
        {step > 0 && step < 9 && (
          <View style={styles.progressRow}>
            {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
              <View key={i} style={[styles.progressDot, i <= step && styles.progressDotActive]} />
            ))}
          </View>
        )}
        {step > 0 && step < 9 && <Text style={styles.progressLabel}>Step {step} of {TOTAL_STEPS} - {STEP_LABELS[step]}</Text>}

        {/* Step 0: Welcome */}
        {step === 0 && (
          <View style={styles.stepBox} data-testid="setup-welcome">
            <Text style={styles.bigTitle}>Welcome to ObeGee</Text>
            <Text style={styles.subtitle}>Your Sovereign AI Workspace</Text>
            <TouchableOpacity style={styles.primaryBtn} onPress={() => setStep(1)} data-testid="setup-create-account-btn">
              <Text style={styles.primaryBtnText}>Create Account</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.outlineBtn} onPress={() => router.replace('/login')} data-testid="setup-login-btn">
              <Text style={styles.outlineBtnText}>I have an account</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Step 1: Create Account */}
        {step === 1 && (
          <View style={styles.stepBox} data-testid="setup-account">
            <Text style={styles.title}>Create Your Account</Text>
            <TextInput style={styles.input} placeholder="Your Name" placeholderTextColor="#555" value={name} onChangeText={setName} autoFocus />
            <TextInput style={styles.input} placeholder="Email" placeholderTextColor="#555" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
            <TextInput style={styles.input} placeholder="Password" placeholderTextColor="#555" value={password} onChangeText={setPassword} secureTextEntry />
            <TouchableOpacity style={styles.primaryBtn} onPress={handleRegister} disabled={loading} data-testid="setup-register-btn">
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Create Account</Text>}
            </TouchableOpacity>
          </View>
        )}

        {/* Step 2: Choose Slug */}
        {step === 2 && (
          <View style={styles.stepBox} data-testid="setup-slug">
            <Text style={styles.title}>Choose Your Workspace Name</Text>
            <Text style={styles.desc}>This will be your unique identifier</Text>
            <TextInput style={styles.input} placeholder="my-workspace" placeholderTextColor="#555" value={slug} onChangeText={(s) => { setSlug(s); checkSlug(s); }} autoCapitalize="none" autoFocus />
            {slugAvailable === true && <Text style={styles.success}>Available!</Text>}
            {slugAvailable === false && (
              <View>
                <Text style={styles.error}>Taken. Try another.</Text>
                {slugSuggestions.length > 0 && (
                  <View style={styles.suggestRow}>{slugSuggestions.map(s => (
                    <TouchableOpacity key={s} style={styles.suggestChip} onPress={() => { setSlug(s); checkSlug(s); }}><Text style={styles.suggestText}>{s}</Text></TouchableOpacity>
                  ))}</View>
                )}
              </View>
            )}
            {slug.length >= 3 && <Text style={styles.preview}>{slug.toLowerCase()}.obegee.co.uk</Text>}
            <TouchableOpacity style={[styles.primaryBtn, !slugAvailable && styles.disabledBtn]} onPress={handleCreateTenant} disabled={!slugAvailable || loading}>
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Continue</Text>}
            </TouchableOpacity>
          </View>
        )}

        {/* Step 3: Choose Plan */}
        {step === 3 && (
          <View style={styles.stepBox} data-testid="setup-plan">
            <Text style={styles.title}>Choose Your Plan</Text>
            {plans.map(p => (
              <TouchableOpacity key={p.plan_id} style={[styles.planCard, selectedPlan === p.plan_id && styles.planCardActive]} onPress={() => setSelectedPlan(p.plan_id)} data-testid={`plan-${p.plan_id}`}>
                <View style={styles.planHeader}>
                  <Text style={styles.planName}>{p.name}</Text>
                  <Text style={styles.planPrice}>{p.currency} {p.price}/mo</Text>
                </View>
                {p.features.map((f: string) => <Text key={f} style={styles.planFeature}>{f}</Text>)}
              </TouchableOpacity>
            ))}
            <TouchableOpacity style={styles.primaryBtn} onPress={() => setStep(4)} data-testid="setup-continue-plan">
              <Text style={styles.primaryBtnText}>Continue to Payment</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Step 4: Payment */}
        {step === 4 && (
          <View style={styles.stepBox} data-testid="setup-payment">
            <Text style={styles.title}>Payment</Text>
            <Text style={styles.desc}>Plan: {plans.find(p => p.plan_id === selectedPlan)?.name || selectedPlan}</Text>
            <View style={styles.couponBox}>
              <Text style={styles.couponLabel}>Have a coupon code?</Text>
              <View style={styles.couponRow}>
                <TextInput
                  style={[styles.couponInput, couponStatus === 'valid' && styles.couponInputValid, couponStatus === 'invalid' && styles.couponInputInvalid]}
                  value={couponCode}
                  onChangeText={v => { setCouponCode(v.toUpperCase()); setCouponStatus(null); setCouponBenefit(''); }}
                  placeholder="OBG-XXXX"
                  placeholderTextColor="#555"
                  autoCapitalize="characters"
                  maxLength={8}
                />
                <TouchableOpacity style={styles.couponBtn} onPress={validateCoupon} disabled={!couponCode.trim()}>
                  <Text style={styles.couponBtnText}>Apply</Text>
                </TouchableOpacity>
              </View>
              {couponStatus === 'valid' && <Text style={styles.couponValid}>✓ {couponBenefit}</Text>}
              {couponStatus === 'invalid' && <Text style={styles.couponInvalid}>✗ {couponBenefit}</Text>}
            </View>
            <TouchableOpacity style={styles.primaryBtn} onPress={handlePayment} data-testid="setup-pay-btn">
              <Text style={styles.primaryBtnText}>{couponStatus === 'valid' ? 'Start Free Trial' : 'Complete Payment'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Step 5: Activating */}
        {step === 5 && (
          <View style={[styles.stepBox, styles.centerBox]} data-testid="setup-activating">
            <Text style={styles.title}>{activationStatus === 'ready' ? 'Workspace Ready!' : 'Provisioning Your Workspace'}</Text>
            <View style={styles.progressBarBg}><View style={[styles.progressBarFill, { width: `${progress * 100}%` }]} /></View>
            <Text style={styles.desc}>{activationStatus === 'ready' ? 'Your AI workspace is ready to use' : 'Setting up your AI workspace...'}</Text>
            {activationStatus === 'ready' && <Text style={styles.successBig}>Done</Text>}
            {activationStatus !== 'ready' && <ActivityIndicator color="#6C63FF" style={{ marginTop: 20 }} />}
          </View>
        )}

        {/* Step 6: Preferences (phone required before pairing code is generated) */}
        {step === 6 && (
          <View style={styles.stepBox} data-testid="setup-preferences">
            <Text style={styles.title}>Quick Setup</Text>
            <Text style={styles.desc}>We need your mobile number to send your pairing code by SMS.</Text>
            <TextInput
              style={styles.input}
              placeholder="+44 7911 123456"
              placeholderTextColor="#555"
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              textContentType="telephoneNumber"
              autoComplete="tel"
            />
            <TextInput style={styles.input} placeholder="Timezone (e.g. Europe/London)" placeholderTextColor="#555" value={tz} onChangeText={setTz} />
            <View style={styles.switchRow}>
              <Text style={styles.switchLabel}>Enable Notifications</Text>
              <TouchableOpacity style={[styles.toggle, notifs && styles.toggleOn]} onPress={() => setNotifs(!notifs)}>
                <Text style={styles.toggleText}>{notifs ? 'ON' : 'OFF'}</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity
              style={[styles.primaryBtn, !phone.trim() && styles.disabledBtn]}
              onPress={handlePreferences}
              disabled={!phone.trim()}
              data-testid="setup-save-prefs"
            >
              <Text style={styles.primaryBtnText}>Continue</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Step 7: Pairing (code generated after phone is stored) */}
        {step === 7 && (
          <View style={[styles.stepBox, styles.centerBox]} data-testid="setup-pairing">
            <Text style={styles.title}>Connecting MyndLens...</Text>
            <View style={styles.codeBox}><Text style={styles.codeText}>{pairingCode}</Text></View>
            <ActivityIndicator color="#6C63FF" style={{ marginTop: 16 }} />
            <Text style={styles.desc}>Pairing automatically...</Text>
          </View>
        )}

        {/* Step 8: Delivery Channels */}
        {step === 8 && (
          <View style={styles.stepBox} data-testid="setup-delivery">
            <Text style={styles.title}>Where should we deliver results?</Text>
            <Text style={styles.desc}>Choose where OpenClaw sends reports, artefacts, and task results after execution. You can select multiple.</Text>
            {DELIVERY_CHANNELS.map(ch => {
              const selected = deliveryChannels.includes(ch.id);
              return (
                <TouchableOpacity key={ch.id} style={[styles.channelCard, selected && styles.channelCardActive]}
                  onPress={() => {
                    if (selected) setDeliveryChannels(deliveryChannels.filter(c => c !== ch.id));
                    else setDeliveryChannels([...deliveryChannels, ch.id]);
                  }} data-testid={`channel-${ch.id}`}>
                  <View style={styles.channelRow}>
                    <View style={[styles.channelCheck, selected && styles.channelCheckActive]}>
                      {selected && <Text style={styles.channelCheckMark}>{'\u2713'}</Text>}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.channelLabel, selected && styles.channelLabelActive]}>{ch.label}</Text>
                      <Text style={styles.channelDesc}>{ch.desc}</Text>
                    </View>
                  </View>
                  {selected && ch.id !== 'in_app' && (
                    <TextInput
                      style={styles.channelInput}
                      placeholder={ch.id === 'email' ? 'your@email.com' : ch.id === 'whatsapp' || ch.id === 'sms' ? '+44 7XXX XXXXXX' : ch.id === 'telegram' ? '@username' : '#channel'}
                      placeholderTextColor="#444"
                      value={channelDetails[ch.id] || ''}
                      onChangeText={(v) => setChannelDetails({ ...channelDetails, [ch.id]: v })}
                    />
                  )}
                </TouchableOpacity>
              );
            })}
            <TouchableOpacity style={styles.primaryBtn} onPress={async () => {
              await obegee('/tenants/preferences', {
              method: 'PATCH',
              body: JSON.stringify({ delivery_channels: deliveryChannels, channel_details: channelDetails }),
            }, authToken);
              setStep(9);
            }} data-testid="setup-save-channels">
              <Text style={styles.primaryBtnText}>Continue</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Step 9: Digital Self — must be populated before Talk screen */}
        {step === 9 && (
          <View style={styles.stepBox} data-testid="setup-digital-self">
            <Text style={styles.title}>Build your Digital Self</Text>
            <Text style={styles.desc}>
              Your Digital Self is what makes MyndLens personal. The more it knows about you — your contacts, routines, and patterns — the fewer questions it needs to ask.{'\n\n'}
              This takes about 10 seconds. You can skip it and add later in Settings.
            </Text>

            {!dsResult && !dsSkipped && (
              <>
                <TouchableOpacity
                  style={[styles.primaryBtn, dsImporting && styles.disabledBtn]}
                  onPress={handleDigitalSelf}
                  disabled={dsImporting}
                  data-testid="setup-import-ds"
                >
                  {dsImporting
                    ? <ActivityIndicator color="#fff" />
                    : <Text style={styles.primaryBtnText}>Import Contacts & Calendar</Text>
                  }
                </TouchableOpacity>
                {dsImporting && (
                  <Text style={[styles.desc, { textAlign: 'center', marginTop: 12 }]}>
                    Reading your contacts and calendar patterns...
                  </Text>
                )}
                <TouchableOpacity onPress={() => { setDsSkipped(true); setStep(10); }} style={styles.skipBtn}>
                  <Text style={styles.skipText}>Skip for now</Text>
                </TouchableOpacity>
              </>
            )}

            {dsResult && (
              <>
                <View style={styles.dsResultBox}>
                  <Text style={styles.dsResultTitle}>Digital Self seeded</Text>
                  <Text style={styles.dsResultItem}>{dsResult.contacts} contacts imported</Text>
                  <Text style={styles.dsResultItem}>{dsResult.calendar} calendar patterns extracted</Text>
                  {dsResult.callLogs > 0 && (
                    <Text style={styles.dsResultItem}>{dsResult.callLogs} call log signals enriched</Text>
                  )}
                </View>
                <TouchableOpacity style={styles.primaryBtn} onPress={() => setStep(10)} data-testid="setup-ds-continue">
                  <Text style={styles.primaryBtnText}>Continue</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        )}

        {/* Step 10: Complete */}
        {step === 10 && (
          <View style={[styles.stepBox, styles.centerBox]} data-testid="setup-complete">
            <Text style={styles.successBig}>All Set!</Text>
            <Text style={styles.title}>Your AI workspace is ready</Text>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryLabel}>Workspace</Text><Text style={styles.summaryValue}>{slug || 'dev-workspace'}</Text>
              <Text style={styles.summaryLabel}>Plan</Text><Text style={styles.summaryValue}>{plans.find(p => p.plan_id === selectedPlan)?.name || 'Pro'}</Text>
            </View>
            <Text style={styles.nextTitle}>What's Next?</Text>
            <Text style={styles.nextItem}>Send your first mandate</Text>
            <Text style={styles.nextItem}>Create custom agents</Text>
            <Text style={styles.nextItem}>Configure tools & integrations</Text>
            <TouchableOpacity style={styles.primaryBtn} onPress={handleComplete} data-testid="setup-get-started">
              <Text style={styles.primaryBtnText}>Get Started</Text>
            </TouchableOpacity>
          </View>
        )}

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0F' },
  scroll: { paddingHorizontal: 24, paddingBottom: 40 },
  progressRow: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 8, marginBottom: 6 },
  progressDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#222' },
  progressDotActive: { backgroundColor: '#6C63FF' },
  progressLabel: { fontSize: 12, color: '#666', textAlign: 'center', marginBottom: 16 },
  stepBox: { paddingTop: 24 },
  centerBox: { alignItems: 'center', paddingTop: 60 },
  bigTitle: { fontSize: 32, fontWeight: '700', color: '#F0F0F5', textAlign: 'center', marginBottom: 8, marginTop: 60 },
  title: { fontSize: 22, fontWeight: '700', color: '#F0F0F5', marginBottom: 8 },
  subtitle: { fontSize: 16, color: '#888', textAlign: 'center', marginBottom: 40 },
  desc: { fontSize: 14, color: '#777', marginBottom: 16 },
  input: { backgroundColor: '#14141E', borderWidth: 1, borderColor: '#2A2A3A', borderRadius: 12, paddingHorizontal: 16, paddingVertical: 14, fontSize: 16, color: '#F0F0F5', marginBottom: 12 },
  primaryBtn: {
    backgroundColor: '#6C63FF',
    borderRadius: 14,
    paddingVertical: 16,
    paddingHorizontal: 32,
    alignItems: 'center',
    marginTop: 20,
    width: '100%',
    shadowColor: '#6C63FF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 6,
  },
  primaryBtnText: { color: '#fff', fontSize: 17, fontWeight: '700', letterSpacing: 0.3 },
  outlineBtn: { borderWidth: 1, borderColor: '#3A3A4E', borderRadius: 12, paddingVertical: 16, alignItems: 'center', marginTop: 12 },
  outlineBtnText: { color: '#AAAAB8', fontSize: 16 },
  disabledBtn: { opacity: 0.4 },
  success: { color: '#00D68F', fontSize: 14, marginBottom: 8 },
  error: { color: '#FF4444', fontSize: 14, marginBottom: 4 },
  successBig: { fontSize: 48, color: '#00D68F', marginBottom: 12 },
  preview: { color: '#6C63FF', fontSize: 14, marginBottom: 12 },
  suggestRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 8 },
  suggestChip: { backgroundColor: '#1A1A2E', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 },
  suggestText: { color: '#6C63FF', fontSize: 13 },
  planCard: { backgroundColor: '#14141E', borderWidth: 1, borderColor: '#2A2A3A', borderRadius: 14, padding: 16, marginBottom: 10 },
  planCardActive: { borderColor: '#6C63FF', backgroundColor: '#1A1A2E' },
  planHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  planName: { color: '#F0F0F5', fontSize: 18, fontWeight: '700' },
  planPrice: { color: '#6C63FF', fontSize: 18, fontWeight: '700' },
  planFeature: { color: '#999', fontSize: 14, marginTop: 2 },
  card: { backgroundColor: '#14141E', borderRadius: 14, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: '#2A2A3A' },
  cardText: { color: '#999', fontSize: 14, marginBottom: 4 },
  progressBarBg: { width: '100%', height: 8, backgroundColor: '#1E1E2E', borderRadius: 4, overflow: 'hidden', marginVertical: 16 },
  progressBarFill: { height: '100%', backgroundColor: '#6C63FF', borderRadius: 4 },
  codeBox: { backgroundColor: '#14141E', borderRadius: 14, paddingVertical: 20, paddingHorizontal: 40, marginVertical: 16, borderWidth: 1, borderColor: '#2A2A3A' },
  codeText: { fontSize: 36, fontWeight: '700', color: '#F0F0F5', textAlign: 'center', letterSpacing: 8 },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginVertical: 12 },
  switchLabel: { color: '#D0D0E0', fontSize: 16 },
  toggle: { backgroundColor: '#2A2A3E', borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8 },
  toggleOn: { backgroundColor: '#6C63FF' },
  toggleText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  skipBtn: { marginTop: 16, alignSelf: 'center', paddingVertical: 10 },
  skipText: { color: '#555', fontSize: 14 },
  channelCard: { backgroundColor: '#14141E', borderWidth: 1, borderColor: '#2A2A3A', borderRadius: 12, padding: 14, marginBottom: 8 },
  channelCardActive: { borderColor: '#6C63FF', backgroundColor: '#1A1A2E' },
  channelRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  channelCheck: { width: 24, height: 24, borderRadius: 6, borderWidth: 2, borderColor: '#3A3A4E', alignItems: 'center', justifyContent: 'center' },
  channelCheckActive: { borderColor: '#6C63FF', backgroundColor: '#6C63FF' },
  channelCheckMark: { color: '#fff', fontSize: 14, fontWeight: '700' },
  channelLabel: { color: '#AAAAB8', fontSize: 16, fontWeight: '600' },
  channelLabelActive: { color: '#F0F0F5' },
  channelDesc: { color: '#666', fontSize: 13, marginTop: 2 },
  channelInput: { backgroundColor: '#0A0A14', borderWidth: 1, borderColor: '#2A2A3A', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, color: '#F0F0F5', marginTop: 10, marginLeft: 36 },
  summaryCard: { backgroundColor: '#14141E', borderRadius: 14, padding: 16, width: '100%', marginVertical: 16, borderWidth: 1, borderColor: '#2A2A3A' },
  summaryLabel: { color: '#777', fontSize: 13, marginTop: 8 },
  summaryValue: { color: '#F0F0F5', fontSize: 16, fontWeight: '600' },
  nextTitle: { color: '#AAAAB8', fontSize: 16, fontWeight: '600', marginTop: 16, marginBottom: 8 },
  nextItem: { color: '#999', fontSize: 14, marginBottom: 4 },
  // Digital Self step styles
  dsResultBox: { backgroundColor: '#0D2B1A', borderRadius: 12, padding: 16, marginVertical: 16, width: '100%' },
  dsResultTitle: { color: '#00D68F', fontSize: 15, fontWeight: '700', marginBottom: 8 },
  dsResultItem: { color: '#aaa', fontSize: 14, marginBottom: 4 },
  couponBox: { marginBottom: 16, backgroundColor: '#1a1a2e', borderRadius: 12, padding: 14 },
  couponLabel: { color: '#888', fontSize: 13, marginBottom: 8 },
  couponRow: { flexDirection: 'row', gap: 8 },
  couponInput: { flex: 1, backgroundColor: '#12121e', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, color: '#fff', fontSize: 15, borderWidth: 1, borderColor: '#333', letterSpacing: 2 },
  couponInputValid: { borderColor: '#00c896' },
  couponInputInvalid: { borderColor: '#e74c3c' },
  couponBtn: { backgroundColor: '#4a4a6a', borderRadius: 8, paddingHorizontal: 14, justifyContent: 'center' },
  couponBtnText: { color: '#fff', fontSize: 14 },
  couponValid: { color: '#00c896', fontSize: 13, marginTop: 6 },
  couponInvalid: { color: '#e74c3c', fontSize: 13, marginTop: 6 },
});
