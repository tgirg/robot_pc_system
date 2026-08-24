# COMPETITION mode and local competition logs

`pc_controller/competition.py` is a hardware-independent, fail-closed wrapper
around the R1/R2 autonomy state machines. It does not send actuator commands and
does not enable competition operation by itself.

## Safety gates

A competition session can become `ACTIVE` only after all of these separate gates:

1. COMPETITION mode is explicitly enabled.
2. Every configured robot passes required-node and safety prechecks.
3. Every robot has an externally confirmed, explicit ARM operation.
4. START is explicitly confirmed.

No method in this layer sends ARM. A failed precheck, invalid transition, robot
STOP/BLOCKED state, or local log write failure requests STOP for every robot.
Mission completion also produces a per-robot `STOP_REQUESTED` action.

The state sequence is:

```text
CREATED -> PRECHECK -> READY_DISARMED -> ARMED_READY -> ACTIVE
                                                      |       |
                                                      v       v
                                                   STOPPED  BLOCKED
                                                      \       /
                                                   POST_COMPETITION
```

## Local log

`CompetitionLogWriter` creates a new `.jsonl`/`.ndjson` file exclusively and
never appends to an existing session file. Each event includes a schema version,
session ID, monotonically increasing sequence, non-regressing timestamp, and competition state.
Writes are flushed and `fsync`-ed. Structured data fields whose keys indicate a
password, token, PSK, private key, Vault value, or other secret are redacted.
Callers must still never place credentials in free-form event names or reasons.

`read_competition_log_records()` is the shared read-only load boundary. It accepts
only one explicitly supplied local `.jsonl`/`.ndjson`, validates the core record
order/session/time/state and writer-owned optional field types, and performs no
directory discovery, repair, staging, deletion, or network operation. The shared
Logs GUI builds a bounded immutable view from this function. Missing optional
Safety/fault/retry/node data remains `UNKNOWN_NOT_RECORDED`; session-local Fault
History is not merged into the persistent Competition record.

The offline Replay GUI consumes that same validated immutable source. It uses a
manual local cursor only, never re-emits recorded actions/commands, and never
calls Competition, Autonomy, ControllerApp, Serial, ARM, outbox, or remote APIs.
Robot state is shown only when the selected robot explicitly recorded the field;
fleet events and truncated prefixes are not used to invent robot state.

The Fake Robot competition E2E can be run without USB or network access:

```powershell
C:\robot_venvs\robot_project_kicad\Scripts\python.exe -m pc_controller.fake_competition_demo `
  --config-dir config `
  --output-dir 99_作業用\tmp\fake-competition `
  --session-id local-validation
```

Use a new session ID/output directory for each run because logs are created with
exclusive semantics. The CLI converts the session ID to a filename-safe component;
log and outbox paths reject URL and UNC/network-share forms.

## POST_COMPETITION outbox

`prepare_post_competition_bundle()` accepts only a finalized
`POST_COMPETITION` log. It validates the JSONL schema, record order, session
identity, and final state; copies the exact bytes into a content-addressed local
outbox; computes SHA-256; and writes an integrity manifest. Repeating the same
operation is idempotent only when the existing staged log and manifest still
match, including the original filename, byte size, event count, and content hash.

The manifest deliberately remains:

```json
{
  "sync_status": "AWAITING_REMOTE_CONFIGURATION",
  "remote_transfer_performed": false
}
```

No network client, destination, credential handling, retention policy, or delete
operation is implemented. Those choices are unresolved safety and operations
requirements. A future remote sync implementation must be additive, verify the
remote checksum/readback before changing status, and must not delete the local
source or outbox copy automatically.

## Validation boundary

The automated tests cover the state gates, R1/R2 stop-all policy, append-only
logging, redaction, corruption detection, outbox integrity/idempotency, and a
Fake ESP32 competition flow that ends SAFE, disarmed, and at zero PWM. They do
not validate physical robots, USB/serial drivers, task semantics, or a remote
log recipient.
