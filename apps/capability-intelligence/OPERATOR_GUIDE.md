# Operator Guide

> Filled in batch-by-batch as features ship.

## TOC

1. Sign-in — Batch 1
2. Configure sources — Batch 1
3. Pull all sources — Batch 1
4. Save a catalogue version — Batch 1
5. Diff two versions and read the narrative — Batch 1
6. Review change flags — Batch 1
7. Review AI suggestions — Batch 4
8. Read a benchmark distribution + adversary verdict — Batch 5
9. Move a subcap through lifecycle — Batch 6
10. Export a client journey for the DMA App — Batch 6
11. Read the Quarterly Strategic Digest — Batch 7
12. Switch persona — Batch 8
13. Run a What-If simulation — Batch 8

## 1. Sign in

In dev: requests use `Authorization: Bearer dev-<email>` where the email must
end in the configured `AUTH_ALLOWED_DOMAIN` (default `zennify.com`). The web
client wires this automatically; pytest sends it via the `auth_headers`
fixture. Production sign-in (Batch 9) is Firebase Google sign-in restricted
to the same domain.

## 2. Configure sources

After running `scripts/setup.sh`, share the Drive pillars folder
(`1rF9zdx1qF7BJ9t21eFdvZQW11Y5dUjy3` or your own) with the printed service
account email. Confirm in **Settings** that the folder ID and project are
populated. For local dev, set `LOCAL_CATALOGUE_DIR=apps/capability-intelligence/test-data`
to point at the bundled Pillar 1 file.

## 3. Pull all sources

In **Mission Control**, click **Refresh all** in the "Pillar source files"
panel. Each pillar gets re-discovered (latest non-inactive version), parsed,
and persisted. Per-pillar refresh is also available alongside each row.

## 4. Save a catalogue version

Open **Version Timeline**, fill optional label/summary, click **Save
version**. The current state of every subcap and pillar is snapshotted; the
new version becomes "current".

## 5. Diff two versions

**Diff Viewer** lets you pick A and B from the version dropdowns. The grid
shows added / removed / modified subcaps with field-level changes plus
pillar-count deltas and category deltas. Narrative explanation lands in
Batch 4 (Gemini 2.5 Pro).

## 6. Review change flags

**Change Flags Inbox** lists open flags (mapping regressions, theme
alignment, schema-incomplete pillars, ingest failures). Each shows
severity, kind, target, detail, and a Resolve button.

(Steps 7-13 ship in later batches per the TOC above.)
