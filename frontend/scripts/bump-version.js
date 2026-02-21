#!/usr/bin/env node
/**
 * bump-version.js
 * Auto-increments versionCode in android/app/build.gradle and syncs app.json.
 * Run before every EAS build: yarn bump
 */

const fs = require('fs');
const path = require('path');

const GRADLE = path.join(__dirname, '../android/app/build.gradle');
const APP_JSON = path.join(__dirname, '../app.json');

// ── Read current values ─────────────────────────────────────────────────────
const gradle = fs.readFileSync(GRADLE, 'utf8');
const appJson = JSON.parse(fs.readFileSync(APP_JSON, 'utf8'));

const codeMatch = gradle.match(/versionCode\s+(\d+)/);
const nameMatch = gradle.match(/versionName\s+"([^"]+)"/);

if (!codeMatch || !nameMatch) {
  console.error('❌ Could not parse versionCode/versionName from build.gradle');
  process.exit(1);
}

const oldCode = parseInt(codeMatch[1], 10);
const newCode = oldCode + 1;
const versionName = nameMatch[1]; // versionName stays the same (manual semver bump)

// ── Update build.gradle ─────────────────────────────────────────────────────
const newGradle = gradle
  .replace(/versionCode\s+\d+/, `versionCode ${newCode}`);
fs.writeFileSync(GRADLE, newGradle);

// ── Update app.json ─────────────────────────────────────────────────────────
appJson.expo.version = versionName;
appJson.expo.android = appJson.expo.android || {};
appJson.expo.android.versionCode = newCode;
appJson.expo.ios = appJson.expo.ios || {};
appJson.expo.ios.buildNumber = String(newCode);
fs.writeFileSync(APP_JSON, JSON.stringify(appJson, null, 2) + '\n');

console.log(`✅ Version bumped: versionCode ${oldCode} → ${newCode}  (versionName: ${versionName})`);
console.log(`   build.gradle updated`);
console.log(`   app.json updated`);

// ── Commit immediately so git pull never conflicts ──────────────────────────
const { execSync } = require('child_process');
try {
  execSync(`git -C "${path.join(__dirname, '../..')}" add frontend/android/app/build.gradle frontend/app.json`, { stdio: 'inherit' });
  execSync(`git -C "${path.join(__dirname, '../..')}" commit -m "chore: bump versionCode to ${newCode}"`, { stdio: 'inherit' });
  console.log(`   committed to git`);
} catch (e) {
  console.error('❌ git commit failed:', e.message);
  process.exit(1);
}
