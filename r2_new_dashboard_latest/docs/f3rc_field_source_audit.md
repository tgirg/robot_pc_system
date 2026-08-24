# F3RC Field source authority audit

## Status

- Audit date: 2026-08-23
- Task: GUI-032A correction
- Result: `PARTIAL_RULEBOOK_AUTHORITY_ONLY`
- Geometry result: `BLOCKED_NO_FIELD_DRAWING_OBJECT_ARTIFACT`
- Mission-coordinate use: `PROHIBITED`
- Shared Field model/renderer use: `NOT_READY`

This audit classifies the Field material currently present in this working
tree. It does not validate any physical dimension, boundary, placement,
orientation, or object geometry. No robot, Serial, network, or hardware
operation was performed.

## Local rulebook evidence

The initial GUI-032 search inspected Git-tracked candidates but missed one
local PDF because the entire historical folder is excluded by
`.git/info/exclude` and therefore does not appear in normal `git status` or
`git ls-files` output:

| Source ID | Local path | Evidence |
| --- | --- | --- |
| `F3RC2026_RULEBOOK_V1_1_LOCAL` | `01_F3RC2026_ロボコン/参考資料/F3RC2026_rulebook_v1.1.pdf` | 14 pages; SHA-256 `d245af60c9f9dc7b33399a395456ce631a5c445a9bfdc052ef7ec91886b722e6` |

The rendered title page identifies the document as the F³RC2026 rulebook,
Ver 1.1, prepared by the F³RC2026 Executive Committee. Page 14 records Ver 1.1
as published on 2026-06-19 and says section 5.5.1 changed the in-competition
robot envelope from 500 mm to 600 mm. All 14 pages were text-extracted and the
relevant title, Field/rule, safety, precedence, and revision pages were
rendered for visual inspection.

This file is useful local source evidence, but it is not retained in Git HEAD,
and this audit did not verify the latest official-site revision. Rulebook
section 10.2 explicitly allows later changes without notice. Do not force-add
the excluded PDF or call it confirmed-current without an operator decision and
official revision check.

## What the rulebook does establish

The following non-geometric semantics have pinpoint support in Ver 1.1:

- pages 3-5 define R1, R2, Field, R1/R2 start zones, warehouse A/B/C,
  walkway, garden, block, plant, watering can, entry, complete entry, and
  placement;
- page 4 identifies the competition objects as blocks, plants, and watering
  cans, with white blocks in warehouses A/B and black blocks in warehouse C;
- page 6 section 4.2.3.1 gives the setup inventory: four plants and four white
  blocks in A, six white blocks in B, and two black blocks plus one watering
  can in C;
- page 6 sections 4.2.3.3-4 require one block in each of the six orange-line
  divisions of warehouse B and prohibit blocks from entering the orange line;
- pages 3 and 9 state that R1 may not enter warehouse C while R2 may enter all
  Field zones;
- page 13 sections 10.3-4 identify a separate `Field drawing / objects`
  document and make the rulebook controlling if the two documents conflict.

These points may be used as a source-backed rules and inventory checklist.
They do not supply zone bounds, Field dimensions, mission coordinates, object
sizes, initial poses, yaw/orientation states, or `face_down` semantics.

## Missing companion authority

The rulebook repeatedly delegates Field details to a separate
`Field drawing / objects` artifact. No such PDF, official drawing, DXF/DWG,
STEP/IGES, dimension table, revision/page reference, or checksum was found in
the tracked repository or the inspected historical folder.

The perspective illustration on rulebook page 3 is not a dimensioned drawing
and must not be measured or converted from pixels into mission coordinates.
Consequently, the rulebook corrects the earlier claim that no rulebook exists,
but it does not unblock Field geometry or pose modeling.

## Legacy dashboard candidates

The only detailed Field geometry remains the copied dashboard candidate data:

| Candidate | SHA-256 | Classification |
| --- | --- | --- |
| `apps/robot_pc_system/config/field/f3rc2026_field.yaml` | `4451951ca4cba3b0bb6394500449fd3668af7e367eea982cdba54f72bd1b2750` | `UNVERIFIED_DERIVED_CANDIDATE` |
| `apps/robot_pc_system_4wis_dashboard/config/field/f3rc2026_field.yaml` | `4451951ca4cba3b0bb6394500449fd3668af7e367eea982cdba54f72bd1b2750` | identical copied candidate |
| `apps/robot_pc_system/pc/field/field_model.py` | `585afeb76e89b80a22daceae52ba6d06677df7d84e9167667377679e7ad82c5a` | legacy dashboard model, not source evidence |
| `apps/robot_pc_system_4wis_dashboard/pc/field/field_model.py` | `585afeb76e89b80a22daceae52ba6d06677df7d84e9167667377679e7ad82c5a` | identical copied implementation |

Both app copies were imported from `https://github.com/tgirg/robot_pc_system`
at recorded revision `783cfb5`, then entered this repository with baseline
commit `087c7f9`. The import record establishes software provenance only. It
does not identify the missing official Field drawing, its revision, page,
issue date, or checksum.

## Candidate reconciliation

The rulebook supports the existence and names of warehouse A/B/C, walkway,
garden, R1/R2 start zones, blocks, plants, and watering cans. It also supports
the setup counts and qualitative access/placement rules listed above.

It does not validate the YAML's `4500 mm x 2400 mm` outline, material/tape
claims, tolerance, zone/wall/line rectangles, start poses, object rectangles,
or coordinates. Those numerical values remain `UNVERIFIED_DERIVED_CLAIM` or
`UNVERIFIED_DERIVED_CANDIDATE`. The YAML objects remain
`PROVISIONAL_EXPLICIT`, as their own notes already say an official drawing or
physical measurement is required.

`top_left_origin_x_right_y_down` remains a `LEGACY_RENDERER_CONVENTION`; it is
not an approved mission coordinate frame and must not be silently combined
with the existing machine coordinate convention. Two byte-identical copies
prevent copy drift at this snapshot but do not increase the authority of the
underlying values.

## Allowed use before the companion artifact is retained

- Keep the legacy dashboard Field feature visibly separate from the shared
  safe runtime.
- Use the rulebook-backed object/zone vocabulary, setup counts, and qualitative
  rules only with the source ID and page/section reference above.
- Treat the YAML as a candidate inventory for later numerical reconciliation.
- Preserve physical units separately from pixels in any investigation tool.
- Keep dimensions, bounds, poses, rotation, orientation, `face_down`, state,
  and assigned robot `UNKNOWN` unless a source explicitly defines them.

Neither the legacy candidate nor the perspective illustration may drive
mission coordinates, navigation, robot commands, automatic placement,
Competition decisions, or claims of official or physical validation.

## Evidence required to unblock the authoritative Field model

1. Operator approval on how the local Ver 1.1 PDF should be retained, plus a
   check that Ver 1.1 is still the intended official revision.
2. The separate official `Field drawing / objects` package with source ID,
   revision/date, checksum, and exact page/view/feature references.
3. Units, tolerances, Field origin, positive axes, rotation convention, and the
   transform to the existing robot/machine coordinate convention.
4. Official object geometry, permitted pose/orientation states, and
   `face_down` semantics where applicable.
5. Reconciliation of every candidate YAML value as accepted, corrected, or
   rejected, with `UNKNOWN` retained for unresolved values.
6. Independent schema, bounds, overlap, coordinate-transform, and renderer
   tests before mission/config integration.

Physical measurements may be stored as a separate measured layer, with tool,
date, uncertainty, and operator provenance. They must not overwrite the
official layer or be described as official rulebook values.

## Next safe action

Retain the approved rulebook and its separate Field drawing/object package with
the provenance above. Until the companion drawing is available, a shared
authoritative Field geometry model, renderer, item pose editor, block
orientation editor, face-down editor, and Competition visualization remain
blocked rather than guessed.
