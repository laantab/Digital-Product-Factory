# Ebook chart context repair — protected candidate, not deployed

Draft PR104 contains candidate v1.9.65. Final runtime source: 1a54da9d1c95f92616ab60043c86bb99648b8afc. Only ebook chart extraction and final chart review implementation changed. No other generator implementation, production settings or customer artifacts changed. No paid provider calls.

## Repair and verified behavior

Final review missed saved “Put these…” instructions, dangling colons and inline list introductions, so existing free automatic-chart redraw recovery did not run. Final review and extraction now share context checks. Extraction also retains its original conservative prose-reference filter (“Hold this position…” must not be extracted without context). Complete named chart labels remain valid. Generated automatic charts recover only from approved chapter text and preserve prior wording in history. Owner edits remain intact; absent safe replacement text remains blocked. Actual regenerated PNG inspected with three complete retained instructions and no clipped labels.

Five regressions failed against the original implementation. An additional candidate regression exposed a loosened prose guard and was corrected before release. Final practice tests:10 passed. Initial focused review/editor suite:72 passed. Final scoped run:682 passed, with one pre-commit version-check failure; the committed source passed all56 metadata cases without changing assertions. All 611 protected cases across 34 ebook files passed. Protection is restored at the real runtime commit, including the newly declared final-review dependency. This is combined verification, not an uninterrupted green full release run.

## Release remains blocked

A prior broader run at04d3f740fa508f50205f922bc75baa5cdd81d3a8 recorded3376 passes and two failures before its execution environment disconnected. It produced no final JUnit report. Failures were the required absent original Room-by-Room preservation pair and an AI-recommended browser creation case. That browser case passed an isolated unchanged retry in105.79 seconds; the final protected run also covers the creation-mode and full browser journeys. Do not label the interrupted run successful or waive any finding.

The exact owner-supplied Room-by-Room PDF and ZIP remain required. A saved Eco Home Makeover PDF was located, but its hash differs from the expected reference and was not substituted. A matching ZIP was not located. An unauthenticated download attempt returned401; no customer record or artifact was changed. The existing CI workflow retains synthetic offline acceptance artifacts, not this original preservation pair.

Next: obtain the original pair, verify the unchanged expected hashes, rerun the unchanged full release gate, then verify deployment and actual live PDF/ZIP downloads. Keep this PR draft until that gate passes. Do not claim full live one-button completion. Keep the existing completion alert tied to its full verified acceptance criteria. See release_evidence/ebook-chart-context-candidate.json for exact evidence and source digests.

Final lock, version, manifest-coverage and Command Center verification after restoring protection:69 passed. Runtime implementation unchanged.
