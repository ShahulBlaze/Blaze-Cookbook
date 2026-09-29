# Blaze's Cook Book

An installable PWA (Progressive Web App) version of Blaze's batch-cooking recipe & nutrition tracker.

Live at: https://shahulblaze.github.io/Blaze-Cookbook/

## Install on Android
1. Open the link above in Chrome.
2. Tap the ⋮ menu → **Add to Home screen** (or **Install app** if offered).
3. Launch it from your home screen — it opens full-screen and keeps working offline.

## Files
- `index.html` — the app (recipes, servings scaler, nutrition engine, checklists)
- `manifest.json` — PWA metadata (name, icons, display mode)
- `sw.js` — service worker for offline caching
- `icon-*.png` — app icons

State (ticks, servings, ingredient edits) is saved locally in the browser via `localStorage` and is per-device.
