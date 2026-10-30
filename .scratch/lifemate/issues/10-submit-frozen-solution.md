# 10: Submit the frozen solution package

**Parent spec:** [LifeMate competition solution](https://github.com/huyxdang/three-good-boys/issues/1)

**What to build:** The registered team submits the verified frozen solution through the official channel and retains enough receipt and checksum evidence to identify exactly what was submitted.

**Blocked by:** [09: Freeze and verify the release](09-freeze-and-verify-release.md).

**Status:** ready-for-human

**Owner:** Unclaimed

**Progress:** not-started

## Implementation steps

1. A registered member logs into the live portal and records deadline/timezone, package count, format/link rules, access requirements and checksum fields, with check date.
2. Pull ticket 09's checksum/replay evidence and resolve package-sharing access with the organizer: current Submission Guidance requests a public Google Drive link, while the handoff prohibits general public redistribution. Record the approved submission exception/access method before uploading; do not publish a link in the repository.
3. Upload only through the official channel under the team account; never place credentials or private links in public issues or the umbrella spec.
4. Wait for and observe the portal's acceptance state (not upload start); save the receipt/status and submission timestamp.
5. Record in authorized team storage: artifact identity, checksum, receipt, timestamp/timezone; add a sanitized pointer here.
6. Keep the exact submitted package immutable and copy its clean invocation for ticket 11; if an organizer-approved replacement happens, record its own identity, receipt and checksum.

## Acceptance criteria

- [ ] A registered team member checks the live portal's deadline/timezone, permitted package count, required format/link, access requirements and checksum fields. Historical handoff dates are not a substitute for this check.
- [ ] Confirm the selected frozen artifact's checksum and reproduction evidence from ticket 09, resolve the portal's public-link requirement against redistribution restrictions with the organizer, and make the approved package link accessible through the official submission channel only.
- [ ] Submit only through the official permitted channel using the registered team's credentials. Do not paste credentials, private links, or restricted package contents into the public umbrella spec.
- [ ] Record the submission time/timezone, official receipt or status, artifact identity and checksum in authorized team records; record a sanitized evidence pointer in this ticket. Confirm the portal accepted the submission rather than treating upload initiation as completion.
- [ ] Preserve the submitted immutable package and clean invocation for later private evaluation. Record any organizer-approved replacement explicitly with its own identity, receipt and checksum.

## Verification

No submission performed. Completion requires human-observed portal acceptance, the submitted artifact checksum and an authorized receipt location. Engineering agents must not fabricate receipts or bypass human authentication.

## Comments

The rendered official Submission Guidance was checked on 2026-10-28: November 16 at 23:59 GMT+7, checksum plus Google Drive link, at most two solution submissions with the last evaluated. Recheck when acting and resolve the link-access conflict in step 2. Repository configuration and ticket creation do not submit the competition solution.
