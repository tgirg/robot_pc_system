# 実機なし Fake ESP32 / Fake Robot

現行 `pc_controller` の実機向け NDJSON 通信経路を、メモリ内の `FakeESP32` を使って同じ上位プロトコル経路で検証する資料です。
`--simulate` と `--fake-esp32` は役割を分けて運用し、実機プロトコルを壊さずに回帰テストを進めます。

## 1. 通常起動（実機なし）

```powershell
python -m pc_controller.main --fake-esp32 --fake-trace
```

- COM ポートや実機は不要です
- 実機と同じ `hello / config / arm / drive / telemetry` 経路を通します
- コントローラ入力なしで走行可能:

```powershell
python -m pc_controller.main --fake-esp32 --fake-trace --no-joystick --once
```

## 2. smoke test（コントローラなし）

```powershell
python -m pc_controller.fake_robot_demo
```

`forward -> stop -> strafe -> stop -> pivot -> stop` の順で `telemetry` を受け、最終 PWM が `[0, 0, 0, 0]` であることを確認します。

### 共有Main Dashboard（読み取り専用）

```powershell
.\run-fake-robot-dashboard.cmd --robot R2
```

既存のlocal Competition JSONLを読み取り専用で表示する場合だけ、明示pathを追加します。

```powershell
.\run-fake-robot-dashboard.cmd --robot R2 --competition-log 99_作業用\tmp\example.jsonl
```

log pathを省略した場合、Logs tabは`NOT_CONFIGURED`です。自動探索、Fault Historyとのmerge、
Competition操作、remote転送、source/outbox削除は行いません。

`--robot R1` / `--robot R2` は必須で、推測による既定割当はありません。選ばなかったrobotは
UNBOUND/OFFLINEのままです。このentrypointは単一の`ControllerApp -> VirtualSerialLink ->
SimulatedEsp32`だけを所有し、旧dashboard Serial、USB探索、カメラ、ARM、走行、calibration出力を
起動しません。CalibrationタブのServo Zero/Angle/Direction候補編集、logical-front vector preview、
bounded Parameter sliderはGUIメモリ内のlocal draftだけです。Parameter sliderはcontroller deadzone、
linear/angular scale、PC側open-loop/pivot PWM clampに限定され、移動・stageともsave/apply/config write/
servo/motor出力は常にblockedです。Fault / Warning Historyは現在snapshotのevent edgeをrobot別の
GUI session memoryへ最大200件保持します。PC Safety根因、structured ESP32 fault、telemetry flags、
timeout/transport/node inventoryを別sourceで表示し、exact source timestampがない項目は
`FIRST_OBSERVED`と明示します。acknowledgementはlocal表示だけでSafety root causeをclearしません。
Logs tabは明示されたlocal Competition JSONLのsession/sequence/timestamp/stateを検証し、R1/R2とfleet eventを
分離して表示します。logに存在しないSafety/fault/retry/node値は`UNKNOWN_NOT_RECORDED`です。
Replay tabは同じvalidated sourceをmanual local cursorで表示するだけです。recorded action/commandは再送せず、
selected robot自身が記録したAutonomy/Safety/armedだけをsource sequence付きで表示します。
終了時はDISARMを送ってVirtualSerialをcloseします。

## 3. Scenario Runner

Fault 注入を含むまとめ実行 CLI:

```powershell
python -m pc_controller.fake_robot_scenarios
python -m pc_controller.fake_robot_scenarios --seed 7 --trace telemetry_timeout disconnect
```

表示項目:

- PASS/FAIL
- finalSafetyState
- finalArmed
- fault

主要シナリオ:

- normal
- telemetry_timeout
- disconnect
- automatic_reconnect
- reboot
- malformed
- explicit_fault
- controller_disconnect
- config_rejection
- arm_rejection
- sequence_regression
- stale_telemetry
- command_receive_stop

## 4. fault injection 一覧

`SimulatedFaultProfile` で個別設定/組み合わせ可能:

- telemetry停止
- 指定時間後通信断
- ESP32再起動
- hello_ack 非返却
- config_ack 拒否
- ARM拒否
- 明示 fault 送信
- malformed JSON 送信
- stale telemetry seq
- telemetry seq regression
- command受信停止
- 任意遅延
- packet drop
- encoder 異常値
- RPM stuck
- servo stuck
- seed 固定（決定論的）

時間faultは `ControllerApp`、`SafetyMonitor` への判定時刻、
`VirtualSerialLink`、`SimulatedEsp32` で同じms clockを共有します。
Scenario Runnerとdemoは手動clockを20 ms単位で進めるため、wall clockや
`sleep` の速さには依存しません。`disconnect_after_ms`、
`reboot_after_ms`、`command_receive_stop_after_ms`、`response_delay_ms` は
開始時刻から `elapsed >= configured_ms` になった境界で有効になります。

random packet dropはhello/config/ARMを偶然壊さないよう、既定では無効です。
正常ARM後に `activate_packet_drop()` を呼んでruntime fault phaseを開始します。
同じseedと同じresponse列ならdrop列も同一です。

## 5. VirtualSerial のログ改善

`--fake-trace` の既存トレースは維持し、以下を追跡します。

- timestamp
- node_id
- state
- armed
- event
- command seq
- telemetry seq
- fault
- reconnect（実装時点では再接続時の明示フラグ）

判定に使う `event_log` は `--fake-trace` が無効でも保持されます。
trace flagはコンソール出力だけを制御します。

## 6. 通常運用時との比較

- `device.disconnect()` 中はwrite/readともtransport errorになり、pending responseは破棄され、
  telemetryは届かず、commandも処理されません。PCは即時SAFEになります。
- `ControllerApp` はtransport errorまたはtelemetry liveness喪失後に、既定1秒の
  quiet intervalからbounded exponential backoffでautomatic reconnectを開始します。
  `--port`指定時は同じport、auto-discovery時は初回identityの`node_id`へ固定して
  rediscoveryし、別drive nodeへのsilent switchを許可しません。
- reconnect後は `DISARM -> HELLO/identity確認 -> CONFIG -> config_ack` の順で
  re-handshakeします。identity/role mismatch、PCA9685 not-ready、config rejectionは
  retryをblockし、handshake timeout/port open failureだけをbackoff retryします。
- re-handshake成功後は`READY_DISARMED`（PC/FakeともSAFE）のままです。切断前からARM comboを押し続けても
  一度releaseするまで新しいARM requestを開始しません。automatic ARMはありません。
- `--no-auto-reconnect`でautomatic reconnectを無効化できます。初期待機は
  `--reconnect-interval`、HELLO/config ACK待ちは`--reconnect-handshake-timeout`で指定します。
- `device.reconnect()` はFake transportを復旧する低位部品であり、試験では
  `ControllerApp`自身が新しい`VirtualSerialLink`を開いて上記handshakeを完了することを確認します。
- 異常時は既存 safety の最小安全状態 (`SAFE`) に寄せ、**自動的に再ARMしません**。
- 実機固有の電源/バス/ハードウェア起因異常は Fake で完全再現しません。

## 7. Fakeで保証できないもの（実機必須）

- 実モータ電流
- 機械的負荷・摩擦・接地滑り
- USB 電気的切断
- 電源瞬断
- 実センサノイズ
- モータードライバ故障

## 8. 現時点の安全動作判定

- telemetry timeout: DISARM
- serial disconnect: DISARM
- ESP32 reboot: Fakeのarmed/state/drive/telemetry seq等のvolatile stateを即時SAFEへreset。
  PCは次のtelemetry regressionまたはfreshness timeoutでSAFEとなり、transport liveness喪失時は
  automatic reconnect/re-handshakeへ進む。成功後もautomatic ARMなし
- malformed: DISARM
- explicit fault: DISARM
- config rejection: DISARM
- arm rejection: DISARM
- sequence regression: 正常seq baseline確立後に過去seq (`seq < last`) を受けた状態。即時DISARM
- stale telemetry: 同一seqの重複packet (`seq == last`)。packetは無視し、即時DISARMはしないが
  telemetry freshness watchdogも更新しないため、重複が続けばtelemetry timeoutでDISARM
- controller disconnect: DISARM
- command receive stop: PCのTXは継続する一方、Fakeのprocessed command countは増えない。
  実firmware同様にtelemetryと`command_age_ms`は継続し、300 msでFake出力0、
  500 msでFake SAFE、PCは`ESP32 command timeout`でDISARM

RPM stuckはcommanded RPM/PWM targetが変化してもobserved `wheel_rpm` が固定値のまま、
servo stuckはcommanded angleが変化してもobserved `servo_deg` が固定値のまま、という意味です。

automatic reconnectのFake試験はOS USB stackやCOM port再enumerationの保証ではありません。
実USB切断、COM番号変化、boot時間、driver buffer挙動は実機検証が必要です。
command stateとobserved telemetry stateは別フィールドで保持します。

曖昧なケースは安全側（再起動なし/保守的）で扱い、再ARMは手動実行に限定します。
