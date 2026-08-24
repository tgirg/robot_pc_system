# Serial Node Inventory

## Purpose

複数ESP32を接続する将来構成で、発見できたportを順番やCOM番号だけで信用しないための
offline-testableな管理基盤です。現時点では実機制御loopへ複数linkを接続せず、
`--list-nodes`時のinventory検証として独立させています。

## Manifest

`config/node_manifest.json`は、active firmwareで確認できるdrive nodeだけをrequiredとして定義します。

```json
{
  "schema_version": 1,
  "nodes": [
    {
      "node_id": "mcb44_drive_main",
      "role": "drive",
      "required": true
    }
  ]
}
```

未確認のsensor node名やroleは既定manifestへ推測で追加しません。将来nodeを追加する場合は、
firmwareの`node_identity`と一致する`node_id` / `role`を明示し、必須でなければ
`"required": false`とします。

## Validation

```powershell
.\run-pc-controller.cmd --list-nodes --node-manifest config\node_manifest.json
```

判定は次の通りです。

- required node missing: `BLOCKED`
- duplicate `node_id` on multiple ports: `BLOCKED`
- manifestのnode_idと発見roleが不一致: `BLOCKED`
- identityにnode_idまたはroleがない: `BLOCKED`
- optional node missing: warning、READYを維持
- manifest外の完全なidentity: warning、READYを維持
- probe error / identityなしport: warning。ただしrequired nodeも欠落する場合は別途`BLOCKED`

`open_discovered_serial_link()`も、`node_id`を指定した場合にroleまで一致しなければ接続しません。
同一node_idが複数portに現れた場合は全候補をcloseして選択を拒否します。
通常の無期限control実行は対象nodeが見つからない場合にSAFE常駐retryを行いますが、複数一致は
`AmbiguousSerialNodeError`として自動retryしません。startup/reconnect flowは
`docs/serial_reconnect.md`を参照してください。

## Safety boundary

- このinventory確認だけでARMしません。
- manifestはCOM番号を固定せず、identityを照合します。
- 現時点のruntime control linkはdrive node 1台のままです。
- 実USB、hub、再enumeration、複数ESP32同時通信は未検証です。
- software READYは配線、電源、モータ、sensorの物理的readyを意味しません。
