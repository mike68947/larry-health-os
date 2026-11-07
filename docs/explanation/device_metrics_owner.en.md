<!-- translation-of: docs/explanation/device_metrics_owner.md sha256:bd8b9bd3e457 -->
<!-- Machine translation by doc_agent --translate-intent; regenerated with the Russian page, do not edit by hand. -->
<!-- 2026-11-07: the scale paragraphs were translated by hand together with the Russian page; the next --translate-intent replaces them. -->

**English** · [Русский](device_metrics_owner.md)

# Every device metric has an owner: how the system notices what isn't visible

## What changed

- **New invariant `body_day_owner_withings`, status `open`.** Weight and body composition from a Withings scale got a second path — straight from the Withings cloud, bypassing Health and Health Auto Export. The invariant states who owns the day's weight columns and how the path behaves when a weighing is deleted or the answer is empty. The status is open: no live import from a real scale has run yet, and the measure codes come from the documentation.

- **The blood-pressure records did not change:** `bp_day_owner_withings` still `holds`, confirmed 2026-10-07.

**Updated:** 2026-11-07


## Why it exists

The device sends dozens of readings at once. If any one of them is lost along the way — the bot does not know. Digests go out, notifications work, one number just quietly disappeared. That is exactly why "everything is working" does not mean "everything arrived".

Loss can look different ways. The device sends a field under one name, and the parser expects another — and stays silent. Or the data ingestion path changed, while an old watchdog sensor keeps staring into the void and raises no alarm. From the outside, "no data" is indistinguishable from "data exists but did not arrive".

This subsystem exists for one purpose: to make such a loss visible.

## What it does, in plain terms

When data arrives, a dedicated judge examines each metric and delivers one of four verdicts.

**Handled** — the metric reached storage. This is confirmed not by a mark in the registry, but by the real behaviour of the parser: the data completed the full path.

**Tracked** — the metric is intentionally not collected, and this is recorded as an explicit decision with an explanation. If the decision states "not collected because it is covered by another column" — it is verified that on days when the metric did arrive that column was indeed non-empty. A bare label of "covered" without data confirmation does not count.

**Unowned** — the metric was parsed but is stored nowhere. This is the loss that needs to be noticed.

**New** — the metric is entirely unknown to the system.

The judge itself is watched separately. If the registry has not seen incoming data for a long time — either the ingestion path is stale or something has broken silently. Such blindness of the judge also becomes a loud alarm, not silence.

One more rule concerns empty columns. If a column is empty — that can mean "no device present". But only in one case: when the entire raw data archive contains not a single file from that source. If the source has arrived before and the column is empty — that is a loss. That is exactly why the archive is compressed but not deleted: without it, the two cases cannot be told apart.

Blood pressure is a special case. It has two independent paths. The first is through the device and the standard parser. The second is directly from the Withings cloud: each measurement with time of day and pulse. When Withings is connected, it becomes the sole owner of daily blood pressure in the final digest. The daily value is the average of all measurements over the local day, and the peak value used for alert assessment is the maximum among them. The Health path in this case does not write to those columns; instead it stores its data as a separate witness. If a measurement is deleted in the Withings app — on the next sync it disappears from the database as well. An empty response from Withings when history is non-empty is not interpreted as "no measurements" — it is treated as a failure, and data is not erased.

Weight is a similar but more modest case. A Withings scale sends its weighings to the same cloud, and through the same connection the system takes weight and body composition (fat, muscle, bone, water, visceral fat, basal metabolic rate — whatever the scale model measures). A day gets its morning, earliest weighing — the same rule as for the Fitdays scale. The owner of the day's columns is whoever wrote the weight first: a day Withings owns is kept as a mirror of the cloud (a correction in the app is written over, a deletion clears it), while a day whose weight already came from Health or Fitdays is left alone — only its empty columns are filled. An empty answer while own days exist is a failure, not a clearing.

The nightly sensor checks all of this not on the event of data arrival, but against the state of the registry. This matters: the sensor does not wait for a new file to notice a problem — it looks at what is already there and compares it with what should be there.

## What to honestly say about its limits

All described invariants hold at the time of writing. But "holds" and "verified under all possible conditions" are different claims.

**The second path for blood pressure (Withings)** is confirmed by a live import into the production database: several measurements matched Health data, the token worked, the error log was empty. But there are limits that are important to name directly.

Withings is polled twice a day. If a measurement was deleted in the app, that deletion will not reach the database until the next poll — not instantly.

Deletion mirroring — that is, removing from the database measurements that no longer exist in Withings — was added after the first import was confirmed. Not a single deletion has gone through this path in production yet.

If a given user does not have Withings connected — this path simply stays silent for them, as if the device does not exist. Blood pressure in that case is still written by Health.

**The sole owner of daily blood pressure** has been verified across several days since connection: averages hold, no foreign value has leaked through, the nightly sensor found no discrepancies. But here too there are real limits.

The day is calculated according to the timezone of the system installation, not the location of the person. If a measurement is taken at night while travelling, it may fall into the neighbouring day.

For a partner without Withings, blood pressure is still calculated differently, and measurements deleted on the device are not visible there — this is not a bug, but a different arrangement for different situations, though it is important to be aware of.

Health data for blood pressure sits as a separate witness and is not automatically cross-checked against Withings by anything. This is intentional: deleting a measurement on the device is a normal human action, and automatic cross-checking would raise an alarm on every such deletion.

**Weight and body composition from a Withings scale** — the path was added on 07.11.2026 and has not yet been confirmed by a live import: the invariant is open. The scale measure codes come from the Withings documentation, not from a live answer — for blood pressure such codes were confirmed by a live answer at the time, and that is still to be done here. There is no nightly judge for weight: the sensor recomputes blood pressure only, so a weight diverging from the cloud is seen only by the next import. And the Health path writes weight unconditionally: a later Health payload for a day Withings wrote first overwrites it — the same scale gives the same value, but no rule guards this.

## Where this lives in the system

The judge's logic lives in **hae_checker.py** — there are the verdicts for each metric, data-coverage verification, registry-blindness control, and tests for distinguishing loss from silence. The second path for blood pressure and weight from the Withings cloud is in **import_withings.py**. The intentions of the subsystem — why it exists and what exactly counts as a loss — are described in **subsystem_intent.yaml**.
