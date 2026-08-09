"""Generate a fixture crossword PDF for visual inspection — NO AI calls.

Uses mode=custom_word_list with pre-defined words and clues so the entire
rendering pipeline runs without any OpenAI/Tavily calls.
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))

from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from pdf2image import convert_from_path

OUTPUT_DIR = r"C:\Users\user\Desktop\The Factory"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Fixture: Garden Vegetables — 3 puzzles, 6 words each, no AI involved
FIXTURE_PUZZLES = [
    {
        "words": "CARROT\nPOTATO\nTOMATO\nLETTUCE\nONION\nCELERY",
        "clues": {
            "CARROT": "Orange root vegetable good for your eyes.",
            "POTATO": "Starchy tuber grown underground.",
            "TOMATO": "Red fruit often used in salads.",
            "LETTUCE": "Leafy green used in salads and sandwiches.",
            "ONION": "Bulb with strong flavor and many layers.",
            "CELERY": "Pale green vegetable with crunchy stalks.",
        },
    },
    {
        "words": "BROCCOLI\nSPINACH\nPEPPER\nPEAS\nCORN\nBEANS",
        "clues": {
            "BROCCOLI": "Green tree-like vegetable with florets.",
            "SPINACH": "Dark leafy green rich in iron.",
            "PEPPER": "Garden vegetable in sweet or hot varieties.",
            "PEAS": "Small round green vegetables often in a pod.",
            "CORN": "Yellow kernels on a cob.",
            "BEANS": "Seeds from a pod, often eaten cooked.",
        },
    },
    {
        "words": "MUSHROOM\nSQUASH\nCUCUMBER\nRADISH\nASPARAGUS\nEGGPLANT",
        "clues": {
            "MUSHROOM": "Fungus with a cap and stem.",
            "SQUASH": "Vegetable that grows on a vine.",
            "CUCUMBER": "Cool green vegetable in salads.",
            "RADISH": "Peppery root vegetable.",
            "ASPARAGUS": "Green spears harvested in spring.",
            "EGGPLANT": "Purple vegetable used in cooking.",
        },
    },
]

def main():
    all_words = []
    all_clues = {}
    for puz in FIXTURE_PUZZLES:
        for word in puz["words"].strip().split("\n"):
            w = word.strip().upper()
            if w:
                all_words.append(w)
                all_clues.update(puz["clues"])

    request = CrosswordPdfRequest(
        product_title="Garden Vegetable Puzzles",
        subtitle="Fun Crossword Puzzles for Everyone",
        theme="Garden Vegetables",
        sub_topic="Garden Vegetables",
        difficulty="easy",
        grid_size=15,
        number_of_puzzles=3,
        mode="custom_word_list",
        custom_words="\n".join(all_words),
        custom_clues=all_clues,
        include_answer_key=True,
        output_type="book",
        words_per_puzzle=6,
        include_cover=True,
        seed=42,
    )

    print("Building fixture crossword PDF (no AI calls)...")
    result = build_crossword_pdf(request)

    print(f"  pdf_bytes: {len(result.pdf_bytes):,} bytes")
    print(f"  puzzles: {len(result.puzzles)}")
    print(f"  errors: {result.errors}")
    print(f"  warnings: {result.warnings}")
    if result.qa_report:
        print(f"  QA passed: {result.qa_report.passed}")
        print(f"  QA blocked_export: {result.qa_report.blocked_export}")
        print(f"  QA errors: {result.qa_report.errors}")

    if not result.pdf_bytes:
        print("ERROR: No PDF generated!")
        return

    # Save PDF
    pdf_path = os.path.join(OUTPUT_DIR, "fixture_garden_vegetables_crossword.pdf")
    with open(pdf_path, "wb") as f:
        f.write(result.pdf_bytes)
    print(f"\nPDF saved: {pdf_path}")

    # Render to images
    print("\nRendering PDF to images...")
    pages = convert_from_path(
        pdf_path,
        dpi=100,
        first_page=1,
        last_page=min(8, 20),
        fmt="png",
    )

    img_paths = []
    for i, page in enumerate(pages, start=1):
        img_path = os.path.join(OUTPUT_DIR, f"fixture_page_{i:02d}.png")
        page.save(img_path, "PNG")
        img_paths.append(img_path)
        print(f"  Page {i}: {img_path}")

    print(f"\n{len(img_paths)} pages rendered. Ready for visual inspection.")
    print("Pages to inspect: cover (1), puzzle 1 (2-3), puzzle 2 (~middle), puzzle 3 (near end), answer key (last)")

if __name__ == "__main__":
    main()
