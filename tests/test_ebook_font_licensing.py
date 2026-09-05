"""The face embedded in a sold ebook must be one we may redistribute.

Until v1.4.1 the ebook font loader preferred C:\\Windows\\Fonts\\arial.ttf and
copied it into services/fonts as "EbookSans-*.ttf". That put Monotype Arial
inside every customer PDF, under a name that hid which font it was. These tests
fail the build if that can happen again.

Generic by design: nothing here is specific to one project or one book.
"""
from __future__ import annotations

import os
import pathlib
import struct
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "services" / "fonts"

# Families we hold no redistribution licence for.
PROPRIETARY_NAMES = (
    "arial",
    "calibri",
    "times new roman",
    "georgia",
    "verdana",
    "tahoma",
    "segoe",
    "cambria",
    "helvetica neue",
    "monotype",
)

# A filename that tells you nothing about whose font it is.
DISGUISED_STEMS = ("ebooksans", "bodyfont", "customfont", "brandsans")


def _ttf_name_table(path: pathlib.Path) -> dict[int, str]:
    """Read the TrueType 'name' table without a font library."""
    data = path.read_bytes()
    if data[:4] not in (b"\x00\x01\x00\x00", b"true", b"ttcf", b"OTTO"):
        return {}
    num_tables = struct.unpack(">H", data[4:6])[0]
    offset = 12
    name_tab = None
    for _ in range(num_tables):
        tag = data[offset : offset + 4]
        tab_off, tab_len = struct.unpack(">II", data[offset + 8 : offset + 16])
        offset += 16
        if tag == b"name":
            name_tab = (tab_off, tab_len)
            break
    if not name_tab:
        return {}
    base, _ = name_tab
    count, string_off = struct.unpack(">HH", data[base + 2 : base + 6])
    out: dict[int, str] = {}
    for i in range(count):
        rec = data[base + 6 + 12 * i : base + 6 + 12 * i + 12]
        if len(rec) < 12:
            continue
        pid, _eid, _lid, nid, length, str_o = struct.unpack(">HHHHHH", rec)
        raw = data[base + string_off + str_o : base + string_off + str_o + length]
        try:
            value = raw.decode("utf-16-be") if pid == 3 else raw.decode("latin-1")
        except (UnicodeDecodeError, ValueError):
            continue
        out.setdefault(nid, value)
    return out


class BundledFontLicensingTests(unittest.TestCase):
    def test_no_proprietary_face_is_bundled(self):
        """Every shipped .ttf must self-identify as a font we may redistribute."""
        offenders = []
        for path in sorted(FONT_DIR.glob("*.ttf")):
            names = _ttf_name_table(path)
            declared = " ".join(names.get(k, "") for k in (1, 4, 8)).lower()
            for marker in PROPRIETARY_NAMES:
                if marker in declared:
                    offenders.append(f"{path.name} declares '{names.get(1)}' by '{names.get(8)}'")
                    break
        self.assertEqual(
            offenders,
            [],
            "proprietary font bundled in services/fonts: " + "; ".join(offenders),
        )

    def test_no_disguised_font_filenames(self):
        """A font file must keep its real name, so provenance stays auditable."""
        bad = [
            p.name
            for p in FONT_DIR.glob("*.ttf")
            if any(stem in p.stem.lower() for stem in DISGUISED_STEMS)
        ]
        self.assertEqual(bad, [], f"renamed font files hide provenance: {bad}")

    def test_licence_and_provenance_ship_with_the_fonts(self):
        self.assertTrue((FONT_DIR / "OFL.txt").is_file(), "OFL.txt missing")
        provenance = FONT_DIR / "FONT-PROVENANCE.md"
        self.assertTrue(provenance.is_file(), "FONT-PROVENANCE.md missing")
        text = provenance.read_text(encoding="utf-8")
        for required in ("Liberation Sans", "SIL Open Font License", "2.1.5", "SHA-256"):
            self.assertIn(required, text, f"provenance does not record {required}")

    def test_ofl_text_is_the_real_licence(self):
        ofl = (FONT_DIR / "OFL.txt").read_text(encoding="utf-8")
        self.assertIn("SIL OPEN FONT LICENSE Version 1.1", ofl)
        self.assertIn("PERMISSION & CONDITIONS", ofl)
        self.assertIn("TERMINATION", ofl)


class FontResolutionTests(unittest.TestCase):
    def test_loader_never_reads_the_system_font_directory(self):
        """A host that has Arial installed must not be able to leak it into a product."""
        src = (ROOT / "services" / "ebook_fonts.py").read_text(encoding="utf-8")
        body = src[src.index("def ebook_font_paths") : src.index("def materialize_ebook_font_files")]
        lowered = body.lower()
        # Reading an OS font directory, or naming a proprietary face, are the two
        # ways a host-installed font gets into a customer PDF.
        forbidden = (
            "windir",
            "os.environ",
            "c:\\windows",
            "/system/library/fonts",
            "/usr/share/fonts",
            "arial",
            "calibri",
            "segoe",
        )
        for token in forbidden:
            # The docstring may name Arial when explaining the history; only the
            # executable body is checked.
            code = lowered.split('"""')[-1]
            self.assertNotIn(token, code, f"ebook_font_paths still reaches for {token!r}")

    def test_resolved_faces_are_liberation(self):
        from services.ebook_fonts import ebook_font_paths

        for face, path in ebook_font_paths().items():
            self.assertIsNotNone(path, f"{face} face did not resolve")
            self.assertIn("Liberation", os.path.basename(path), f"{face} resolved to {path}")

    def test_registered_font_names_are_honest(self):
        from services.ebook_fonts import ensure_ebook_fonts

        for name in ensure_ebook_fonts():
            self.assertTrue(
                name.startswith("LiberationSans"),
                f"PDF would embed the face under the misleading name {name!r}",
            )

    def test_materialize_does_not_rename_fonts(self):
        from services.ebook_fonts import materialize_ebook_font_files

        for face, path in materialize_ebook_font_files().items():
            self.assertIn("Liberation", os.path.basename(path), f"{face} materialized as {path}")

    def test_gitignore_ships_liberation_but_not_arbitrary_faces(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("services/fonts/*.ttf", ignore)
        for face in ("Regular", "Bold", "Italic", "BoldItalic"):
            self.assertIn(f"!services/fonts/LiberationSans-{face}.ttf", ignore)


class EveryBuilderEmbedsOnlyLicensedFontsTests(unittest.TestCase):
    """The ebook was not the only product embedding a proprietary face.

    Crossword and math-worksheet PDFs resolved their TrueType face by looking in
    C:\\Windows\\Fonts. Neither had a bundled fonts directory, so both fell
    through to Monotype Arial and embedded it into products that are sold.

    This is deliberately a scan of every font resolver in services/, not a list
    of the two that were wrong, so a new product builder cannot quietly
    reintroduce the same pattern.
    """

    #: Substrings that mean "read a font from wherever this machine keeps them".
    OS_FONT_LOOKUPS = (
        "windir",
        "c:\\windows",
        "/system/library/fonts",
        "/usr/share/fonts",
        "~/library/fonts",
    )
    #: Proprietary faces by filename stem.
    PROPRIETARY_FILES = (
        "arial", "calibri", "segoeui", "tahoma", "verdana",
        "cambria", "georgia", "times.ttf", "timesbd", "comic", "impact",
    )

    def _font_modules(self) -> list[pathlib.Path]:
        found = [p for p in (ROOT / "services").rglob("*.py") if "font" in p.name.lower()]
        self.assertTrue(found, "no font modules found — has the layout changed?")
        return found

    @staticmethod
    def _executable_code(path: pathlib.Path) -> str:
        """Source with docstrings and comments removed.

        These modules describe in prose exactly which proprietary faces they
        used to reach for, so a naive text scan flags the explanation as if it
        were the offence. Only real code is checked.
        """
        import ast as _ast

        source = path.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        blanked: set[int] = set()
        try:
            tree = _ast.parse(source)
        except SyntaxError:
            return source.lower()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Expr) and isinstance(node.value, _ast.Constant):
                if isinstance(node.value.value, str):
                    end = node.value.end_lineno or node.value.lineno
                    blanked.update(range(node.value.lineno, end + 1))
        kept = [
            line.split("#", 1)[0]
            for i, line in enumerate(lines, start=1)
            if i not in blanked
        ]
        return "\n".join(kept).lower()

    def test_no_builder_reads_the_os_font_directory(self):
        offenders = []
        for path in self._font_modules():
            code = self._executable_code(path)
            for token in self.OS_FONT_LOOKUPS:
                if token in code:
                    offenders.append(f"{path.relative_to(ROOT)} -> {token!r}")
        self.assertEqual(
            offenders, [],
            "a product builder resolves fonts from this machine, which embeds "
            "whatever face happens to be installed: " + "; ".join(offenders),
        )

    def test_no_builder_names_a_proprietary_font_file(self):
        offenders = []
        # A deny-list of family names is legitimate and looks identical to a
        # lookup unless the surrounding context is considered. Only flag a
        # proprietary name that is being used to BUILD A PATH to a font file.
        path_context = ("os.path.join", ".ttf", "fonts_dir", "\\fonts", "/fonts")
        for path in self._font_modules():
            for line in self._executable_code(path).splitlines():
                if not any(marker in line for marker in path_context):
                    continue
                for stem in self.PROPRIETARY_FILES:
                    if stem in line:
                        offenders.append(f"{path.relative_to(ROOT)} -> {stem}: {line.strip()[:60]}")
        self.assertEqual(
            offenders, [],
            "a builder resolves a path to a proprietary font file: " + "; ".join(offenders),
        )

    def test_crossword_and_math_resolve_to_the_shared_licensed_family(self):
        from services.crossword.pdf_fonts import _font_candidates as crossword_faces
        from services.math_worksheet.pdf_fonts import _font_candidates as math_faces

        for label, faces in (("crossword", crossword_faces()), ("math worksheet", math_faces())):
            for path in faces:
                self.assertIsNotNone(path, f"{label} face did not resolve")
                self.assertIn(
                    "Liberation", os.path.basename(str(path)),
                    f"{label} resolved to {path}, which is not the licensed family",
                )

    def test_one_shared_family_serves_every_builder(self):
        """A second copy of the fonts is a second thing to get wrong."""
        copies = [p for p in (ROOT / "services").rglob("Liberation*.ttf")]
        dirs = {p.parent for p in copies}
        self.assertEqual(
            len(dirs), 1,
            f"the licensed family is duplicated across {len(dirs)} directories: {sorted(map(str, dirs))}",
        )


if __name__ == "__main__":
    unittest.main()
