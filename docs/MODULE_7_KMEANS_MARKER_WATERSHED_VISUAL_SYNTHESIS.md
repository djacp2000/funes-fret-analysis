# Module 7 K-means and Marker Watershed visual synthesis

## Scope and evidence boundary

This follow-up review uses only the existing artifacts in:

- `outputs/module7_ofat_review_20260714_kmeans/`;
- `outputs/module7_ofat_review_20260714_marker_watershed/`;
- `outputs/module7_human_visual_review_crops_20260716/`.

No new image was used or generated, no segmentation engine was executed, and
neither original OFAT package was modified. Cellpose remains on standby. D046
was not used or modified, the global K-means `benchmark_baseline` was not
changed, no profile was registered, and no winner was selected. The two fields
are an explicit review set; their sufficiency and representativeness were not
assessed.

The evidence below is deliberately separated into three types:

- **Visible fact:** what can be seen in an existing PNG preview, without
  assigning biological identity or acceptability.
- **Confirmed human observation:** the scientific user's interpretation saved
  in the fixed-crop review package. It applies only to the named crop and shown
  variant.
- **Exact mask comparison:** a read-only comparison of the existing NPY label
  arrays. Binary equality ignores positive label numbers; exact label equality
  requires every integer value to match.

D051 is the confirmed interpretation rule for touching cells: split them when
the division is reliable; otherwise retain one joint ROI and quantify the
cells together. D052 limits this comparison to K-means plus morphology and
Marker Watershed. Neither decision supplies a mask-accuracy metric or selects
a variant.

## Complete variant coverage

Every row below was checked in both 600 x 600 previews and against both saved
label arrays. ROI counts are `Position 1 / Position 2`.

### K-means plus morphology: eight variants

| Variant | Exact mask comparison | Visible fact in the two previews |
|---|---|---|
| `benchmark_baseline` | Reference; 48 / 60 ROI and 6,748 / 8,179 foreground pixels. | Contours occur mainly on bright compact regions; many dim silhouettes have no contour. There are connected multilobed contours, isolated small contours, and border-intersecting objects. |
| `foreground_cluster_count=1` | Its support is contained in the baseline and removes 6,049 / 7,743 baseline pixels; 6 / 4 ROI remain. | Only a few of the brightest objects are outlined; most visible bodies are omitted. |
| `minimum_object_area_pixels=32` | Exact superset of the baseline support: all 48 / 60 baseline components are unchanged and 12 / 21 smaller components add 512 / 1,008 pixels; 60 / 81 ROI. | It shows the largest number of small isolated contours among K-means variants, while dim silhouettes still remain unoutlined. |
| `minimum_object_area_pixels=128` | Subset of the baseline: 2,910 / 3,146 pixels are removed and 16 / 27 exact baseline components remain; 16 / 27 ROI. | Many small and intermediate bright objects are omitted; retained contours remain concentrated on brighter regions. |
| `opening_disk_radius=0` | Superset of baseline support by 152 / 276 pixels; only 10 / 12 components retain their exact baseline support, and one Position 2 output label overlaps two baseline labels; 48 / 61 ROI. | Some narrow extensions and small objects appear that are absent from the baseline, but whole dim silhouettes are still commonly unoutlined. |
| `opening_disk_radius=2` | Subset of baseline support, removing 475 / 503 pixels; 44 / 56 ROI. | Contours are more compact and thin extensions disappear; omissions of dim bodies persist. |
| `closing_disk_radius=1` | Mixed change: adds 5 / 2 pixels, removes 83 / 211, and splits one baseline component in each field; 49 / 60 ROI. | It is visibly close to the baseline over much of each field, with local contour narrowing or separation. |
| `closing_disk_radius=5` | Mixed change: adds 125 / 319 pixels and removes 8 / 9; in Position 2 two output labels each overlap more than one baseline label; 48 / 58 ROI. | Some nearby bright regions acquire wider or bridged contours; dim silhouettes remain largely unoutlined. |

### Marker Watershed: nine variants

| Variant | Exact mask comparison | Visible fact in the two previews |
|---|---|---|
| `benchmark_baseline` | Reference; 16 / 28 ROI and 2,669 / 3,305 foreground pixels. | Fewer bright objects are outlined than by K-means baseline, and many visible bright or dim bodies have no contour. |
| `foreground_threshold_scale=0.9` | Exact superset of baseline support by 353 / 544 pixels; 18 / 31 ROI. Every retained baseline contour expands or otherwise changes support. | More and wider contours appear than at baseline, but extensive unoutlined signal remains. |
| `foreground_threshold_scale=1.1` | Subset of baseline support, removing 263 / 614 pixels; 15 / 23 ROI. | Retained contours are smaller and additional bright objects disappear. |
| `minimum_object_area_pixels=32` | Exact superset: all 16 / 28 baseline components are unchanged and 10 / 9 smaller components add 449 / 419 pixels; 26 / 37 ROI. | Additional small bright foci are outlined; many dim silhouettes remain unoutlined. |
| `minimum_object_area_pixels=128` | Subset of baseline: 668 / 1,484 pixels are removed and 9 / 11 exact baseline components remain; 9 / 11 ROI. | Only larger bright objects retain contours, producing the greatest visible omission within Marker Watershed. |
| `foreground_opening_disk_radius=0` | Superset of baseline support by only 12 / 20 pixels, with unchanged ROI counts of 16 / 28; 8 / 16 components remain exactly equal. | It is visibly very close to baseline, with slight local outward changes. |
| `foreground_opening_disk_radius=2` | Subset of baseline support, removing 44 / 133 pixels; 16 / 27 ROI. | It is also close to baseline, but contours are slightly reduced and one Position 2 object disappears. |
| `marker_min_distance_pixels=8` | **Binary support is globally identical to baseline in both fields.** One baseline ROI is divided into two labels in each field, giving 17 / 29 ROI. | Only the internal division of one outlined object per field changes; foreground coverage and omissions are unchanged. |
| `marker_min_distance_pixels=16` | **The complete integer label image is globally identical to baseline in both fields.** | It is not a distinct visual or mask outcome for these fields. |

## Locally identical binary masks in the eight reviewed crops

Only groups with at least two identical local binary masks are listed. `empty`
means every pixel in that crop is background for the stated variants.

| Crop | K-means locally identical groups | Marker Watershed locally identical groups |
|---|---|---|
| P1-R1 | `{base, close=1, close=5}`; `{fg=1, area=128}` empty | all nine variants empty and exactly equal |
| P1-R2 | `{base, area=32, area=128}` | `{base, area=32, open=0, distance=8, distance=16}` |
| P1-R3 | `{base, area=32}` | `{base, threshold=1.1, area=128, open=0, open=2, distance=8, distance=16}` empty |
| P1-R4 | `{fg=1, area=128}` empty | `{base, area=32, open=2, distance=8, distance=16}` |
| P2-R1 | `{fg=1, area=128, open=2, close=1}` empty | all nine variants empty and exactly equal |
| P2-R2 | none | `{base, area=32, distance=8, distance=16}` |
| P2-R3 | none | `{base, distance=8, distance=16}`; `{threshold=1.1, area=128}` empty |
| P2-R4 | `{base, area=32, area=128}` | `{base, area=32, distance=8, distance=16}` |

Some members of a binary-equality group use different positive label numbers.
Therefore they are the same ROI support locally but not necessarily the same
integer array or the same full-field result.

## Explicit P2-R4 correction

The prior local statement that K `area=32` labeled the P2-R4 border object
better than K baseline is superseded by the exact saved masks:

- inside P2-R4 (`x=535:600`, `y=115:220`), K baseline and K `area=32`
  contain the same 149 foreground pixels and therefore have the same binary
  mask;
- their integer label numbers differ (`8` versus `14`) because the full-field
  component lists are numbered differently;
- K `area=128` also has the same binary mask in this crop, with label `3`;
- over the complete Position 2 field, K `area=32` is not identical to baseline:
  it preserves every baseline foreground pixel and adds 1,008 pixels in 21
  additional small objects.

Thus P2-R4 cannot support a local preference between K baseline and K
`area=32`. The earlier human statement remains useful only for two biological
facts: the border object was considered interpretable, and K `fg=1` did not
label it well.

## Confirmed human observations, kept separate

These observations come only from the eight fixed crops and the six displayed
columns in the auxiliary review package:

- In P1-R2, the central structure was identified as two cells. K `fg=1`
  labeled one and omitted the other; the other five shown variants placed both
  inside one label. Under D051 this is not automatically an error: it is
  acceptable as a joint ROI only if a reliable division cannot be made.
- The small bright foci in P1-R3 and P2-R3 were identified as cells. K baseline
  and K `area=32` labeled the visible P1-R3 cells; K `area=32` was reported to
  cover all visible cells in P2-R3, while the other five shown columns were
  described locally as artefactual or inadequate.
- K `area=32` was the only shown variant considered good in P1-R1. In P2-R1 it
  was considered better than the other shown variants, but cells were still
  missing.
- The central P2-R2 object may be a mitotic cell and was considered perfectly
  labeled by K `area=32` in that crop; no reliable biological split was
  asserted.
- The P1-R4 and P2-R4 border objects were considered interpretable. The P1-R4
  local preference for K baseline remains a human observation. The P2-R4
  comparison is corrected above because K baseline and K `area=32` have the
  same binary mask there.

These local statements do not establish full-field accuracy, field-set
sufficiency, representativeness, or a global ordering of methods or variants.

## Omissions, unions, artefacts, complete-cell relevance, and borders

- **Complete-cell relevance / omissions:** in every full-field preview, many
  visible dim silhouettes and peripheral extensions lack contours. The
  scientific user confirmed that these silhouettes are not obligatorily cells
  requiring ROI solely by their preview appearance; their omission therefore
  does not automatically reject a variant. A structure already identified as
  a cell still requires complete-cell treatment under D042. The scientific
  user subsequently confirmed that many structures outside the Marker
  Watershed baseline / distance-8 masks in both fields are valid cells, so
  those omissions are biologically relevant even though not every dim
  silhouette is obligatorily a cell.
- **Unions:** connected multilobed supports occur in both method families.
  Marker Watershed `distance=8` tests a pure partition change: it divides one
  otherwise unchanged ROI at P1 `x=424:440, y=436:456` and one at P2
  `x=471:481, y=313:332`. Whether either division is reliable under D051 is not
  determined by the mask arrays.
- **Artefacts:** lowering minimum area adds small components in both families.
  The scientific user confirmed that the components added by the area-32
  variants in these two complete previews are cells whose retention is
  desirable. This field-limited interpretation cannot be extrapolated to new
  fields or used as a representativeness claim.
- **Border objects:** exact counts of labels touching an image boundary are:
  K P1 `2/0/4/0/2/2/2/2`, K P2 `1/0/2/1/1/1/0/2`, MW P1
  `2/2/2/2/0/2/2/2/2`, and MW P2 `0/0/0/0/0/0/0/0/0`, in each method's
  variant order above. These are geometric facts, not accept/exclude decisions.
  The two fixed-crop border objects were human-classified as interpretable.

## Human answers to the three closing questions

Confirmed answers:

1. Dim silhouettes without contours are not obligatorily cells requiring ROI.
2. The 12 / 21 extra K `area=32` components and the 10 / 9 extra MW `area=32`
   components in these two fields are cells.

Marker Watershed `distance=8` outlines exactly the same pixels as its baseline,
but changes one outlined object from one label to two:

- Position 1 object at `x=424:440, y=436:456`;
- Position 2 object at `x=471:481, y=313:332`.

The scientific user classified both divisions as doubtful. Under D051, retain
each object as one joint ROI rather than forcing the split. The user also
confirmed that many valid cells lie outside these identical Marker Watershed
supports; changing marker distance does not recover them.

These answers close the three prepared human questions without selecting a
current variant. They must not be generalized into a sufficiency or
representativeness claim.

## Follow-up audit of omitted-cell recovery

This follow-up reuses the same three artifact packages and does not add images,
segmentation runs, or human classifications. It compares every one of the 17
existing variants against two saved sets of confirmed-cell support:

- the 12 / 21 components added by K-means `minimum_object_area_pixels=32`;
- the 10 / 9 components added by Marker Watershed
  `minimum_object_area_pixels=32`.

D054 identifies every component in both sets as a cell in these fields. They
are nevertheless mask supports, not complete manual cell masks. Coverage below
therefore means coverage of the saved confirmed component, not proof that the
complete cell is covered. The two reference sets also cannot be added as unique
cell counts: only one K/MW component pair overlaps in Position 1, and none
overlap in Position 2.

Each entry is `complete / partial / omitted` coverage of reference components,
reported as `Position 1 ; Position 2`.

| Existing variant | K area-32 confirmed supports | MW area-32 confirmed supports |
|---|---:|---:|
| K baseline | `0/0/12 ; 0/0/21` | `9/0/1 ; 9/0/0` |
| K `foreground_cluster_count=1` | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |
| K `minimum_object_area_pixels=32` | `12/0/0 ; 21/0/0` | `10/0/0 ; 9/0/0` |
| K `minimum_object_area_pixels=128` | `0/0/12 ; 0/0/21` | `4/0/6 ; 2/0/7` |
| K `opening_disk_radius=0` | `0/0/12 ; 2/0/19` | `9/0/1 ; 9/0/0` |
| K `opening_disk_radius=2` | `0/0/12 ; 0/0/21` | `9/0/1 ; 9/0/0` |
| K `closing_disk_radius=1` | `0/0/12 ; 0/0/21` | `9/0/1 ; 9/0/0` |
| K `closing_disk_radius=5` | `1/0/11 ; 1/1/19` | `9/0/1 ; 9/0/0` |
| MW baseline | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |
| MW `foreground_threshold_scale=0.9` | `0/0/12 ; 0/0/21` | `2/0/8 ; 3/0/6` |
| MW `foreground_threshold_scale=1.1` | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |
| MW `minimum_object_area_pixels=32` | `0/1/11 ; 0/0/21` | `10/0/0 ; 9/0/0` |
| MW `minimum_object_area_pixels=128` | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |
| MW `foreground_opening_disk_radius=0` | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |
| MW `foreground_opening_disk_radius=2` | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |
| MW `marker_min_distance_pixels=8` | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |
| MW `marker_min_distance_pixels=16` | `0/0/12 ; 0/0/21` | `0/0/10 ; 0/0/9` |

These exact comparisons distinguish the requested evidence classes:

1. **Confirmed cells still omitted.** All variants except K `area=32` omit at
   least one of the saved confirmed supports. MW `threshold=0.9` still omits
   8 / 6 MW-reference components and all 12 / 21 K-reference components. MW
   `area=32` retains its own 10 / 9 confirmed additions but omits 11 K
   references plus part of one in Position 1, and all 21 K references in
   Position 2. Independently, the human review says K `area=32` still omits
   cells in P2-R1.
2. **Added components confirmed as cells.** K `area=32` adds 12 / 21 separate
   components and 512 / 1,008 pixels to its baseline. MW `area=32` adds 10 / 9
   separate components and 449 / 419 pixels. Their component areas are all
   below the baseline 64-pixel cutoff: K 35-59 / 33-63 pixels and MW 33-63 /
   36-61 pixels. D054 confirms their cellular identity only in these fields.
3. **Incomplete coverage of labeled cells.** Exact reference-support coverage
   is partial only for one K reference under MW `area=32` in Position 1 and one
   K reference under K `closing=5` in Position 2. This narrow mask fact does
   not replace the human complete-cell observations: K `area=32` was the only
   good shown result in P1-R1, was still incomplete in P2-R1, and was not
   accepted in P1-R4. K baseline was the accepted P1-R4 result.
4. **Artefacts.** In P2-R3, the human reviewer described the labeling in the
   five shown alternatives to K `area=32` as artefactual, while K `area=32`
   covered all visible cells. The saved response does not map that statement
   to exact label identifiers, so no full-field artefact count is inferred.
   The area-32 additions themselves must not be called artefacts because D054
   confirms them as cells.
5. **Acceptable unions under D051.** P1-R2 contains two confirmed cells. K
   baseline, K `area=32`, MW baseline, MW `threshold=0.9`, and MW `distance=8`
   keep them inside one label; this remains an acceptable joint ROI unless a
   reliable division is established. The two different MW `distance=8` splits
   remain doubtful and must retain the baseline joint labels under D055. No
   split is inferred for the possible mitotic cell in P2-R2.
6. **Exact mask differences for the three priority variants.** K `area=32` is
   an exact binary superset of K baseline. MW `area=32` is an exact binary
   superset of MW baseline. MW `threshold=0.9` also adds without removing
   baseline pixels, but changes the support of every retained baseline contour.
   K `area=32` versus MW `threshold=0.9` has `3,002 / 3,801` shared pixels,
   `4,258 / 5,386` K-only pixels, and `20 / 48` MW-only pixels. K `area=32`
   versus MW `area=32` has `3,111 / 3,703` shared, `4,149 / 5,484` K-only, and
   `7 / 21` MW-only pixels. MW `threshold=0.9` versus MW `area=32` has
   `2,783 / 3,451` shared, `239 / 398` threshold-only, and `335 / 273`
   area-only pixels. Values are `Position 1 / Position 2`.

## Existing-grid candidacy and final-review selection

K `minimum_object_area_pixels=32` is the only existing variant that merits
being presented for a final human acceptability decision on these examples: it
covers every saved area-32 confirmed support from both method families and has
the strongest fixed-crop observations. This is a review-candidacy statement,
not a winner selection or an acceptable-mask conclusion. Its confirmed P2-R1
omissions and rejected P1-R4 coverage may still disqualify it. No existing
Marker Watershed variant has comparable confirmed-cell recovery.

D057 subsequently advanced only K `area=32` as a final-review candidate, and
D060 made it the sole member of the final human acceptability comparison. Those
decisions did not approve it. D061 records the later human outcome that it is
not yet acceptable for these two examples because many cells are excluded and
that another causal extension is required before acceptance or rejection.
None of these outcomes implies sufficiency or representativeness.

## Read-only causal diagnosis and proposed minimum extension

The saved masks support a mixed cause rather than a single one:

- **Area filtering is a confirmed cause for a subset.** Every area-32 addition
  has 33-63 pixels and is absent at the 64-pixel baseline cutoff while all
  baseline components remain unchanged.
- **Foreground selection is also a confirmed cause for a subset in Marker
  Watershed.** Lowering the threshold scale to 0.9 expands support by 353 / 544
  pixels and recovers 2 / 3 MW area-32 reference components, but it leaves most
  confirmed references omitted.
- **The tested opening morphology is not the main observed cause.** Removing
  opening adds only 152 / 276 K pixels and 12 / 20 MW pixels; it recovers only
  two K-reference components in Position 2 and no MW-reference components.
  The other saved opening/closing variants likewise recover at most isolated
  references. This does not exclude untested morphology values or interactions.
- **Marker distance is not an omission cause here.** Distance 8 has exactly the
  baseline support, and distance 16 has exactly the baseline integer labels.
- **Residual K foreground causality is unresolved.** The only saved K
  foreground variant is more selective (`foreground_cluster_count=1`) and
  removes most support. With three clusters, the baseline already selects the
  two brightest clusters; the existing interface has no valid one-parameter
  step that simply includes a dimmer cluster without also selecting background.

The minimum new OFAT block proposed for prior review is therefore exactly three
new variants on the same two fields, six runs total:

1. K `minimum_object_area_pixels=16`, to test whether residual K omissions are
   already present before the 32-pixel filter;
2. MW `minimum_object_area_pixels=16`, to test continuation of the confirmed
   area-filter effect;
3. MW `foreground_threshold_scale=0.8`, to test continuation of the confirmed
   threshold effect.

Existing `opening=0` variants already provide the least-opened morphology test,
so no new morphology run is included in this minimum block. Do not combine MW
`threshold=0.9` with `area=32` in this block because that would change two
factors and cease to be OFAT. If K `area=16` still omits confirmed cells, a
separate reviewed design is required for a genuinely more permissive K
foreground factor; it must not be disguised as a one-parameter extension.

At the time of proposal this plan was not authorized. D057 subsequently
advanced K `area=32` only as a final-review candidate, and D058 authorized the
six-run block exactly as written. The execution evidence is recorded below.

## Authorized minimum extension results

The extension was executed only on `Capture 1 + Position 1/2` and written to
`outputs/module7_ofat_minimum_extension_20260718/`. The original two OFAT
packages and fixed-crop package were not modified. The new package preserves
the same selected C1 source hashes and prepared-frame hashes as the originals,
uses identity preprocessing, records six engine-only operational timings, and
keeps all human-observation fields blank.

### Exact support changes

| Authorized variant | Position 1 | Position 2 |
|---|---:|---:|
| K area `16` versus K area `32` | exact superset; +144 px; +7 components | exact superset; +179 px; +7 components |
| MW area `16` versus MW area `32` | exact superset; +120 px; +6 components | exact superset; +138 px; +6 components |
| MW threshold `0.8` versus `0.9` | exact superset; +680 px; +6 wholly new labels | exact superset; +950 px; +7 wholly new labels |

The K area-16 additions have areas `16-28 / 17-31` pixels and the MW area-16
additions have areas `16-30 / 16-27` pixels. Their biological identity has not
been reviewed; D054 applies only to the prior area-32 additions and must not be
silently extended to these smaller components.

K area `16` still covers all saved K and MW area-32 confirmed supports. MW area
`16` covers all 10 / 9 MW references but only part of one K reference in
Position 1 and none of the 21 K references in Position 2. MW threshold `0.8`
covers 8 / 7 MW references, omits 2 / 2, and covers none of the 12 / 21 K
references.

### Relation to confirmed human problem regions

- None of the three extension variants adds any foreground pixel in P2-R1,
  where the human review confirmed that K area `32` still omitted cells.
- K area `16` adds no pixel in P1-R4, so it leaves unchanged the K area-32 mask
  that was not accepted there.
- MW area `16` adds no pixel in any of the eight fixed crops; all its new small
  components lie elsewhere in the complete fields.
- MW threshold `0.8` adds support in several previously reviewed crops but none
  in P1-R1 or P2-R1. These additions have no new human classification.

Visible inspection of the six new full-field previews shows additional small
isolated contours for both area-16 variants and broader/more numerous contours
for MW threshold `0.8`; many visible bodies remain without contours. Under
D053, visibility alone does not establish cellular identity. Therefore the
extension confirms continued area and threshold effects but does not show, on
confirmed evidence, recovery of the key residual P2-R1 omissions or a variant
that displaces K area `32` as the sole D057 final-review candidate.

No winner, acceptable mask, profile, global baseline change, sufficiency or
representativeness conclusion, or D046 operation is recorded.

## Human classification and final comparison set

D059 supersedes only the earlier unclassified status of the area-16 additions:
the scientific user confirmed that all 7 / 7 new K components and all 6 / 6 new
MW components are cells in Position 1 / Position 2. This does not turn their
small saved supports into manual complete-cell masks or establish a production
minimum-area value.

D060 keeps all three extension variants out of the final comparison despite
that cellular identity. Their added components do not repair the confirmed
P2-R1 omission, K area `16` does not repair P1-R4, and neither MW extension
matches the confirmed support recovery of K area `32`. The final human
acceptability comparison therefore contains only K-means
`minimum_object_area_pixels = 32`.

This is a comparison-set decision, not production approval. K area `32` retains
its known P2-R1 omissions and P1-R4 limitation; no profile is registered, the
global baseline is unchanged, and D046 remains unused.

## Final human acceptability outcome

The scientific user selected outcome B: K-means
`minimum_object_area_pixels = 32` is not yet acceptable for these two examples
because many cells are excluded, and another causal extension is required.
This is not a final rejection.

The confirmed evidence distinguishes the requested classes:

1. **Complete saved-reference coverage.** K area `32` covers every saved
   area-32 component support confirmed as cellular by D054. This narrow support
   fact does not establish complete-cell coverage.
2. **Wholly omitted cells.** Cells remain wholly outside the mask in P2-R1.
   K area `16` adds no foreground pixel there.
3. **Unaccepted coverage.** K area `32` was not accepted in P1-R4, and K area
   `16` leaves that local mask unchanged.
4. **Artefacts.** No saved human response classifies the K area-32 additions as
   artefacts; D054 classifies them as cells. No full-field artefact count is
   inferred.
5. **Acceptable unions under D051.** The two confirmed touching cells in P1-R2
   may remain one joint ROI unless a reliable division is established. No split
   is inferred for the possible mitotic cell in P2-R2.

The causal evidence is mixed but bounds the next question. Minimum-area
filtering is a confirmed cause for a subset because lowering 64 to 32 pixels
recovers 12 / 21 cellular components. It does not explain the key residual
limitations at the tested values: lowering 32 to 16 pixels adds no support in
P2-R1 and leaves P1-R4 unchanged. A foreground/intensity-selection cause
upstream of area filtering is therefore a plausible hypothesis, but it is not
confirmed by the saved artifacts because the only saved K foreground variant
is more selective, not more permissive.

D061 requires a separately reviewed causal-extension design but does not
authorize a new variant or run. No sufficiency, representativeness, production
approval, profile registration, global-baseline change, or D046 operation is
recorded.

## Post-D061 design record

D062 subsequently defines the minimum design for the unresolved K-means
foreground/intensity-selection hypothesis. It introduces one proposed
field-relative boundary relaxation while holding the area limit fixed at 32,
uses the existing area-32 masks as references, and limits any later authorized
execution to one candidate on each of the same two fields. Nothing was
implemented or executed when the design was recorded. See
`docs/MODULE_7_KMEANS_FOREGROUND_CAUSAL_EXTENSION_DESIGN.md`.
