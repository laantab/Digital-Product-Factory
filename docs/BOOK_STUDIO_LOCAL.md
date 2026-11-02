# Book Studio supplied-manuscript milestone

This is the reconstructed, isolated local engine. Existing Factory routes,
customer projects and production services are unchanged. It is not a fix claim
for the legacy 70 percent stall and is not a completed topic generator.

## Start on Windows

Extract the complete repository to a separate folder and double-click
`Start_Book_Studio.bat`. It creates its own virtual environment and stores data
under `%LOCALAPPDATA%\DigitalProductFactoryPro\BookStudio`. Open
http://127.0.0.1:5088 and create a local account. Those credentials are separate
from the hosted Factory. The launcher has not been executed on Windows here.

Keep the worker window open while a book is processing. You can close the
browser: processing does not depend on the page. After a PC shutdown, open the
launcher again. Saved chapters are reused; an interrupted active claim becomes
available after its finite lease expires. If the worker is missing, creation
refuses before starting a book, and saved running work shows waiting for service.

## Create a supplied-text book

Enter a title, author and one of three designs. Paste at least two chapters,
starting each with `## Chapter title`. Each needs 250 to 8000 words and at least
three developed paragraphs. Review the actual PDF pages, then approve the
edition to enable PDF, complete ZIP and editable Markdown downloads.

This path preserves supplied prose and performs structural/file-integrity
checks. It does not claim AI generation, copyediting, plagiarism checking or
fact verification. Those and photographs, EPUB/DOCX, chapter revision/version
controls and KDP preparation remain later reconstruction stages.

## Command line

Use a separate local data directory for all three commands:

```
python -m services.ebook_v2.cli init --data /your/separate/studio-data
python -m services.ebook_v2.cli worker --data /your/separate/studio-data
python -m services.ebook_v2.cli serve --data /your/separate/studio-data
```

The last two run in separate terminals. Server binding is loopback-only.
There is no main-app registration, schema cutover or production configuration
change. Hosted PostgreSQL/R2 parity and deployment are not certified.

## Proof

```
python -m pytest -q tests/test_ebook_v2_recovery.py tests/test_ebook_v2_books.py tests/test_ebook_v2_customer_path.py
```

The supplied fixture is original acceptance text explicitly labeled NOT FOR
SALE. Real HTTP and browser acceptance use an independent CLI worker. The
browser case stops that worker after one chapter is saved, closes the page,
restarts the worker and reopens the saved book. It checks the original chapter
was not repeated, then approves and downloads actual PDF/ZIP bytes. HTTP checks
verify signatures, response checksums, CRC, embedded/standalone PDF equality,
authentication, ownership, CSRF and read-only status behavior. No paid calls.

## Local topic writing checkpoint
Choose Write from my topic, provide audience and reader outcome, and select
Automatic or Manual. The local Ollama service must be installed and running
withqwen3:8b (the default) before a topic attempt can start. It is never pulled
silently by the app. Source settings can be configured through
FACTORY_V2_OLLAMA_MODEL and a loopback-only FACTORY_V2_OLLAMA_URL. No cloud or
paid fallback is allowed. The worker checks installed model metadata separately
from the browser.

This checkpoint explicitly requires acknowledging that market demand has not
been assessed. Automatic mode asks for title and cover/theme choices. Manual
mode also asks for outline and final-page approval. Local editorial checks
review grammar, relevance, consistency and cautious claims; they do not certify
external facts or plagiarism absence. Short outputs retain their draft and
receive bounded expansion attempts. Code-owned remedies are learned only when
the repaired output passes validation.

The actual small CPU-model pilot is engineering evidence with stated limits,
not a benchmark of the owner's8B model/GPU or a publication-ready product.

## Editable manuscripts and retained editions
Finished books include PDF, EPUB, editable Word and Markdown manuscripts, a
cover JPEG, and a ZIP containing matching copies. In Review or Ready, choose
Edit manuscript and view editions. Save new edition keeps the original book
and downloads, checks the exact revised text, and requires approval before the
new downloads are released. Existing AI chapter work is retained in the original
book; owner edits do not trigger automatic rewriting. Saved editions can be
reopened from the same editor. Two tabs cannot silently overwrite one another.
