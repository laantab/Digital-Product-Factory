# Start here — v1.9.52 full release proof

This record supersedes the missing-reference blocker in the earlier October20 editorial and mindfulness handoffs. Lonnie explicitly approved using the uploaded completed Room-by-Room package as the required preservation reference. The original Project351 expected hashes remain unchanged and are still checked when either legacy reference file exists; incomplete legacy pairs fail. The new required reference cannot skip when absent or pass with replacement bytes. Its customer files remain gitignored and are not published.

## Verified source and acceptance

Runtime/test source a6343fb4491c830330fc721bd6d77842744e5010 has tree 4baaae21b7911ac0443d2045bb1471440cb9e398, identical to local ae63f62. All 3,253 unique acceptance cases across all 232 manifest files passed: zero failures, errors, skipped, missing, extra or duplicates. Python compilation and JavaScript syntax passed. Tests blocked external network and paid-provider calls.

The first full six-shard execution caught one missing required changelog heading. Only CHANGELOG.md changed to repair that failure. All 31 version/documentation checks passed and the entire 478-case affected shard was repeated successfully; the five other full shards passed. The original failing report and the clean repeated shard are both retained. No assertion was weakened or failed case omitted. Evidence: release_evidence/v1.9.52-full-release.json and v1.9.52-full-release-tests.tar.gz.

Room-by-Room PDF SHA256: 20792e8fcce4ab4fcc7daa8e49df1d0a634f7c624d9197d346d0fda83f8d025d.
ZIP SHA256: f7cc37a90f71e8563039c412f23f7ba11deff52edb055419117197921d572d26.
The uploaded original and staged reference remain byte-identical; ZIP CRC passes and embedded PDF matches. This is preservation evidence for the older book, not a quality verdict on upgraded output.

## Release and live acceptance

Publish metadata, merge PR74, and independently verify website srv-da8qisegekts7380vdvg and builder wfl-damqq8uk1f9s738jtgc0 in the already-confirmed workspace. Both track main; builder read-only logs verified checkout of main on the preceding release. Do not manually redeploy while automatic deployment is active. Keep production configuration, billing and credentials unchanged. Deployment results belong in PR74's latest body; inspect it before repeating work.

At the start of release, project11 Mindfulness in Motion remains failed at visuals, updated_at 2026-10-20T21:21:49.080480+00:00 (version33). Project20 remains updated_at 2026-10-18T14:01:14.127997+00:00 (version406). No production project was changed or resumed by verification. After deployment, the customer's existing Resume Build action can recover the saved visuals stage. Reuse accepted chapters. Verify the real finished PDF/ZIP before claiming the customer book is complete. Existing title/cover/picture decisions remain intact.

Billing/PR73 and unfinished dual-mode work remain separate. Protected coloring, puzzle and planner implementations were not changed. No additional provider spending was authorized.
