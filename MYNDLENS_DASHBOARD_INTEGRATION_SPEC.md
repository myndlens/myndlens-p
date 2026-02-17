# MyndLens-ObeGee Dashboard Integration Specification

**Version**: 2.0  
**Date**: February 17, 2026  
**Purpose**: Enable full ObeGee dashboard functionality within MyndLens mobile app

---

## Overview

This specification enables MyndLens users to access ALL ObeGee dashboard features directly from the mobile app, eliminating the need for web browser access. Users can configure their workspace, manage tools/models, view usage, and access settings entirely within MyndLens.

---

## Architecture

```
┌──────────────────────────────────────────┐
│  MyndLens Mobile App (iOS/Android)      │
│  ┌────────────────────────────────────┐ │
│  │  Dashboard Tab                     │ │
│  │  ├─ Workspace Overview             │ │
│  │  ├─ Usage/Billing                  │ │
│  │  ├─ Tools Configuration            │ │
│  │  ├─ Model Settings (BYOK)          │ │
│  │  ├─ Agents List                    │ │
│  │  └─ [Full Dashboard] (WebView)     │ │
│  └────────────────────────────────────┘ │
└──────────────┬───────────────────────────┘
               │ HTTPS API Calls
               ↓
┌──────────────────────────────────────────┐
│  ObeGee Backend (obegee.co.uk)          │
│  ┌────────────────────────────────────┐ │
│  │  /api/myndlens-dashboard/*         │ │
│  │  ├─ POST /auth/extend-pairing      │ │
│  │  ├─ GET  /workspace/config         │ │
│  │  ├─ PATCH /workspace/tools         │ │
│  │  ├─ PATCH /workspace/model         │ │
│  │  ├─ GET  /workspace/agents         │ │
│  │  ├─ GET  /workspace/usage          │ │
│  │  └─ GET  /dashboard-url (WebView)  │ │
│  └────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

---

## Authentication Flow

### Phase 1: Pairing (Already Implemented)

1. User enters 6-digit code in MyndLens
2. MyndLens calls `POST /api/myndlens/pair` with code
3. Receives standard pairing token (30-day expiry)

### Phase 2: Extended API Access (NEW)

**Endpoint**: `POST /api/myndlens-dashboard/auth/extend-pairing`

**Request:**
```json
{
  "code": "123456",
  "device_id": "unique-device-id"
}
```

**Response:**
```json
{
  "api_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 2592000,
  "tenant": {
    "tenant_id": "tenant_xxx",
    "workspace_slug": "myworkspace",
    "status": "READY",
    "name": "My Workspace"
  },
  "endpoints": {
    "myndlens_ws": "ws://138.68.179.111:18791",
    "gateway": "http://138.68.179.111:10010"
  }
}
```

**MyndLens Implementation:**
```typescript
// Store token securely
await SecureStore.setItemAsync('obegee_api_token', response.api_token);
await SecureStore.setItemAsync('tenant_id', response.tenant.tenant_id);
await SecureStore.setItemAsync('myndlens_ws_url', response.endpoints.myndlens_ws);
```

---

## API Endpoints (ObeGee-Side)

### 1. Get Workspace Configuration

**Endpoint**: `GET /api/myndlens-dashboard/workspace/config`  
**Auth**: Bearer token (from pairing)

**Response:**
```json
{
  "workspace": {
    "tenant_id": "tenant_xxx",
    "slug": "myworkspace",
    "name": "My Workspace",
    "status": "READY",
    "model": "moonshot/kimi-k2.5"
  },
  "subscription": {
    "plan_id": "early_bird_pro",
    "status": "active",
    "current_period_end": "2026-03-17T00:00:00Z"
  },
  "tools": {
    "enabled": ["web-browser", "file-system", "data-analysis"]
  },
  "approval_policy": {
    "auto_approve_low": true,
    "auto_approve_medium": false
  },
  "integrations": ["google_oauth"],
  "runtime": {
    "status": "running",
    "port": 10010,
    "myndlens_port": 18791
  }
}
```

**MyndLens UI (React Native):**
```jsx
// Dashboard Overview Screen
<View>
  <Text>Workspace: {config.workspace.slug}</Text>
  <Text>Plan: {config.subscription.plan_id}</Text>
  <Text>Status: {config.workspace.status}</Text>
  <Text>Model: {config.workspace.model}</Text>
</View>
```

### 2. Update Tools Configuration

**Endpoint**: `PATCH /api/myndlens-dashboard/workspace/tools`  
**Auth**: Bearer token

**Request:**
```json
{
  "enabled_tools": ["web-browser", "file-system", "email", "code-execution"]
}
```

**Response:**
```json
{
  "message": "Tools updated",
  "enabled_tools": ["web-browser", "file-system", "email", "code-execution"]
}
```

**MyndLens UI:**
```jsx
// Tools Configuration Screen
<ScrollView>
  {AVAILABLE_TOOLS.map(tool => (
    <Switch
      key={tool.id}
      value={enabledTools.includes(tool.id)}
      onValueChange={() => toggleTool(tool.id)}
      label={tool.name}
      description={tool.description}
      riskLevel={tool.risk_level}
    />
  ))}
  <Button onPress={saveToolsConfig}>Save Changes</Button>
</ScrollView>
```

### 3. Update Model/API Key (BYOK)

**Endpoint**: `PATCH /api/myndlens-dashboard/workspace/model`  
**Auth**: Bearer token

**Request:**
```json
{
  "provider": "moonshot",
  "api_key": "sk-..."
}
```

**Response:**
```json
{
  "message": "API key updated",
  "provider": "moonshot"
}
```

**MyndLens UI:**
```jsx
// Model Settings Screen
<View>
  <Picker
    selectedValue={provider}
    onValueChange={setProvider}>
    <Picker.Item label="Kimi K2.5 (Moonshot)" value="moonshot" />
    <Picker.Item label="OpenAI GPT-4" value="openai" />
  </Picker>
  
  <TextInput
    placeholder="API Key (sk-...)"
    secureTextEntry
    value={apiKey}
    onChangeText={setApiKey}
  />
  
  <Button onPress={testAndSaveKey}>Test & Save</Button>
</View>
```

### 4. Get Agents List

**Endpoint**: `GET /api/myndlens-dashboard/workspace/agents`  
**Auth**: Bearer token

**Response:**
```json
{
  "agents": [
    {
      "id": "python-coder",
      "name": "Python Developer",
      "model": "moonshot/kimi-k2.5",
      "status": "active",
      "skills": ["python-dev", "file-operations"],
      "tools": ["read", "write", "exec"]
    }
  ],
  "total": 1
}
```

**MyndLens UI:**
```jsx
// Agents Screen
<FlatList
  data={agents}
  renderItem={({item}) => (
    <Card>
      <Text style={styles.title}>{item.name}</Text>
      <Text>Model: {item.model}</Text>
      <Text>Skills: {item.skills.join(', ')}</Text>
      <Badge color={item.status === 'active' ? 'green' : 'gray'}>
        {item.status}
      </Badge>
    </Card>
  )}
/>
```

### 5. Get Usage Statistics

**Endpoint**: `GET /api/myndlens-dashboard/workspace/usage`  
**Auth**: Bearer token

**Response:**
```json
{
  "today": {
    "messages": 45,
    "tokens": 12453,
    "tool_calls": 8
  },
  "limits": {
    "messages": 500,
    "tokens": 100000
  },
  "subscription": {
    "plan_name": "Pro",
    "status": "active"
  }
}
```

**MyndLens UI:**
```jsx
// Usage Screen
<View>
  <ProgressBar
    progress={usage.today.messages / usage.limits.messages}
    label="Messages"
    current={usage.today.messages}
    max={usage.limits.messages}
  />
  <ProgressBar
    progress={usage.today.tokens / usage.limits.tokens}
    label="Tokens"
    current={usage.today.tokens}
    max={usage.limits.tokens}
  />
  <Text>Plan: {usage.subscription.plan_name}</Text>
</View>
```

### 6. WebView Fallback

**Endpoint**: `GET /api/myndlens-dashboard/dashboard-url`  
**Auth**: Bearer token

**Response:**
```json
{
  "webview_url": "https://obegee.co.uk/dashboard?token=eyJhbG...",
  "expires_in": 3600
}
```

**MyndLens Implementation:**
```jsx
// Full Dashboard Button
<Button
  title="Open Full Dashboard"
  onPress={async () => {
    const response = await fetch(
      'https://obegee.co.uk/api/myndlens-dashboard/dashboard-url',
      {headers: {Authorization: `Bearer ${apiToken}`}}
    );
    const {webview_url} = await response.json();
    
    navigation.navigate('WebViewDashboard', {url: webview_url});
  }}
/>

// WebView Screen
<WebView
  source={{uri: route.params.url}}
  injectedJavaScript={AUTO_LOGIN_SCRIPT}
  onMessage={handleDashboardMessage}
/>
```

---

## MyndLens App Structure

### Screens

**1. Dashboard Home**
- Workspace overview card
- Quick stats (usage, agents, status)
- Quick actions (chat, create agent, settings)

**2. Workspace Settings**
- Tools configuration
- Model/API key management
- Approval policy settings
- Integration management

**3. Agents & Skills**
- List all agents
- View agent details (skills, tools, activity)
- Create new agent (via mandate)

**4. Usage & Billing**
- Real-time usage charts
- Subscription info
- Payment method
- Upgrade/downgrade

**5. Full Dashboard (WebView)**
- Fallback for complex operations
- Embedded browser with auto-login
- Seamless navigation

### Navigation

```
Bottom Tab Navigator:
├─ 🏠 Home (Chat + Mandates)
├─ 🤖 Agents
├─ ⚙️ Settings
└─ 📊 Dashboard
```

---

## Implementation Steps (MyndLens Dev Team)

### Phase 1: API Integration (2-3 days)

**Step 1**: Extend pairing flow
```typescript
// After successful 6-digit pairing
const extendedAuth = await fetch(
  'https://obegee.co.uk/api/myndlens-dashboard/auth/extend-pairing',
  {
    method: 'POST',
    body: JSON.stringify({code, device_id})
  }
);

await SecureStore.setItemAsync('api_token', extendedAuth.api_token);
```

**Step 2**: Create API client
```typescript
// services/ObeGeeAPI.ts
class ObeGeeAPI {
  private apiToken: string;
  private baseURL = 'https://obegee.co.uk/api/myndlens-dashboard';
  
  async getWorkspaceConfig() {
    return await this.fetch('/workspace/config');
  }
  
  async updateTools(tools: string[]) {
    return await this.fetch('/workspace/tools', {
      method: 'PATCH',
      body: JSON.stringify({enabled_tools: tools})
    });
  }
  
  async updateModel(provider: string, apiKey: string) {
    return await this.fetch('/workspace/model', {
      method: 'PATCH',
      body: JSON.stringify({provider, api_key: apiKey})
    });
  }
  
  private async fetch(path: string, options = {}) {
    const response = await fetch(this.baseURL + path, {
      ...options,
      headers: {
        'Authorization': `Bearer ${this.apiToken}`,
        'Content-Type': 'application/json',
        ...options.headers
      }
    });
    
    if (!response.ok) throw new Error(`API error: ${response.status}`);
    return response.json();
  }
}
```

### Phase 2: Dashboard UI (3-4 days)

**Screen 1: Dashboard Home**
```jsx
function DashboardHome() {
  const [config, setConfig] = useState(null);
  
  useEffect(() => {
    loadConfig();
  }, []);
  
  async function loadConfig() {
    const data = await obeGeeAPI.getWorkspaceConfig();
    setConfig(data);
  }
  
  return (
    <ScrollView>
      <Card title="Workspace">
        <Text>{config?.workspace.slug}</Text>
        <Badge>{config?.workspace.status}</Badge>
      </Card>
      
      <Card title="Today's Usage">
        <ProgressCircle
          value={config?.usage.today.messages}
          max={config?.usage.limits.messages}
          label="Messages"
        />
      </Card>
      
      <Card title="Model">
        <Text>{config?.workspace.model}</Text>
        <Button onPress={() => navigate('ModelSettings')}>
          Change Model
        </Button>
      </Card>
    </ScrollView>
  );
}
```

**Screen 2: Tools Configuration**
```jsx
function ToolsConfig() {
  const [tools, setTools] = useState([]);
  const [enabled, setEnabled] = useState([]);
  
  async function saveTools() {
    await obeGeeAPI.updateTools(enabled);
    Alert.alert('Success', 'Tools configuration updated');
  }
  
  return (
    <View>
      <FlatList
        data={AVAILABLE_TOOLS}
        renderItem={({item}) => (
          <ListItem>
            <Switch
              value={enabled.includes(item.id)}
              onValueChange={() => toggleTool(item.id)}
            />
            <View>
              <Text>{item.name}</Text>
              <Text style={styles.description}>{item.description}</Text>
              <Badge color={getRiskColor(item.risk_level)}>
                {item.risk_level}
              </Badge>
            </View>
          </ListItem>
        )}
      />
      <Button onPress={saveTools}>Save Changes</Button>
    </View>
  );
}
```

**Screen 3: Model Settings (BYOK)**
```jsx
function ModelSettings() {
  const [provider, setProvider] = useState('moonshot');
  const [apiKey, setApiKey] = useState('');
  const [testing, setTesting] = useState(false);
  
  async function testAndSave() {
    setTesting(true);
    try {
      // Test key validity first
      const valid = await testAPIKey(provider, apiKey);
      if (!valid) {
        Alert.alert('Invalid Key', 'Please check your API key');
        return;
      }
      
      // Save to ObeGee
      await obeGeeAPI.updateModel(provider, apiKey);
      Alert.alert('Success', 'API key updated successfully');
    } catch (error) {
      Alert.alert('Error', error.message);
    } finally {
      setTesting(false);
    }
  }
  
  return (
    <View>
      <Picker
        selectedValue={provider}
        onValueChange={setProvider}>
        <Picker.Item label="Kimi K2.5 (Moonshot)" value="moonshot" />
        <Picker.Item label="OpenAI GPT-4" value="openai" />
        <Picker.Item label="Anthropic Claude" value="anthropic" />
      </Picker>
      
      <TextInput
        placeholder="API Key (sk-...)"
        value={apiKey}
        onChangeText={setApiKey}
        secureTextEntry
      />
      
      <Button
        onPress={testAndSave}
        loading={testing}
        title={testing ? 'Testing...' : 'Test & Save'}
      />
    </View>
  );
}
```

**Screen 4: Agents List**
```jsx
function AgentsList() {
  const [agents, setAgents] = useState([]);
  
  useEffect(() => {
    loadAgents();
  }, []);
  
  async function loadAgents() {
    const data = await obeGeeAPI.getAgents();
    setAgents(data.agents);
  }
  
  async function createAgent() {
    // Send mandate artifact via existing MyndLens WS
    const mandate = {
      mandateId: `agent_${Date.now()}`,
      mandate: 'Create a new agent',
      agents: [{
        id: 'new-agent',
        name: 'New Agent',
        action: 'create',
        skills: [],
        tools: {allow: ['read', 'write']}
      }]
    };
    
    await sendMandate(mandate);
    
    // Refresh list after 20s (wait for provisioning)
    setTimeout(loadAgents, 20000);
  }
  
  return (
    <View>
      <FlatList
        data={agents}
        renderItem={({item}) => (
          <Card>
            <Text style={styles.title}>{item.name}</Text>
            <Text>Skills: {item.skills?.join(', ') || 'None'}</Text>
            <Text>Tools: {item.tools?.join(', ') || 'Default'}</Text>
          </Card>
        )}
      />
      <FAB icon="plus" onPress={createAgent} />
    </View>
  );
}
```

**Screen 5: WebView Fallback**
```jsx
function FullDashboard() {
  const [dashboardUrl, setDashboardUrl] = useState(null);
  
  useEffect(() => {
    loadDashboardUrl();
  }, []);
  
  async function loadDashboardUrl() {
    const response = await obeGeeAPI.getDashboardUrl();
    setDashboardUrl(response.webview_url);
  }
  
  return (
    <WebView
      source={{uri: dashboardUrl}}
      onMessage={(event) => {
        // Handle messages from web dashboard
        const message = JSON.parse(event.nativeEvent.data);
        if (message.type === 'config_updated') {
          // Refresh local config
          loadConfig();
        }
      }}
    />
  );
}
```

### Phase 3: Real-Time Sync (1-2 days)

**Polling Strategy:**
```typescript
// Poll config every 30 seconds when app is active
useEffect(() => {
  const interval = setInterval(async () => {
    const config = await obeGeeAPI.getWorkspaceConfig();
    setConfig(config);
  }, 30000);
  
  return () => clearInterval(interval);
}, []);
```

**WebSocket Alternative (Future):**
```typescript
// Real-time updates via WebSocket
const ws = new WebSocket(myndlens_ws_url);

ws.on('message', (data) => {
  const event = JSON.parse(data);
  
  if (event.type === 'config_updated') {
    // Refresh dashboard
    loadConfig();
  } else if (event.type === 'agent_created') {
    // Refresh agents list
    loadAgents();
  }
});
```

---

## Testing Checklist

### ObeGee Backend (Already Implemented)

- ✅ `/api/myndlens-dashboard/auth/extend-pairing` - Created
- ✅ `/api/myndlens-dashboard/workspace/config` - Created
- ✅ `/api/myndlens-dashboard/workspace/tools` - Created
- ✅ `/api/myndlens-dashboard/workspace/model` - Created
- ✅ `/api/myndlens-dashboard/workspace/agents` - Created
- ✅ `/api/myndlens-dashboard/workspace/usage` - Created
- ✅ `/api/myndlens-dashboard/dashboard-url` - Created

### MyndLens App (To Implement)

- [ ] Extended pairing flow
- [ ] Dashboard home screen
- [ ] Tools configuration screen
- [ ] Model settings screen (BYOK)
- [ ] Agents list screen
- [ ] Usage statistics screen
- [ ] WebView fallback screen
- [ ] Real-time config polling
- [ ] Secure token storage
- [ ] Error handling & retry logic

---

## Security Considerations

**Token Management:**
- Store API tokens in SecureStore/Keychain
- Refresh before expiry (30-day lifetime)
- Clear on logout

**API Key Storage:**
- Never log API keys
- Encrypt in transit (HTTPS only)
- Validate format before sending

**WebView Security:**
- Only load obegee.co.uk domain
- Disable external navigation
- Clear cookies on exit

---

## Error Handling

**Common Scenarios:**

1. **Token Expired**: Re-pair with new code
2. **Workspace Suspended**: Show upgrade prompt
3. **API Key Invalid**: Validation error with retry
4. **Network Error**: Retry with exponential backoff
5. **Config Update Failed**: Rollback UI state, show error

---

## Migration Path

**For Existing MyndLens Users:**

1. App update prompts: "New! Manage your workspace from MyndLens"
2. One-time re-pairing to get extended token
3. Dashboard features gradually roll out
4. WebView available immediately for full access

---

## API Summary Table

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/auth/extend-pairing` | POST | Get API token | ✅ Implemented |
| `/workspace/config` | GET | Get all config | ✅ Implemented |
| `/workspace/tools` | PATCH | Update tools | ✅ Implemented |
| `/workspace/model` | PATCH | Update API key (BYOK) | ✅ Implemented |
| `/workspace/agents` | GET | List agents | ✅ Implemented |
| `/workspace/usage` | GET | Get statistics | ✅ Implemented |
| `/dashboard-url` | GET | WebView URL | ✅ Implemented |

---

## Estimated Effort (MyndLens Team)

- **API Integration**: 2-3 days
- **Dashboard UI**: 3-4 days
- **Testing**: 1-2 days
- **Total**: 6-9 days

---

**All ObeGee-side APIs are now deployed and ready for MyndLens integration. Users will soon access full dashboard functionality from the mobile app.**
