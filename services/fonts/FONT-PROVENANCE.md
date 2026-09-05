# Ebook font provenance

The Factory embeds this family into every customer ebook PDF. Because those PDFs
are sold, the font must be one we are licensed to **redistribute** (ship inside
the repository) and to **embed** in a commercial document. Liberation Sans is.

## Shipped family

| Face | File | SHA-256 |
|---|---|---|
| Regular | `LiberationSans-Regular.ttf` | `8d91388f1d3604b3b8ae0e3ee2d140e50cd6122f9214514f4aca772540a4076d` |
| Bold | `LiberationSans-Bold.ttf` | `ba0e0dc3f7aca5b0afbc31e800531ee43be3aa79ae35b2ef1f6470a9547765c4` |
| Italic | `LiberationSans-Italic.ttf` | `01f559e5c501d3d5777647c6a92b3ff37a4523bcf4f3b6e97ae052af567618b1` |
| Bold Italic | `LiberationSans-BoldItalic.ttf` | `15c1068175252e4adee6d3721bf74064ffe437f679d9dbaeacd03fa7711a041b` |

- **Family:** Liberation Sans
- **Version:** 2.1.5
- **Upstream project:** https://github.com/liberationfonts
- **Obtained from:** Debian/Ubuntu package `fonts-liberation2`, version `2.1.5-1`
- **Licence:** SIL Open Font License 1.1 — full text in `OFL.txt` (this directory)
- **Copyright:** Digitized data copyright (c) 2010 Google Corporation with
  Reserved Font Names Arimo, Tinos and Cousine. Copyright (c) 2012 Red Hat, Inc.
  with Reserved Font Name Liberation.

The OFL permits bundling these files with the Factory and embedding them in the
PDFs customers buy. The only OFL restriction that touches us: the font files
must not be sold on their own, and a *modified* version may not keep the
reserved name "Liberation". We ship them unmodified, so neither applies.

## Why Liberation Sans

It is metric-compatible with Arial. Replacing the previous font therefore left
line breaks and pagination essentially unchanged, so the contents page and page
numbers stayed correct without a redesign.

## What this replaced, and why

Until v1.4.1 this directory held `EbookSans-regular.ttf`, `-bold.ttf`,
`-italic.ttf` and `-bold_italic.ttf`. Despite the name, those files were
**Monotype Arial** — copied out of `C:\Windows\Fonts` by
`materialize_ebook_font_files()` and renamed. Their internal name table still
read `Arial` / `The Monotype Corporation`, version 7.06.

Scope of the problem, stated precisely:

- Those files were **not** committed to git. `.gitignore` line `services/fonts/*.ttf`
  kept them untracked, and `git ls-tree HEAD` confirms nothing under
  `services/fonts/` was ever in the tree. So this was not a case of proprietary
  font files being redistributed through the repository.
- The real exposure was **embedding**: `ebook_font_paths()` preferred
  `C:\Windows\Fonts\arial.ttf`, so Arial was embedded in every ebook PDF the
  Factory produced for sale. A Windows licence lets you use Arial on that
  machine; it does not by itself cover redistributing it inside a commercial
  product.
- Secondary: the renamed copies were swept into the desktop backup archives
  (`GOOGLE_DRIVE_BACKUP.zip`, `factory-backup.zip`), which do travel.

Embedding a font in a PDF is ordinary and lawful when the licence allows it.
What was wrong here was embedding *this particular* proprietary face in a sold
product without a Monotype licence covering that use, under a name that
concealed which font it was.

The removed files are preserved outside the repository at
`Desktop\Factory Backup\project351_backup_20260904_211737\arial_fonts_removed\`
for recovery only. Do not return them to the repository.

`ebook_font_paths()` no longer looks in `C:\Windows\Fonts` at all, so a Windows
machine that happens to have Arial installed can no longer pull it back into a
customer product. `tests/test_ebook_font_licensing.py` fails the build if a
proprietary face reappears in `services/fonts/` or in the font search order.
