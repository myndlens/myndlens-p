/**
 * Digital Self Media Enrichment
 *
 * Runs async in the background after DS setup.
 * Collects photos + documents → sends to ObeGee /api/ds/enrich
 * ObeGee forwards each item to the tenant's OpenClaw (moonshot/kimi-k2.5)
 * for relationship + synopsis extraction.
 *
 * User is NOT blocked. Push notification fires when complete.
 */

const MAX_PHOTOS    = 30;   // max photos per enrichment run
const MAX_DOCS      = 20;   // max documents per enrichment run
const PHOTO_QUALITY = 0.4;  // compress before sending (balance quality vs token size)
const MONTHS_BACK   = 12;   // how far back to look for photos

// ── Main entry point ──────────────────────────────────────────────────────────

export async function runMediaEnrichment(params: {
  obegeeUrl: string;
  authToken: string;
  tenantId: string;
  pushToken: string | null;
}): Promise<void> {
  const { obegeeUrl, authToken, tenantId, pushToken } = params;

  try {
    const items: any[] = [];

    // 1. Collect photos
    const photos = await collectPhotos();
    items.push(...photos);

    // 2. Collect documents
    const docs = await collectDocuments();
    items.push(...docs);

    if (items.length === 0) {
      console.log('[DSEnrich] No media items to send');
      return;
    }

    console.log(`[DSEnrich] Sending ${items.length} items for enrichment`);

    // 3. POST to ObeGee (fire-and-forget — backend handles async processing)
    const r = await fetch(`${obegeeUrl}/api/ds/enrich/${tenantId}`, {
      method:  'POST',
      headers: { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json' },
      body:    JSON.stringify({ items, push_token: pushToken }),
    });

    if (r.ok) {
      const d = await r.json();
      console.log(`[DSEnrich] Job started: ${d.job_id}, total: ${d.total}`);
      // Store job_id for status polling
      const { setItem } = require('../utils/storage');
      await setItem('ds_enrich_job_id', d.job_id);
      await setItem('ds_enrich_tenant', tenantId);
    }
  } catch (err) {
    console.log('[DSEnrich] Error (non-fatal):', err);
  }
}


// ── Photo collection ──────────────────────────────────────────────────────────

async function collectPhotos(): Promise<any[]> {
  try {
    const MediaLibrary = require('expo-media-library');
    // Check existing permission — do NOT prompt again here.
    // Permission is requested once during DS setup wizard.
    const { status } = await MediaLibrary.getPermissionsAsync();
    if (status !== 'granted') {
      console.log('[DSEnrich] Photos: permission not granted — skipping');
      return [];
    }

    const cutoff = Date.now() - MONTHS_BACK * 30 * 24 * 60 * 60 * 1000;

    const { assets } = await MediaLibrary.getAssetsAsync({
      mediaType:  MediaLibrary.MediaType.photo,
      sortBy:     [MediaLibrary.SortBy.creationTime],
      first:      MAX_PHOTOS,
      createdAfter: cutoff,
    });

    if (!assets || assets.length === 0) return [];

    const FileSystem = require('expo-file-system/legacy');
    const ImageManipulator = require('expo-image-manipulator');
    const items: any[] = [];

    for (const asset of assets) {
      try {
        // Get the actual file URI
        const info = await MediaLibrary.getAssetInfoAsync(asset);
        const uri  = info.localUri || info.uri;

        // Compress + resize to reduce base64 size
        const resized = await ImageManipulator.manipulateAsync(
          uri,
          [{ resize: { width: 800 } }],
          { compress: PHOTO_QUALITY, format: ImageManipulator.SaveFormat.JPEG }
        );

        const base64 = await FileSystem.readAsStringAsync(resized.uri, {
          encoding: 'base64',
        });

        // Clean up temp file
        FileSystem.deleteAsync(resized.uri, { idempotent: true }).catch(() => {});

        items.push({
          type:      'photo',
          content:   base64,
          mime_type: 'image/jpeg',
          filename:  asset.filename,
          taken_at:  new Date(asset.creationTime).toISOString(),
        });
      } catch (e) {
        // Skip individual failures silently
      }
    }

    console.log(`[DSEnrich] Collected ${items.length} photos`);
    return items;
  } catch (err) {
    console.log('[DSEnrich] Photo collection failed (non-fatal):', err);
    return [];
  }
}


// ── Document collection ───────────────────────────────────────────────────────

async function collectDocuments(): Promise<any[]> {
  try {
    const FileSystem = require('expo-file-system/legacy');
    const items: any[] = [];

    // Known document directories on Android
    const DOC_DIRS = [
      FileSystem.documentDirectory,
      // Android external storage paths (accessed via content URI in newer APIs)
    ];

    for (const dir of DOC_DIRS) {
      if (!dir) continue;
      try {
        const files = await FileSystem.readDirectoryAsync(dir);
        for (const file of files.slice(0, MAX_DOCS)) {
          const ext = file.split('.').pop()?.toLowerCase();
          if (!['pdf', 'txt', 'docx', 'doc', 'xlsx', 'xls', 'csv'].includes(ext || '')) continue;

          try {
            const uri  = `${dir}${file}`;
            const info = await FileSystem.getInfoAsync(uri);
            if (!info.exists || info.size > 500_000) continue;  // skip files > 500KB

            // Read as text (works for txt, csv; limited for binary formats)
            let text = '';
            if (['txt', 'csv'].includes(ext || '')) {
              text = await FileSystem.readAsStringAsync(uri, { encoding: 'utf8' });
            } else {
              // For PDFs/DOCXs — read as base64 for backend extraction
              text = await FileSystem.readAsStringAsync(uri, { encoding: 'base64' });
            }

            items.push({
              type:      'document',
              content:   text,
              mime_type: ext === 'pdf' ? 'application/pdf' : 'text/plain',
              filename:  file,
            });
          } catch { /* skip */ }
        }
      } catch { /* skip dir */ }
    }

    console.log(`[DSEnrich] Collected ${items.length} documents`);
    return items;
  } catch (err) {
    console.log('[DSEnrich] Document collection failed (non-fatal):', err);
    return [];
  }
}


// ── Poll for completion (called from loading.tsx background) ──────────────────

export async function pollEnrichmentStatus(params: {
  obegeeUrl: string;
  authToken: string;
  tenantId: string;
}): Promise<void> {
  const { obegeeUrl, authToken, tenantId } = params;
  const { getItem, setItem } = require('../utils/storage');

  const jobId = await getItem('ds_enrich_job_id');
  const done  = await getItem('ds_enrich_done');
  if (!jobId || done === 'true') return;

  const maxPolls = 120;  // 120 × 30s = 1 hour max
  let   polls    = 0;

  const poll = async () => {
    polls++;
    if (polls > maxPolls) return;
    try {
      const r = await fetch(`${obegeeUrl}/api/ds/enrich-status/${tenantId}`, {
        headers: { 'Authorization': `Bearer ${authToken}` },
      });
      if (!r.ok) return;
      const d = await r.json();

      if (d.status === 'done') {
        await setItem('ds_enrich_done', 'true');

        // Show local push notification
        if (d.count > 0) {
          try {
            const Notifications = require('expo-notifications');
            await Notifications.scheduleNotificationAsync({
              content: {
                title: 'Digital Self Updated',
                body:  `${d.count} insights extracted from your photos & documents.`,
                data:  { type: 'ds_enrichment_complete' },
              },
              trigger: null,  // show immediately
            });
          } catch { /* notifications may not be permitted */ }
        }
        console.log(`[DSEnrich] Complete. ${d.count} nodes extracted.`);
      } else if (d.status === 'running') {
        // Keep polling every 30 seconds
        setTimeout(poll, 30_000);
      }
    } catch { /* silent */ }
  };

  // Start polling after 10 seconds
  setTimeout(poll, 10_000);
}
