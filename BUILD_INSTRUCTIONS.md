# MyndLens Mobile App — Build Instructions

## Pre-requisites
- Node.js 18+
- Yarn
- EAS CLI: `npm install -g eas-cli`
- Expo account linked: `eas login`

## Clean Build (Recommended)

When you encounter git conflicts or build issues, always start fresh:

```bash
# 1. Ensure you're on the latest code
cd /path/to/myndlens-p
git fetch origin
git reset --hard origin/main

# 2. Install dependencies
yarn install

# 3. Bump version (creates a new commit)
yarn bump

# 4. Push the bump commit to keep remote in sync
git push origin main

# 5. Build
eas build --platform android --profile production
```

## Why `yarn bump` Causes Conflicts

`yarn bump` modifies `android/app/build.gradle` (incrementing versionCode) and commits it.
If your local branch has diverged from `origin/main`, this commit creates a merge conflict.

**Solution:** Always `git reset --hard origin/main` before running `yarn bump`.

## After Build

1. Download the APK from the EAS build dashboard
2. Install on device via `adb install` or share link
3. Verify the version number matches what was bumped

## Common Issues

| Issue | Fix |
|-------|-----|
| `CONFLICT in build.gradle` | `git reset --hard origin/main && yarn install && yarn bump` |
| `yarn bump` fails | Check `bump-version.js` exists. Ensure `.gitignore` doesn't ignore `build.gradle`. |
| EAS build fails | Run `eas build --platform android --profile production --clear-cache` |
| APK blocked by Play Protect | Expected on test builds. Tap "Install anyway". |
