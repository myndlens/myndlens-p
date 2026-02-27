#!/usr/bin/env node
/**
 * bump-version.js
 * Pulls latest remote, increments versionCode in android/app/build.gradle,
 * syncs app.json, then commits immediately.
 *
 * Usage: yarn bump
 * This replaces the manual workflow of: git pull && edit files && git commit
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_ROOT = path.join(__dirname, '../..');
const GRADLE   = path.join(__dirname, '../android/app/build.gradle');
const APP_JSON  = path.join(__dirname, '../app.json');

// ── Step 1: Pull latest so we never operate on stale versionCode ────────────
console.log('Pulling latest from remote…');
try {
  // Detect remote name (may be 'origin' or 'myndlens' depending on setup)
  const remote = execSync('git remote', { cwd: REPO_ROOT }).toString().trim().split('\n')[0] || 'origin';
  execSync(`git pull --rebase ${remote} main`, { cwd: REPO_ROOT, stdio: 'inherit' });
} catch (e) {
  console.error('❌ git pull --rebase failed. Commit or stash local changes first.');
  process.exit(1);
}

// ── Step 2: Read current values ─────────────────────────────────────────────
const gradle  = fs.readFileSync(GRADLE, 'utf8');
const appJson = JSON.parse(fs.readFileSync(APP_JSON, 'utf8'));

const codeMatch = gradle.match(/versionCode\s+(\d+)/);
const nameMatch = gradle.match(/versionName\s+"([^"]+)"/);

if (!codeMatch || !nameMatch) {
  console.error('❌ Could not parse versionCode/versionName from build.gradle');
  process.exit(1);
}

const oldCode   = parseInt(codeMatch[1], 10);
const newCode   = oldCode + 1;
const oldVersionName = nameMatch[1];

// Auto-increment patch version: 1.0.9 → 1.0.10
const vParts = oldVersionName.split('.');
vParts[2] = String(parseInt(vParts[2] || '0', 10) + 1);
const versionName = vParts.join('.');

// ── Step 3: Write new values ─────────────────────────────────────────────────
fs.writeFileSync(GRADLE, gradle
  .replace(/versionCode\s+\d+/, `versionCode ${newCode}`)
  .replace(/versionName\s+"[^"]+"/, `versionName "${versionName}"`)
);

appJson.expo.version               = versionName;
appJson.expo.android               = appJson.expo.android || {};
appJson.expo.android.versionCode   = newCode;
appJson.expo.ios                   = appJson.expo.ios || {};
appJson.expo.ios.buildNumber       = String(newCode);
fs.writeFileSync(APP_JSON, JSON.stringify(appJson, null, 2) + '\n');

// ── Step 4: Commit immediately ───────────────────────────────────────────────
try {
  execSync(`git add -f frontend/android/app/build.gradle frontend/app.json`, { cwd: REPO_ROOT, stdio: 'inherit' });
  execSync(`git commit -m "chore: bump versionCode ${oldCode} → ${newCode}"`, { cwd: REPO_ROOT, stdio: 'inherit' });
} catch (e) {
  console.error('❌ git commit failed:', e.message);
  process.exit(1);
}

console.log(`\n✅ Ready to build:`);
console.log(`   versionCode  ${oldCode} → ${newCode}`);
console.log(`   versionName  ${oldVersionName} → ${versionName}`);
console.log(`\n   eas build --platform android --profile production\n`);
