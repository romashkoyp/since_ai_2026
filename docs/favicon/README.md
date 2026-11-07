# ZeroFault Favicon Set

All files in this directory were generated directly from [`docs/logo/logo.svg`](../logo/logo.svg) as the single source of truth for the ZeroFault brand mark.

## File Inventory

| Filename | Purpose | Size / Format |
| :--- | :--- | :--- |
| **`favicon.svg`** | Scalable modern browser favicon (dark theme background) | Vector SVG |
| **`favicon-mark-transparent.svg`** | Scalable transparent favicon | Vector SVG |
| **`favicon.ico`** | Legacy & multi-resolution favicon bundle | 16x16, 32x32, 48x48 ICO |
| **`favicon-16x16.png`** | Standard tab icon | 16x16 PNG |
| **`favicon-32x32.png`** | Standard tab icon (Retina) | 32x32 PNG |
| **`favicon-48x48.png`** | Desktop / browser shortcut | 48x48 PNG |
| **`apple-touch-icon.png`** | iOS Home Screen icon | 180x180 PNG |
| **`android-chrome-192x192.png`** | Android PWA / mobile launcher | 192x192 PNG |
| **`android-chrome-512x512.png`** | Android splash / PWA store | 512x512 PNG |
| **`site.webmanifest`** | Progressive Web App manifest | JSON |

---

## HTML Integration Snippet for Frontend (`<head>`)

When ready to integrate into the frontend `index.html`:

```html
<!-- Favicons -->
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
<link rel="manifest" href="/site.webmanifest" />
<meta name="theme-color" content="#14181E" />
```

