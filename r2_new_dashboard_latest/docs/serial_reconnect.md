# Serial Startup and Reconnect

## Scope

`pc_controller.ControllerApp`の実serial経路は、初回起動時と確立済みlink切断後の両方で
fail-closedに接続を回復します。実機、USB driver、Windows再enumerationの確認結果を示す文書では
なく、software state machineとFake serial試験の境界を記録します。

## Startup policy

| 実行形式 | 初回discovery/open失敗時 |
| --- | --- |
| 通常の無期限実行 | `SAFE`のまま常駐し、bounded exponential backoffで再試行 |
| `--once` | エラー終了。通信確認失敗を成功として隠さない |
| `--duration` | エラー終了。bounded runの結果を曖昧にしない |
| `--no-auto-reconnect` | エラー終了。operatorのopt-outを維持 |
| 複数node一致 | エラー終了または再接続を`blocked`。候補を自動選択しない |

初回失敗後の待機中はcontrollerのARM操作を受けてもPC側をARMにせず、`serial unavailable`で
`SAFE`を維持します。起動途中で例外が発生しても、現在processが作成したPID fileはfinallyで
除去します。

## Recovery flow

```text
initial discovery/open failure
        |
        v
SAFE + serial closed + waiting
        |
        v
bounded backoff rediscovery/open
        |
        v
identity and role check
        |
        +-- mismatch / duplicate / wrong role --> BLOCKED
        |
        v
DISARM -> HELLO -> identity validation -> CONFIG -> config_ack
        |
        v
READY_DISARMED
        |
        v
fresh explicit operator ARM only
```

再試行間隔は`--reconnect-interval`を基準に1、1、2、4、8、16倍まで増加し、その後は16倍を
上限とします。handshakeは`--reconnect-handshake-timeout`を超えるとlinkを閉じ、次の再試行へ
戻ります。確立済みnodeから得た`node_id`と`role`は再接続候補へ固定します。

## Safety invariants

- 初回失敗、切断、handshake timeoutのいずれでもautomatic ARMしない。
- recoveryは常に先に`DISARM`を送り、HELLOとCONFIGを順に再確認する。
- `config_ack`成功後もstateは`READY_DISARMED`であり、fresh explicit ARMが必要。
- duplicate node、identity mismatch、role mismatch、PCA9685 not ready、config rejectionは自動選択や
  broad retryで隠さず`blocked`にする。
- GUIやFake専用の接続stateは作らず、`ControllerApp`と同じstate machineを使用する。

## Offline validation

`tests/test_app_reconnect.py`は、初回auto-discovery失敗と明示port open失敗からの回復、backoff、
HELLO/CONFIG re-handshake、`READY_DISARMED`、ARM不送信、serial不在中のARM拒否、曖昧なnodeの
BLOCKEDをFake serialで確認します。実USB抜去、COM番号変更、driver timing、実ESP32 boot timingは
hardware-only validationとして残ります。
