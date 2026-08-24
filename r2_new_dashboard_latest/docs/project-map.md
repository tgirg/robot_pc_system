# Project Map

Date: 2026-08-12

This file records the human-facing folder organization for this workspace.
It is meant to keep the project readable without moving files that scripts already depend on.

## Keep At Root

These files intentionally stay at the root because they are the command entrypoints:

| File | Role |
| --- | --- |
| `run-pc-controller.cmd` | Current real-machine PC controller launcher |
| `run-pc-controller.ps1` | PowerShell variant of the PC controller launcher |
| `run-pc-controller-3min.cmd` | Timed PC controller run |
| `run-encoder-monitor.cmd` | Encoder/RPM monitor |
| `stop-pc-controller.cmd` | Stops the current PC controller process |
| `setup-robot-dashboard.cmd` | Installs the friend dashboard dependencies |
| `run-robot-dashboard.cmd` | Starts the friend dashboard |
| `README.md` | Full operation manual |
| `00_START_HERE.md` | Short human index |
| `requirements.txt` | Current `pc_controller` dependencies |
| `pytest.ini` | Test discovery configuration |

Do not move those without updating the README, user habits, and any batch-file relative paths.

## Active Software

| Path | Keep For |
| --- | --- |
| `pc_controller/` | Existing four-wheel independent steering controller |
| `esp32_firmware/` | Existing ESP32 firmware that speaks JSON Lines |
| `config/` | Existing v29 vehicle and controller configuration |
| `apps/robot_pc_system/` | Imported friend dashboard. It is not the live 4WIS drive path yet |
| `tests/` | Regression tests for `pc_controller` |

## Hardware And Design Data

| Path | Keep For |
| --- | --- |
| `基板/` | KiCad board projects and board assets |
| `bom/` | Parts cache and BOM data |
| `drivers/` | External or reference driver packages |
| `06_3Dモデル/` | Loose STL/CAD exports that used to be at the root |
| `パンタグラフアーム/` | Pantograph arm mechanism STLs |
| `収納/` | Storage/case design files |
| `03_ハードウェア_エンコーダ/` | Encoder hardware notes and older materials |

## Documents And History

| Path | Keep For |
| --- | --- |
| `docs/` | Current documentation and research notes |
| `docs/reports/` | Standalone reports such as pin maps |
| `01_F3RC2026_ロボコン/` | Robocon-level planning and older project documents |
| `02_ソフトウェア_ESP32/` | Older ESP32 sketches and notes |
| `04_調査資料/` | Research materials |
| `05_GoogleDrive/`, `googleDrive/` | Google Drive exported or mirrored materials |
| `video/` | Video/reference media |

## Generated Or Temporary

| Path | Meaning |
| --- | --- |
| `.codex_work/` | Codex work area, temporary clones, generated checks |
| `analysis/` | Analysis outputs |
| `outputs/` | Deliverables or generated artifacts |
| `logs/` | Runtime logs |
| `99_作業用/` | Scratch and older work-in-progress material |
| `.pytest_cache/` | Test cache |
| `.venv/`, `.venv_win/` | Local virtual environments, not the preferred launch path |

Before deleting generated material, check whether it is referenced in README or a handoff note.

## 2026-08-12 Cleanup

Moved these loose root STL files into `06_3Dモデル/単体STL/` after a reference search found no matching text references:

- `アームA v1.stl`
- `アームB v1.stl`
- `カップリング v1.stl`

The move is only for readability. It does not change code, firmware, KiCad, or runtime behavior.

Also moved `PINMAP_REPORT.md` into `docs/reports/PINMAP_REPORT.md`.
