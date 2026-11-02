# Release verification with preserved evidence

Keep checkouts, environments, references and reports inside the active conversation workspace. Repository-backed source remains in Git; customer PDF/ZIP references stay ignored and must match the established preservation hashes.

For the established full gate, install requirements-dev.txt and Chromium. On a host with sufficient capacity, use:

    PYTEST_ADDOPTS='-n 4 --dist loadfile' python scripts/run_factory_tests.py

This runs the unchanged release script and all manifest tests. File-based distribution keeps a test file's fixtures and order together. tests/conftest.py creates a separate throwaway database/export directory in every worker. Use fewer workers on smaller hosts. Do not run against production records.

Persist evidence outside ephemeral compute: exact commit/tree, dependency fingerprint, original-reference hashes, collected test identities, per-case reports, final JUnit and process exit status. Live progress is provisional; the final JUnit is authoritative. Save reports after completion and checkpoint during long runs. A checkpoint never authorizes deployment by itself.

Before calling the gate passed, require exit0, zero failures/errors/skips, all worker collections identical, and a one-to-one match between collected identities and final JUnit cases. No missing, extra or duplicate cases. Preserve unknown/incomplete cases as unverified after interruption. Reuse previous evidence only when source, collection, dependencies and references match; never infer a pass from a percentage or an interrupted console log.

The November2 runtime candidate completed all3393 cases in892.667 seconds using four workers. The original source's fast/protected baselines and unchanged runtime candidate's GitHub workflows were already verified and were not unnecessarily repeated. See release_evidence/ebook-recovery-1.9.67.json. Metadata-only relocking is checked separately before merge; production behavior is not silently changed after its full gate.
