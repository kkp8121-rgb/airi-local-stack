# Local replay campaign operator checklist

All boxes are intentionally blank. Complete each one for the actual local study; do not record names, handles, source IDs, prompts, or response text in the manifest or campaign report.

- [ ] Verify written permission covers this specific capture, paired replay, human review, and local retention period.
- [ ] Confirm export and revocation status immediately before the campaign; stop if authorization has changed.
- [ ] Keep the actual source-to-`channel_a`/`channel_b`/`channel_c` mapping only in the protected local operator record.
- [ ] Capture only an authorized local export or an explicitly approved official API/SDK session. Do not scrape a VOD/player page, use unofficial endpoints, or import third-party dumps.
- [ ] For an official YouTube live API capture, verify the API project/privacy notice and deletion process, keep the API key only in ignored local custody, exclude pre-capture history, and set `delete_by` no later than 30 days after capture start.
- [ ] Do not combine YouTube API data from unrelated content owners into the multi-source campaign unless the applicable platform/content-owner authorization explicitly permits that use; keep an otherwise valid capture as a separate diagnostic.
- [ ] Complete human privacy review before model replay; remove or stop on content outside the approved scope.
- [ ] Use the same protected local identity key for normalization, paired replay, human scoring, and campaign validation; never copy the key into a manifest or report.
- [ ] Record content-free source observations (atmosphere, pace, context pressure, dominant patterns) locally.
- [ ] Run each exact capture once with epistemic confidence OFF and once ON in an exclusive local-model session.
- [ ] Have an operator or authorized reviewer complete every response review and record critical failure categories.
- [ ] Create a fresh UTC attestation with a validity window no longer than 24 hours, then aggregate while valid.
- [ ] Treat any campaign critical-gate failure as a stop: do not switch operating behavior or adopt automatically. Obtain explicit user confirmation for any later decision.
