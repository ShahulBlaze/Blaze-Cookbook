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

Barcodes can be scanned live or read from a gallery photo, and are looked up in Open Food Facts (free, no key).
Every product in Open Food Facts (worldwide; ones without figures get their category's average, marked as an estimate) is built into the app as an
offline copy (`scripts/build_off_db.py`, rebuilt weekly by the deploy workflow), so lookups are instant and
work without signal. Product data © Open Food Facts contributors, ODbL.
Per-100 g uses raw ingredient weight; logging by portion of the batch avoids weighing altogether.

## Files
- `index.html` — the app (recipes, servings scaler, nutrition engine, checklists)
- `manifest.json` — PWA metadata (name, icons, display mode)
- `sw.js` — service worker for offline caching
- `icon-*.png` — app icons
- `scripts/build_off_db.py` — builds the offline product database from the Open Food Facts export
- `.github/workflows/deploy.yml` — builds the database weekly and deploys to GitHub Pages

State (ticks, servings, ingredient edits) is saved locally in the browser via `localStorage` and is per-device.
