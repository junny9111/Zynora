# Creator publishing release

Backend applied to the existing Zynora Supabase project:

- Each signed-in creator owns their series and submissions.
- One new series per UTC calendar month; existing series accept more episodes.
- Server assigns creator identity and pending review. Direct ownership and publication edits are denied.
- Uploads accept MP4/WebM up to 50 MiB; covers JPEG/PNG/WebP up to 5 MiB.
- Creator videos are private. Playback requires a free published episode, an existing unlock, or ownership.
- Paid coins bought after rollout are attributed FIFO to episode unlocks. Verified live PayPal net proceeds are split 80% creator / 20% platform. Sandbox proceeds are zero.
- Legacy and reward coins do not receive an invented cash valuation. Earnings remain provisional, with no automatic payout or refund webhook installed.

Frontend changes prepared:

- Profile → Creator Studio link.
- Account-specific series selector, quota explanation, upload validation, ownership declaration, pending status, preview, title edits and earnings display.
- Home and Discover exclude pending submissions.

Verification:

- tests/creator-security.sql executes within a transaction and rolls back every test row. Passed: ownership isolation; moderation; quota; private catalog access; locked playback; idempotent unlock; 80/20 split; net amount reconciliation.
- tests/creator-ui.test.cjs passed: file types, size limits, empty files, sanitization and signed-out upload gating.
- creator.js syntax check and git diff whitespace check passed.

Owner review currently uses Supabase Table Editor → episodes. Review the video in Storage, then set is_published=true to approve. To request changes, set is_published=false, review_status=rejected and review_note to the explanation. Creators cannot set these values through the app.

Still required before calling the entire app launch-ready:

1. Publish these frontend files to GitHub Pages and verify the live UI and a real upload.
2. Complete a real PayPal sandbox checkout test in the user's account.
3. Configure payment dispute/refund webhooks and creator payouts before offering cash withdrawals. No funds are transferred by this release.
4. Connect a rewarded-ad provider before enabling ad rewards. AI series production remains a separate existing workflow.

The SQL files are applied deployment records, not rerunnable migrations. Do not rerun creator-platform.sql on the existing project.
