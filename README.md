# Blaze's Cook Book

An installable PWA (Progressive Web App) version of Blaze's batch-cooking recipe & nutrition tracker.

Live at: https://shahulblaze.github.io/Blaze-Cookbook/

## Install on Android
1. Open the link above in Chrome.
2. Tap the ⋮ menu → **Add to Home screen** (or **Install app** if offered).
3. Launch it from your home screen — it opens full-screen and keeps working offline.

## What it does
- **Recipes** — the batch-cooking book, per-100 g macros, servings scaler, checklists
- **Intake** — log shop products by barcode + grams, or a dish by weight or by portion of the batch
- **Create** — build your own recipe from scanned, pantry or general ingredients, with optional steps
- **Pantry** — every product you've scanned or typed in, plus the list of ingredients the recipes need

Barcodes are looked up in Open Food Facts (free, no key). Cooked weight is estimated from how much
of the added water simmers off; logging by portion avoids weighing altogether.

## Files
- `index.html` — the app (recipes, servings scaler, nutrition engine, checklists)
- `manifest.json` — PWA metadata (name, icons, display mode)
- `sw.js` — service worker for offline caching
- `icon-*.png` — app icons

State (ticks, servings, ingredient edits) is saved locally in the browser via `localStorage` and is per-device.
