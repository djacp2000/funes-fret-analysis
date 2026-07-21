# Module 3 real SlideBook log validation

Date: 2026-07-13

## Scope

Inspect the two SlideBook `.log` files in `raw_data/` and decide whether
Module 3 can safely discover and associate them without changing later
modules.

## Files inspected

- `Capture 1 - Position 1_XY1757012095_Z0_T0_C0.log`
- `Capture 1 - Position 2_XY1757012096_Z0_T0_C0.log`

Each file is 502 bytes and decodes with the existing `utf-8-sig` reader.

## Observed structure

Both logs contain:

- eight simple `key: value` header fields, including export and capture times,
  channel count, time-point count, microns per pixel, and average timelapse
  interval;
- a tab-separated table with a `TIFF File Name` column;
- one row naming the C0 TIFF and one row naming the C1 TIFF for the same parsed
  `Capture + Position + XY + Z + T` identity.

Module 3 exposes the recognized header values as structured fields while
continuing to preserve every original key/value line. Export and capture
date-times remain strings so their source formatting is not silently changed.
Counts and calibration values are parsed as numbers when valid. The average
timelapse interval remains the reported string, including `Unknown`.

Each table row is also structured as IFD, X/Y/Z position in micrometers,
elapsed time in milliseconds, channel name, and TIFF filename, while retaining
the source line number and original row text. This makes spatial positions and
channel descriptions available for later output or analysis without making
new scientific assumptions now.

The `.log` filename resembles the C0 TIFF filename, but this resemblance is not
needed for association. The table itself explicitly names both members of the
pair and is the stronger, auditable association source.

## Validation result

Module 3 should support `.log` as auxiliary text metadata and should associate
this inspected log family to TIFF pairs when all of these conditions hold:

1. the file is a `.log` containing a tab-separated `TIFF File Name` column;
2. every referenced TIFF was discovered beside the log;
3. the references resolve to exactly one parsed acquisition identity;
4. that identity has exactly one C0 and one C1 TIFF.

If these conditions fail, Module 3 preserves the metadata file, leaves it
unassociated, and emits a structured error. It does not guess from the log
filename alone. Ordinary `.txt` files and unrecognized `.log` formats remain
preserved and unassociated without an error.

Applied to `raw_data/`, Module 3 discovers two logs, creates two pair
associations, leaves no file unassociated, and reports no discovery or
association issues.

## Temporal metadata boundary

The logs say `Time Points: 2`, but `Average Timelapse Interval` is `Unknown`.
The inspected table has only one row per channel and reports elapsed time zero
for both rows. This is not enough evidence to assign per-frame elapsed times or
change Module 2 normalization. Module 3 preserves these values as metadata
only.

## Channel-count warning

The inspected files declare two channels and therefore produce no channel-count
warning. Module 3 emits `slidebook_log_channel_count_exceeds_supported` when a
recognized log declares more than two channels. The warning records the
declared and currently supported counts, while extra channel rows and raw
metadata remain preserved for future handling.

## Module boundary

The new association is a Module 3 result built from Module 1 parsed TIFF
records. No Module 2 TIFF-reading behavior or Modules 4-14 behavior was
changed. Later integration can consume the explicit Module 3 association in a
separate requested session.
