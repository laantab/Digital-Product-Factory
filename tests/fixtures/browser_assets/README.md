# Local browser assets for the real-browser tests

`templates/index.html` loads four things from the internet. The real-browser
tests (`tests/test_ebook_real_browser_customer_path.py`) serve these local
copies instead, so they check the same styled, working page on any machine,
with or without internet access:

| Page requests | Served from here | What it is |
|---|---|---|
| `https://cdn.tailwindcss.com` | `factory-tailwind.css` (injected as a `<style>`) | Tailwind v3 styles compiled from the app's own templates, scripts and `tailwind.config` theme |
| `https://cdn.jsdelivr.net/npm/marked/marked.min.js` | `marked-15.0.12.min.js` | The exact file that URL serves (marked v15.0.12, MIT) |
| `https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js` | `jszip-3.10.1.min.js` | JSZip 3.10.1 (MIT or GPLv3), from the npm package |
| `https://fonts.googleapis.com/css2?family=Inter...` | an empty stylesheet | Only the Inter web font; the page falls back to the system font |

Rebuild the Tailwind file after adding new Tailwind classes to the app:

```
npx tailwindcss@3.4.19 -c tests/fixtures/browser_assets/tailwind.config.js -i tests/fixtures/browser_assets/tailwind-input.css -o tests/fixtures/browser_assets/factory-tailwind.css --minify
```
