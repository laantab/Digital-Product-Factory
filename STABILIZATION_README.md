# Digital Product Factory stabilization foundation

This package establishes one repeatable release gate across Ebook, Word Search,
Crossword, Coloring Book, covers, save/download naming, and shared product QA.
Tests block external network traffic and require zero skipped acceptance tests.

## First setup on Windows

1. Open a terminal in this `flask_app` folder.
2. Create a virtual environment: `python -m venv .venv`
3. Activate it: `.venv\Scripts\activate`
4. Install exact dependencies: `python -m pip install -r requirements-dev.txt`
5. Double-click `Run_Factory_Preflight.bat`.
6. When it passes, double-click `Initialize_Factory_Git.bat` once to create the
   first recoverable source checkpoint.

Do not copy a real `.env` into a ZIP or Git commit. Use `.env.example` only.

## Required change workflow

Run the preflight before a repair. Change one product family. Run the preflight
again. Reject the change if any test fails or skips. For product-output changes,
also walk through the customer UI and inspect the actual downloaded PDF and ZIP.

The release gate does not start Flask, generate a paid image, call OpenAI, call
Tavily, or create a customer product.
