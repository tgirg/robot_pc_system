# Command-center GUI feature and migration matrix

## Visual source decision

The requested prior-chat reference image and
`robotics_project_specs_512mb_20260819_181016.zip` were not present in the
workspace or supplied attachment. The implementation therefore uses the
explicit fallback brief: near-black background, luminous yellow-green state,
orange controls, yellow cautions, red faults, thick hierarchy, cut-corner
fascia, diagonal technical grid, dense bilingual labels, and no external CDN.

No Evangelion image, logo, audio, music, dialogue, proprietary effect, or
unlicensed font is included. The UI uses OS Japanese fonts and original
project-generated WAV cues.

## Authoritative paths inspected

| Concern | Current authority | GUI rule |
| --- | --- | --- |
| Real PC control | `pc_controller/ControllerApp` | one owner; render snapshots |
| ESP32 protocol | v1 NDJSON through `SerialLink` or `VirtualSerialLink` | no visual-layer protocol change |
| Safety | `SafetyMonitor` | no GUI bypass or automatic ARM |
| R1/R2 binding | `FleetDashboardSnapshot` | explicit binding; unbound stays `UNBOUND` |
| Vehicle settings | `config/vehicle_config.json` | existing keys retained |
| Controller settings | `config/controller_mapping.json` | existing keys retained |
| Competition log | explicitly selected local JSONL/NDJSON | read-only validated source |
| Field geometry/items | `config/field/f3rc2026_field.yaml` | existing YAML keys retained; optional item pose keys added |
| Sound settings | `config/sound_settings.json` | immediate atomic save with defaults |

## Screen migration

| Existing feature/source | Command-center destination | State |
| --- | --- | --- |
| Fleet overview, R1/R2, Safety, node inventory, battery, wheel telemetry | 01 COMMAND / OVERVIEW | retained and restyled |
| 4WIS wheel commands, PWM/RPM, encoder, steer, vectors | 02 DRIVE / VECTOR | retained and restyled |
| Real R2 port/config/controller diagnostics | 03 LINK / SETTINGS (real runtime) | retained; SAFE-only apply |
| Confirmed non-drive mechanisms | 04 ACTUATOR / TEST | retained; currently `NOT_CONFIGURED` because no authoritative inventory exists |
| Confirmed non-drive sensors | 05 SENSOR / INPUT | retained; currently `NOT_CONFIGURED` where contracts are absent |
| Servo Zero local drafts | 06 CALIB / ZERO | retained |
| Servo Angle endpoint drafts | 06 CALIB / ANGLE | retained |
| Direction/coordinate and parameter drafts | 06 CALIB / DIR | retained |
| Field geometry, R1/R2 drawing, coordinates, zoom, item add/move/duplicate/delete | 07 FIELD / MAP | migrated |
| Item orientation and face-down selection | 07 FIELD / MAP | added; optional backward-compatible YAML keys |
| Fault and warning session history | 08 ALERT | retained |
| Autonomy and Competition read-only context | 09 AUTO | retained |
| Validated local Competition records | 10 LOG | retained |
| Offline replay cursor | 11 REPLAY | retained |
| Master/category/event sound settings and preview | 12 AUDIO | added |
| Legacy Home/diagnostics/camera/Arduino/serial/LSB/noise/simulation/documents | original full dashboard navigation | retained; not constructed by safe shared runtime |

## Control inventory and dummy-action audit

- Shared COMMAND, DRIVE, ACTUATOR, SENSOR, ALERT, AUTO, LOG, and REPLAY controls
  are snapshot selection, local acknowledgement, validated local-file reload,
  or offline replay controls.
- Calibration Apply/Save buttons remain visibly unavailable because the
  controller API contract is not defined; local validate/stage/revert operations
  remain functional.
- FIELD item controls mutate the in-memory field model; Save and Reload are
  connected to atomic YAML persistence. R2 pose/optical controls are hidden in
  the safe shared runtime because no controller binding is provided there.
- AUDIO controls update the live `SoundManager` and atomically save JSON.
- The full legacy dashboard keeps all original buttons, shortcuts, serial tools,
  simulation, write tools, and navigation. No legacy control was removed.

## Safety and readiness semantics

- Shared Fake runtime remains output-free and uses zero operator input.
- Reconnect remains `DISARM -> HELLO/identity -> CONFIG -> config_ack`, then
  `READY_DISARMED`; it never automatically re-ARMs.
- Audio observes state edges only. Repeated telemetry cannot retrigger sounds.
- Audio failure is caught and never interrupts GUI or control processing.
- The command fascia can display a 60-second countdown only when the immutable
  Competition state is actually `READY_DISARMED`, with a once-only 10-second
  cue. The current controller does not expose an authoritative communication
  PASS timestamp or automatic competition re-lock API, so the GUI does not
  invent one when Competition is absent.
- SAFE, READY, ARMED, RUNNING, FAIL, connection state, and backend are expressed
  with text and structure, not color alone.
- No continuous or decorative animation is used; reduced-motion environments
  therefore receive the same static layout.

## Known authority gaps (displayed explicitly)

- No configured non-drive mechanism/sensor inventory or generic telemetry
  contract exists for the current shared snapshot.
- No controller API currently applies Servo Zero/Angle/Direction local drafts
  to hardware; the GUI keeps those actions blocked instead of writing Serial.
- The shared snapshot has no authoritative absolute field pose for both robots.
  Initial/map-local poses are not represented as live hardware position.
- Competition START READY expiry is not a controller-side interlock in the
  current repository; the GUI countdown is a display aid only when Competition
  state is supplied.

