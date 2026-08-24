# R1/R2 Autonomy State Machine Foundation

## Scope

`pc_controller/autonomy.py`はR1/R2のmission進行と失敗policyだけを扱う、
hardware-independentな状態機械です。serial、motor、servo、network、SSHを直接操作しません。
active robotの物理task、経路、sensor条件がまだ確定していないため、それらは推測で実装していません。

## Safety gates

開始順序は固定です。

```text
IDLE
  -> required nodes READY + safety READY
READY_DISARMED
  -> 外部で明示ARM済みであることを確認
ARMED_READY
  -> 独立した明示START
RUNNING
```

- `prepare()`はrequired nodeまたはsafety gateがfalseなら`BLOCKED`となり、`STOP_REQUESTED`を返します。
- `confirm_explicit_arm()`はARM commandを生成しません。外部Safety層が明示ARMを確認した事実だけを記録します。
- 明示ARMなしでSTARTすると`BLOCKED`です。
- `explicit_start=False`では状態を進めません。
- invalid transitionは例外で進行を継続せず、`BLOCKED` + `STOP_REQUESTED`へfail closedします。
- mission完了時も最後の出力を残さないよう、`STOP_REQUESTED`と`MISSION_COMPLETED`を同時に返します。

## Failure policy

各`MissionStep`はretry回数、retry delay、最終failure actionを保持します。

- `STOP`: `STOPPED`へ入り、必ず`STOP_REQUESTED`
- `SKIP`: 直前出力を止める`HOLD_REQUESTED`、`STEP_SKIPPED`、次stepの`RUN_STEP`
- `FALLBACK`: `HOLD_REQUESTED`後に`RUN_FALLBACK`。fallback失敗は`STOPPED`
- `retry`: `HOLD_REQUESTED`と`RETRY_SCHEDULED`を返し、deadlineまでは再実行しない

retryは注入された`now_ms`だけで進み、sleepやwall clockを使いません。deadline到達時の1回の
`tick()`で1回分の`RUN_STEP`だけを返すため、busy retry loopにはなりません。

`RUN_STEP`、`HOLD_REQUESTED`、`RUN_FALLBACK`、`STOP_REQUESTED`は意味的actionです。
実executorはHOLD/STOPを先に適用し、Safety/transport異常時にはstate machineの進行より
PC/ESP32のDISARMを優先する必要があります。

## Read-only GUI context

共有GUIは既存machineが明示的にsnapshot builderへ渡された場合だけ、state ID/name、mission、
current/next step、retry、failure policy、active fallback、skipped step、reason、recent eventを表示します。
GUIはmachine methodを呼ばず、ARM/START/STOP/SKIP/FALLBACK/state transition controlを持ちません。

現行`FakeFleetDashboardRuntime`はAutonomy machineを所有しないため、共有Autonomy tabは
`NOT_CONFIGURED`を表示します。`MissionStep`に一般step timeout fieldはないため捏造せず、retry deadlineだけを
別表示します。またHOLD/STOPはexecutorの実行完了証拠ではないため、executor confirmationは`UNKNOWN`です。

## R1/R2 isolation

`FleetAutonomyCoordinator`は`RobotId.R1`と`RobotId.R2`ごとに独立したstate machineを保持します。
同じrobot IDを二重登録できません。`stop_all()`は決定論的なR1、R2順で両方へSTOPを要求します。

## Fake Robot E2E

```powershell
C:\robot_venvs\robot_project_kicad\Scripts\python.exe -m pc_controller.fake_autonomy_scenarios --config-dir config
```

現在のscenario:

- `stop_on_failure`: R2のstep failureからPC/Fake ESP32をSAFE、PWM 0へ落とす
- `retry_skip_fallback`: R1でdeadline retry、SKIP、safe-stop FALLBACK、mission完了時STOPを通す
- `missing_node_blocks_start`: required drive node欠落でARM messageを一切送らずBLOCKED

このE2Eは`ControllerApp -> VirtualSerialLink -> SimulatedEsp32`を通しますが、実競技taskを表すものではありません。

## Not yet implemented

- 実R1/R2 task sequenceとfield geometry
- sensor observationからstep resultを決めるadapter
- real controller runtimeへのautonomy action接続
- COMPETITION mode、local competition log、post-competition sync
- 実機でのSTOP距離、再試行安全性、fallback経路
