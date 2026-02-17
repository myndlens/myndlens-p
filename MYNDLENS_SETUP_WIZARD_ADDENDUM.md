# ADDENDUM: MyndLens Setup Wizard Specification

**Added to**: MyndLens-ObeGee Dashboard Integration Specification v2.0  
**Date**: February 17, 2026  
**Purpose**: First-time user onboarding flow in MyndLens app

---

## Overview

The Setup Wizard guides new MyndLens users through workspace creation, payment, and initial configuration - all within the mobile app. This eliminates the need for web browser access during onboarding.

---

## Setup Wizard Flow

### Step 1: Welcome & Account Creation

**Screen**: Welcome  
**Purpose**: Introduce ObeGee and create account

```jsx
function WelcomeScreen() {
  return (
    <View>
      <Image source={require('./obegee-logo.png')} />
      <Text style={styles.title}>Welcome to ObeGee</Text>
      <Text>Your Sovereign AI Workspace</Text>
      
      <Button
        title="Create Account"
        onPress={() => navigate('CreateAccount')}
      />
      <Button
        title="I have an account"
        onPress={() => navigate('Login')}
        variant="outline"
      />
    </View>
  );
}

function CreateAccountScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  
  async function createAccount() {
    const response = await fetch('https://obegee.co.uk/api/auth/register', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email, password, name})
    });
    
    if (response.ok) {
      const {access_token, user} = await response.json();
      await SecureStore.setItemAsync('auth_token', access_token);
      navigate('ChooseWorkspaceSlug');
    }
  }
  
  return (
    <View>
      <TextInput
        placeholder="Your Name"
        value={name}
        onChangeText={setName}
      />
      <TextInput
        placeholder="Email"
        value={email}
        onChangeText={setEmail}
        keyboardType="email-address"
      />
      <TextInput
        placeholder="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
      />
      <Button onPress={createAccount}>Create Account</Button>
    </View>
  );
}
```

**ObeGee Backend Endpoint** (Already Exists):
- `POST /api/auth/register`

---

### Step 2: Choose Workspace Slug

**Screen**: Workspace Slug  
**Purpose**: Select unique workspace identifier

```jsx
function ChooseSlugScreen() {
  const [slug, setSlug] = useState('');
  const [checking, setChecking] = useState(false);
  const [available, setAvailable] = useState(null);
  
  async function checkSlug() {
    setChecking(true);
    
    const response = await fetch(
      `https://obegee.co.uk/api/tenants/check-slug/${slug}`,
      {headers: {Authorization: `Bearer ${authToken}`}}
    );
    
    const {available} = await response.json();
    setAvailable(available);
    setChecking(false);
  }
  
  async function createTenant() {
    const response = await fetch('https://obegee.co.uk/api/tenants', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({workspace_slug: slug})
    });
    
    const {tenant_id} = await response.json();
    await SecureStore.setItemAsync('tenant_id', tenant_id);
    
    navigate('ChoosePlan');
  }
  
  return (
    <View>
      <Text style={styles.title}>Choose Your Workspace Name</Text>
      <Text>This will be your unique identifier</Text>
      
      <TextInput
        placeholder="my-workspace"
        value={slug}
        onChangeText={setSlug}
        onBlur={checkSlug}
        autoCapitalize="none"
      />
      
      {checking && <ActivityIndicator />}
      
      {available === true && (
        <Text style={styles.success}>✅ Available!</Text>
      )}
      
      {available === false && (
        <Text style={styles.error}>❌ Taken. Try another.</Text>
      )}
      
      <Text style={styles.preview}>
        Your URL: {slug}.obegee.co.uk
      </Text>
      
      <Button
        onPress={createTenant}
        disabled={!available}
      >
        Continue
      </Button>
    </View>
  );
}
```

**ObeGee Backend Endpoints**:
- `GET /api/tenants/check-slug/{slug}` (needs to be created)
- `POST /api/tenants` (already exists)

---

### Step 3: Select Plan

**Screen**: Choose Plan  
**Purpose**: Select subscription tier

```jsx
function ChoosePlanScreen() {
  const [plans, setPlans] = useState([]);
  const [selected, setSelected] = useState(null);
  
  useEffect(() => {
    loadPlans();
  }, []);
  
  async function loadPlans() {
    const response = await fetch('https://obegee.co.uk/api/billing/plans');
    const data = await response.json();
    setPlans(data);
    setSelected(data[0]?.plan_id);
  }
  
  async function proceed() {
    await SecureStore.setItemAsync('selected_plan', selected);
    navigate('Payment');
  }
  
  return (
    <ScrollView>
      <Text style={styles.title}>Choose Your Plan</Text>
      
      {plans.map(plan => (
        <Card
          key={plan.plan_id}
          selected={selected === plan.plan_id}
          onPress={() => setSelected(plan.plan_id)}
        >
          <Text style={styles.planName}>{plan.name}</Text>
          <Text style={styles.price}>
            {plan.currency} {plan.price}/month
          </Text>
          <View>
            {plan.features.map(feature => (
              <Text key={feature}>✓ {feature}</Text>
            ))}
          </View>
        </Card>
      ))}
      
      <Button onPress={proceed}>Continue to Payment</Button>
    </ScrollView>
  );
}
```

**ObeGee Backend Endpoint** (Already Exists):
- `GET /api/billing/plans`

---

### Step 4: Payment

**Screen**: Payment (WebView)  
**Purpose**: Complete Stripe checkout

```jsx
function PaymentScreen() {
  const [checkoutUrl, setCheckoutUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    createCheckout();
  }, []);
  
  async function createCheckout() {
    const planId = await SecureStore.getItemAsync('selected_plan');
    const tenantId = await SecureStore.getItemAsync('tenant_id');
    const slug = await SecureStore.getItemAsync('workspace_slug');
    
    const response = await fetch('https://obegee.co.uk/api/billing/checkout', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        plan_id: planId,
        tenant_id: tenantId,
        workspace_slug: slug,
        origin_url: 'myndlens://payment-complete'
      })
    });
    
    const {checkout_url} = await response.json();
    setCheckoutUrl(checkout_url);
    setLoading(false);
  }
  
  function handleNavigationChange(event) {
    const {url} = event;
    
    // Check for success/cancel URLs
    if (url.includes('payment-complete')) {
      navigate('ActivatingWorkspace');
    } else if (url.includes('payment-cancelled')) {
      navigate('ChoosePlan');
    }
  }
  
  return (
    <View>
      {loading ? (
        <ActivityIndicator size="large" />
      ) : (
        <WebView
          source={{uri: checkoutUrl}}
          onNavigationStateChange={handleNavigationChange}
        />
      )}
    </View>
  );
}
```

**ObeGee Backend Endpoint** (Already Exists):
- `POST /api/billing/checkout`

---

### Step 5: Workspace Activation

**Screen**: Activating Workspace  
**Purpose**: Provision OpenClaw instance

```jsx
function ActivatingWorkspaceScreen() {
  const [status, setStatus] = useState('starting');
  const [progress, setProgress] = useState(0);
  
  useEffect(() => {
    activateWorkspace();
  }, []);
  
  async function activateWorkspace() {
    const tenantId = await SecureStore.getItemAsync('tenant_id');
    
    // Trigger activation
    setStatus('activating');
    setProgress(0.2);
    
    const response = await fetch(
      `https://obegee.co.uk/api/tenants/${tenantId}/activate`,
      {
        method: 'POST',
        headers: {Authorization: `Bearer ${authToken}`}
      }
    );
    
    setProgress(0.5);
    
    // Poll for completion
    const pollInterval = setInterval(async () => {
      const statusResp = await fetch(
        `https://obegee.co.uk/api/tenants/${tenantId}`,
        {headers: {Authorization: `Bearer ${authToken}`}}
      );
      
      const tenant = await statusResp.json();
      
      if (tenant.status === 'READY') {
        clearInterval(pollInterval);
        setProgress(1.0);
        setStatus('ready');
        
        setTimeout(() => navigate('GeneratePairingCode'), 2000);
      } else if (tenant.status === 'PROVISIONING') {
        setProgress(0.7);
      }
    }, 3000);
    
    // Timeout after 5 minutes
    setTimeout(() => {
      clearInterval(pollInterval);
      setStatus('timeout');
    }, 300000);
  }
  
  return (
    <View style={styles.center}>
      <AnimatedCheck show={status === 'ready'} />
      
      <Text style={styles.title}>
        {status === 'starting' && 'Starting...'}
        {status === 'activating' && 'Provisioning Your Workspace'}
        {status === 'ready' && '✅ Workspace Ready!'}
        {status === 'timeout' && 'Taking longer than expected...'}
      </Text>
      
      <ProgressBar progress={progress} />
      
      <Text style={styles.subtitle}>
        {status === 'activating' && 'Setting up OpenClaw with Kimi K2.5...'}
        {status === 'ready' && 'Your AI workspace is ready to use'}
      </Text>
    </View>
  );
}
```

**ObeGee Backend Endpoints** (Already Exist):
- `POST /api/tenants/{id}/activate`
- `GET /api/tenants/{id}`

---

### Step 6: Generate Pairing Code

**Screen**: Pair MyndLens  
**Purpose**: Connect mobile app to workspace

```jsx
function GeneratePairingCodeScreen() {
  const [code, setCode] = useState(null);
  const [expiresIn, setExpiresIn] = useState(null);
  
  useEffect(() => {
    generateCode();
  }, []);
  
  async function generateCode() {
    const response = await fetch(
      'https://obegee.co.uk/api/myndlens/generate-code',
      {
        method: 'POST',
        headers: {Authorization: `Bearer ${authToken}`}
      }
    );
    
    const data = await response.json();
    setCode(data.code);
    setExpiresIn(data.expires_in_seconds);
    
    // Auto-pair since we're already in the app
    await autoPair(data.code);
  }
  
  async function autoPair(code) {
    const deviceId = await getDeviceId();
    
    const response = await fetch(
      'https://obegee.co.uk/api/myndlens-dashboard/auth/extend-pairing',
      {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code, device_id: deviceId})
      }
    );
    
    const {api_token, tenant, endpoints} = await response.json();
    
    // Store credentials
    await SecureStore.setItemAsync('api_token', api_token);
    await SecureStore.setItemAsync('tenant_id', tenant.tenant_id);
    await SecureStore.setItemAsync('myndlens_ws_url', endpoints.myndlens_ws);
    
    // Mark setup complete
    await SecureStore.setItemAsync('setup_complete', 'true');
    
    navigate('SetupComplete');
  }
  
  return (
    <View style={styles.center}>
      <Text style={styles.title}>Connecting MyndLens...</Text>
      
      <View style={styles.codeBox}>
        <Text style={styles.code}>{code || '------'}</Text>
      </View>
      
      <Text>Code also sent to your email</Text>
      
      <ActivityIndicator />
      <Text>Pairing automatically...</Text>
    </View>
  );
}
```

**ObeGee Backend Endpoints** (Already Exist):
- `POST /api/myndlens/generate-code`
- `POST /api/myndlens-dashboard/auth/extend-pairing`

---

### Step 7: Initial Configuration

**Screen**: Quick Setup  
**Purpose**: Configure essential settings

```jsx
function QuickSetupScreen() {
  const [phone, setPhone] = useState('');
  const [timezone, setTimezone] = useState('UTC');
  const [notifications, setNotifications] = useState(true);
  
  async function completeSetup() {
    // Save preferences
    const response = await fetch(
      'https://obegee.co.uk/api/user/preferences',
      {
        method: 'PATCH',
        headers: {
          Authorization: `Bearer ${apiToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          phone_number: phone,
          timezone: timezone,
          notifications_enabled: notifications
        })
      }
    );
    
    navigate('SetupComplete');
  }
  
  return (
    <ScrollView>
      <Text style={styles.title}>Quick Setup</Text>
      <Text>Help us personalize your experience</Text>
      
      <TextInput
        label="Phone Number (Optional)"
        placeholder="+44 7XXX XXXXXX"
        value={phone}
        onChangeText={setPhone}
        keyboardType="phone-pad"
      />
      
      <Picker
        label="Timezone"
        selectedValue={timezone}
        onValueChange={setTimezone}>
        <Picker.Item label="London (GMT)" value="Europe/London" />
        <Picker.Item label="New York (EST)" value="America/New_York" />
        <Picker.Item label="Tokyo (JST)" value="Asia/Tokyo" />
      </Picker>
      
      <Switch
        label="Enable Notifications"
        value={notifications}
        onValueChange={setNotifications}
      />
      
      <Button onPress={completeSetup}>Complete Setup</Button>
      <Button
        variant="text"
        onPress={() => navigate('SetupComplete')}
      >
        Skip for now
      </Button>
    </ScrollView>
  );
}
```

**ObeGee Backend Endpoint** (Needs to be created):
```python
# /app/backend/routes/user.py
@router.patch("/preferences")
async def update_user_preferences(data: dict, request: Request):
    user = await get_current_user(request)
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "phone_number": data.get("phone_number"),
            "timezone": data.get("timezone"),
            "notifications_enabled": data.get("notifications_enabled"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Preferences updated"}
```

---

### Step 8: Setup Complete

**Screen**: All Set!  
**Purpose**: Confirm setup and show next steps

```jsx
function SetupCompleteScreen() {
  const [config, setConfig] = useState(null);
  
  useEffect(() => {
    loadWorkspaceConfig();
  }, []);
  
  async function loadWorkspaceConfig() {
    const data = await obeGeeAPI.getWorkspaceConfig();
    setConfig(data);
  }
  
  return (
    <View style={styles.center}>
      <LottieAnimation source={require('./success-animation.json')} />
      
      <Text style={styles.title}>🎉 All Set!</Text>
      <Text>Your AI workspace is ready</Text>
      
      <Card style={styles.summary}>
        <Text style={styles.label}>Workspace</Text>
        <Text style={styles.value}>{config?.workspace.slug}</Text>
        
        <Text style={styles.label}>Plan</Text>
        <Text style={styles.value}>{config?.subscription.plan_id}</Text>
        
        <Text style={styles.label}>AI Model</Text>
        <Text style={styles.value}>{config?.workspace.model}</Text>
      </Card>
      
      <View style={styles.nextSteps}>
        <Text style={styles.subtitle}>What's Next?</Text>
        <Text>• Send your first mandate</Text>
        <Text>• Create custom agents</Text>
        <Text>• Configure tools & integrations</Text>
        <Text>• Explore the dashboard</Text>
      </View>
      
      <Button
        onPress={() => {
          // Reset navigation to main app
          navigation.reset({
            index: 0,
            routes: [{name: 'MainApp'}]
          });
        }}
      >
        Get Started
      </Button>
    </View>
  );
}
```

---

## Setup Wizard Navigation Flow

```
Welcome
  ├─ Create Account → Email/Password/Name
  └─ Login → Existing account
      ↓
Choose Workspace Slug → my-workspace
      ↓
Select Plan → Starter/Pro
      ↓
Payment (WebView) → Stripe checkout
      ↓
Activating Workspace → Provision OpenClaw (15-30s)
      ↓
Generate Pairing Code → Auto-pair (background)
      ↓
Quick Setup → Phone/Timezone/Notifications (optional)
      ↓
Setup Complete → Show summary & next steps
      ↓
Main App → Dashboard ready!
```

---

## Progress Tracking

**Save progress at each step** so users can resume if interrupted:

```typescript
// Progress state
type SetupProgress = {
  step: 'welcome' | 'account' | 'slug' | 'plan' | 'payment' | 'activation' | 'pairing' | 'preferences' | 'complete';
  completed_steps: string[];
  tenant_id?: string;
  workspace_slug?: string;
  selected_plan?: string;
};

// Store progress
await SecureStore.setItemAsync('setup_progress', JSON.stringify(progress));

// Resume on app restart
const savedProgress = await SecureStore.getItemAsync('setup_progress');
if (savedProgress) {
  const progress = JSON.parse(savedProgress);
  
  // Resume from last step
  if (progress.step !== 'complete') {
    navigation.navigate('Setup', {screen: progress.step});
  }
}
```

---

## Error Handling in Setup Wizard

**Common Issues:**

1. **Email Already Registered**:
```jsx
if (error.message.includes('already registered')) {
  Alert.alert(
    'Account Exists',
    'This email is already registered. Would you like to login instead?',
    [
      {text: 'Login', onPress: () => navigate('Login')},
      {text: 'Try Different Email', style: 'cancel'}
    ]
  );
}
```

2. **Slug Taken**:
```jsx
if (!available) {
  setSuggestedSlugs([
    `${slug}1`,
    `${slug}-workspace`,
    `${name.toLowerCase()}-workspace`
  ]);
}
```

3. **Payment Failed**:
```jsx
// Webhook from Stripe will update tenant status
// App polls tenant status and shows retry if payment failed
if (tenant.status === 'PAYMENT_FAILED') {
  Alert.alert(
    'Payment Failed',
    'There was an issue processing your payment',
    [
      {text: 'Try Again', onPress: () => navigate('Payment')},
      {text: 'Contact Support'}
    ]
  );
}
```

4. **Activation Timeout**:
```jsx
if (activationTimeout) {
  Alert.alert(
    'Taking Longer Than Expected',
    'Your workspace is still being set up. You can close this and we\'ll email you when it\'s ready.',
    [
      {text: 'Continue Waiting'},
      {text: 'I\'ll Wait for Email', onPress: () => navigate('MainApp')}
    ]
  );
}
```

---

## Backend Endpoints Needed

### New Endpoints to Create:

**1. Check Slug Availability**
```python
# /app/backend/routes/tenants.py
@tenant_router.get("/check-slug/{slug}")
async def check_slug_availability(slug: str):
    # Validate format
    if not re.match(r'^[a-z0-9-]{3,30}$', slug):
        return {"available": False, "reason": "invalid_format"}
    
    # Check if taken
    existing = await db.tenants.find_one({"workspace_slug": slug})
    reserved = await db.slug_reservations.find_one({"slug": slug})
    
    if existing or reserved:
        return {"available": False, "reason": "taken"}
    
    return {"available": True}
```

**2. User Preferences**
```python
# /app/backend/routes/user.py (create new file)
@router.patch("/preferences")
async def update_user_preferences(data: dict, request: Request):
    user = await get_current_user(request)
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "phone_number": data.get("phone_number"),
            "timezone": data.get("timezone", "UTC"),
            "notifications_enabled": data.get("notifications_enabled", True),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Preferences updated"}
```

---

## Setup Wizard Design Guidelines

**UI/UX Principles:**

1. **Progress Indicator**: Show steps (1 of 8, 2 of 8, etc.)
2. **Skip Options**: Allow skipping non-critical steps
3. **Back Navigation**: Let users go back to previous steps
4. **Auto-Save**: Save progress automatically
5. **Clear CTAs**: Big, obvious "Continue" buttons
6. **Visual Feedback**: Loading states, success animations
7. **Error Recovery**: Clear error messages with retry options

**Estimated Time for User:**
- Account creation: 1 minute
- Slug selection: 30 seconds
- Plan selection: 1 minute
- Payment: 2 minutes
- Activation: 30 seconds (automated)
- Pairing: 10 seconds (automated)
- Preferences: 1 minute (optional)

**Total**: ~6 minutes to complete setup

---

## Testing Checklist

**Setup Wizard Flow:**
- [ ] New user can create account
- [ ] Slug validation works
- [ ] Plan selection displays correctly
- [ ] Stripe payment completes
- [ ] Workspace activates successfully
- [ ] Pairing happens automatically
- [ ] User lands in main app with working dashboard

**Error Scenarios:**
- [ ] Duplicate email handled
- [ ] Taken slug shows suggestions
- [ ] Payment failure allows retry
- [ ] Activation timeout handled gracefully

---

## Implementation Estimate

**Setup Wizard (MyndLens Team):**
- Screens: 3-4 days
- API integration: 1-2 days
- Error handling: 1 day
- Testing: 1-2 days

**Total**: 6-9 days

**Backend (ObeGee - Already 90% Done):**
- Add `/check-slug` endpoint: 30 minutes
- Add `/user/preferences` endpoint: 30 minutes
- **Total**: 1 hour

---

**This addendum completes the specification. MyndLens users can now sign up, subscribe, and configure their workspace entirely from the mobile app without ever opening a web browser.**
