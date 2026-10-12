# v1.9.21 — automatic visual recovery

## Verified code and tests

PR #39 repairs shared visual-stage defects. An uncertain stock photo previously stopped acquisition yet could not pass approval. Guided replacements used only stock retrieval, skipping the free chapter graphic fallback. The fallback missed structured lists and tables with no usable short prose. Guided recovery now uses the free path, renders its local replacement before validation, and checkpoints prepared visuals and each replacement before later approval can fail. Passing pictures and the accepted manuscript are retained. No quality gate or paid authorization is bypassed; when there is no honest local fallback, an uncertain photo still needs review and cannot trigger paid generation.

Tested production-code commit: 86db175cd912c2b2ec3778871b2cfa6b8fdbf43e. Tested source tree: 8324db97a36a2e6efc226dbb648b29a40b93baf7. The local and published source trees match exactly.

The full 211-file gate passed: 2,981 tests, zero failures, errors, or skips, in 1,329.52 seconds. Earlier preliminary verification was interrupted after the structured fallback addition; it is not reported as passing. New focused tests reproduced three original failures before the repair. The actual displayed Chapter 1 text also produced a local graphic with minimum labels about 10 pt, above the unchanged 8 pt floor. This offline graphic is not a live export or proof of overall visual approval.

Preserved reference PDF SHA-256: 6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd. ZIP SHA-256: 5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f. Both were retrieved from the original reference archive and verified before the release gate. No external or paid calls were permitted during tests.

## Live state and next step

The website was on v1.9.20. Project 20, The Room-by-Room Eco Home Makeover Checklist, has 10 chapters and 11,165 words. Its visual stage reported Chapter 1 as unfinished despite showing a stock photo. After the owner corrected UNSPLASH_ACCESS_KEY on both Render services, the website showed Try Unsplash as available. This establishes configuration detection, not successful authentication or photo acquisition. A direct replacement/resume on the old code did not establish completion.

Deploy PR #39, verify the deployed version, resume the existing project, and inspect its actual remaining findings. Quality gates remain intact: a local fallback alone does not prove that the complete set meets photo, variety, relevance, and readability requirements. Do not claim that all three reported stalled books share this exact cause without inspecting them, or that the book is finished without checking the real PDF and ZIP.

Routine commit, push, merge, and deployment of this repair are authorized. Do not initiate extra paid calls. Do not ask the owner for console commands or tests. The cloud Render sign-in reached Google recovery and a password-change requirement; the owner switched to Render in their own iPad browser. No signed-in cloud Render session was established. Password changes must be performed personally by the owner.
