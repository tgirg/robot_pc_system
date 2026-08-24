from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from arduino_tools import ArduinoCliResult, compile_drive_controller, scan_firmware_text

from .ui_feedback import format_elapsed_time, show_error, show_info, show_success
from .ui_helpers import boxed, make_button, make_notice


I2C_SCANNER_TEMPLATE = """#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(21, 22);
  Serial.println("I2C scan start");
  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("I2C device found at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
    }
  }
  Serial.println("I2C scan done");
}

void loop() {
}
"""

SERIAL_TEST_TEMPLATE = """void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("BOOT,TEST_READY");
}

void loop() {
  Serial.println("STATUS,OK");
  delay(500);
}
"""

DRIVE_VEL_TEST_TEMPLATE = """void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("FW,drive_controller,free_edit_test");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\\n');
    line.trim();
    if (line.startsWith("DRIVE VEL")) {
      Serial.println("DRIVE,100,100");
    } else if (line == "DRIVE STOP" || line == "EMERGENCY_STOP") {
      Serial.println("DRIVE,0,0");
    } else {
      Serial.print("RX,");
      Serial.println(line);
    }
  }
  Serial.println("STATUS,OK");
  delay(500);
}
"""

IMU_TEST_TEMPLATE = """void setup() {
  Serial.begin(115200);
}

void loop() {
  Serial.println("IMU_STATUS,OK");
  Serial.println("IMU,10.0,1.0,2.0");
  Serial.println("GYRO,0.1,0.2,0.3");
  delay(500);
}
"""

LIDAR_TEST_TEMPLATE = """void setup() {
  Serial.begin(115200);
}

void loop() {
  Serial.println("LIDAR_STATUS,OK");
  Serial.println("LIDAR,800,1200,900,1500");
  delay(500);
}
"""

SAFE_DUMMY_DRIVE_TEMPLATE = """// 安全ダミー drive_controller
// 実モータ出力は使いません。

#define MOTOR_OUTPUT_ENABLED 0
#define USE_REAL_IMU 0
#define USE_REAL_LIDAR 0

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("FW,drive_controller,safe_dummy");
  Serial.println("READY,SAFE_DUMMY");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("ACK,");
      Serial.println(line);
    }
  }

  Serial.println("IMU_STATUS,DUMMY");
  Serial.println("LIDAR_STATUS,DUMMY");
  Serial.println("ENC,0,0");
  Serial.println("MOTOR_DUMMY,0,0");
  Serial.println("STATUS,OK");
  delay(500);
}
"""


TEMPLATES = {
    "I2Cスキャナ": (I2C_SCANNER_TEMPLATE, False),
    "最小Serialテスト": (SERIAL_TEST_TEMPLATE, False),
    "DRIVE VEL応答テスト": (DRIVE_VEL_TEST_TEMPLATE, False),
    "IMU出力テスト": (IMU_TEST_TEMPLATE, False),
    "LiDAR出力テスト": (LIDAR_TEST_TEMPLATE, False),
    "安全ダミーdrive_controller": (SAFE_DUMMY_DRIVE_TEMPLATE, True),
}


class FirmwareCompileWorker(QThread):
    result_ready = Signal(object)
    error_ready = Signal(str)

    def __init__(self, fqbn: str) -> None:
        super().__init__()
        self.fqbn = fqbn

    def run(self) -> None:
        try:
            self.result_ready.emit(compile_drive_controller(self.fqbn))
        except Exception as exc:
            self.error_ready.emit(str(exc))


class FirmwareEditorWidget(QWidget):
    def __init__(self, host) -> None:
        super().__init__()
        self.host = host
        self.project_root = host._project_root()
        self.esp32_root = (self.project_root / "esp32").resolve()
        self.current_path = (self.esp32_root / "drive_controller" / "drive_controller.ino").resolve()
        self.worker: FirmwareCompileWorker | None = None
        self.loading = False
        self.dirty = False
        self.compile_started_at = 0.0

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.status_label = QLabel("未保存の変更なし")
        self.status_label.setObjectName("diagnosticLabel")
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlaceholderText("Arduino / ESP32 のコードを自由に入力または貼り付けできます。")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1200)
        self.fqbn_edit = QLineEdit(str(host.local_settings.get("last_upload_fqbn", "esp32:esp32:esp32")))
        self.template_combo = QComboBox()
        self.template_combo.addItems(list(TEMPLATES.keys()))
        self.operation_label = QLabel("状態: 待機中")
        self.operation_label.setObjectName("diagnosticLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        self._build()
        self._connect()
        self.load_file(self.current_path)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(make_notice(
            "ESP32フォルダ内のファームウェアを直接編集できます。保存やコンパイルは手動です。危険そうなコードは警告しますが、自由編集は止めません。"
        ))

        file_box = QWidget()
        file_layout = QGridLayout(file_box)
        file_layout.addWidget(QLabel("現在のファイル表示"), 0, 0)
        file_layout.addWidget(self.path_edit, 0, 1)
        file_layout.addWidget(QLabel("FQBN"), 1, 0)
        file_layout.addWidget(self.fqbn_edit, 1, 1)
        file_layout.setColumnStretch(1, 1)
        layout.addWidget(file_box)
        layout.addWidget(self.status_label)
        layout.addWidget(self.operation_label)
        layout.addWidget(self.progress)

        buttons = QWidget()
        button_layout = QHBoxLayout(buttons)
        for button in [
            make_button("読み込み", self.choose_file),
            make_button("保存", self.save),
            make_button("名前を付けて保存", self.save_as),
            make_button("変更を破棄", self.discard_changes),
            make_button("このコードをコンパイル", self.compile_current_code),
            make_button("書き込み画面へ移動", self.move_to_upload_panel),
            make_button("シリアルモニタへ移動", self.move_to_serial_monitor),
        ]:
            button_layout.addWidget(button)
        button_layout.addStretch(1)
        layout.addWidget(buttons)

        template_row = QWidget()
        template_layout = QHBoxLayout(template_row)
        template_layout.addWidget(QLabel("テンプレート挿入"))
        template_layout.addWidget(self.template_combo)
        template_layout.addWidget(make_button("挿入", self.insert_template))
        template_layout.addWidget(make_button("コード編集エリアをクリア", self.clear_editor))
        template_layout.addStretch(1)
        layout.addWidget(template_row)
        layout.addWidget(make_notice("書き込み後は「シリアルモニタ」で出力確認できます。I2CスキャナやSerial.printlnの生ログ確認に使えます。"))

        layout.addWidget(boxed("コード編集エリア", self.editor), 4)
        layout.addWidget(boxed("コンパイル / 保存ログ", self.log_view), 2)

    def _connect(self) -> None:
        self.editor.textChanged.connect(self._mark_dirty)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "ESP32ファイルを開く",
            str(self.current_path.parent),
            "ESP32/Arduino/C++ (*.ino *.h *.hpp *.c *.cpp);;すべてのファイル (*)",
        )
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> bool:
        path = path.resolve()
        show_info(self.operation_label, "読み込み中...")
        if not self._is_under_esp32(path):
            QMessageBox.warning(
                self,
                "編集範囲外",
                "このエディタでは安全のため esp32 フォルダ内のファイルだけ編集できます。",
            )
            return False
        if self.dirty and not self._ask_discard_changes():
            return False
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.warning(self, "読み込み失敗", f"ファイルを読み込めませんでした。\n{exc}")
            return False
        self.loading = True
        self.current_path = path
        self.path_edit.setText(str(path))
        self.editor.setPlainText(text)
        self.loading = False
        self.dirty = False
        self._update_dirty_label()
        self.append_log(f"読み込み: {path}")
        show_success(self.operation_label, "読み込み完了")
        return True

    def save(self) -> bool:
        return self._save_to_path(self.current_path)

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "名前を付けて保存",
            str(self.current_path),
            "ESP32/Arduino/C++ (*.ino *.h *.hpp *.c *.cpp);;すべてのファイル (*)",
        )
        if not path:
            return False
        return self._save_to_path(Path(path).resolve(), update_current=True)

    def discard_changes(self) -> None:
        if self.load_file(self.current_path):
            self.append_log("変更を破棄して再読み込みしました。")

    def clear_editor(self) -> None:
        self.editor.clear()
        self.append_log("コード編集エリアをクリアしました。")

    def compile_current_code(self) -> None:
        if not self._confirm_safety("コンパイル前の確認"):
            self.append_log("コンパイルをキャンセルしました。")
            return
        if self.dirty:
            answer = QMessageBox.question(
                self,
                "保存確認",
                "保存してからコンパイルしますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.append_log("未保存のためコンパイルをキャンセルしました。")
                return
            if not self.save():
                return
        if self.worker is not None and self.worker.isRunning():
            self.append_log("コンパイル中です。完了までお待ちください。")
            show_info(self.operation_label, "コンパイル中です。完了までお待ちください。")
            return
        self.host.local_settings["last_upload_fqbn"] = self._current_fqbn()
        self.host._save_local_settings()
        self.append_log("コンパイルを開始しました。")
        self.compile_started_at = time.time()
        self.progress.show()
        show_info(self.operation_label, "コンパイル中...")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation("ファームウェアをコンパイル中...", "busy")
        self.worker = FirmwareCompileWorker(self._current_fqbn())
        self.worker.result_ready.connect(self._handle_compile_result)
        self.worker.error_ready.connect(self._handle_compile_error)
        self.worker.finished.connect(self._clear_worker)
        self.worker.start()

    def move_to_upload_panel(self) -> None:
        if self.dirty:
            answer = QMessageBox.question(
                self,
                "保存確認",
                "未保存の変更があります。保存してから書き込み画面へ移動しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            if not self.save():
                return
        self.host.switch_to_tab("診断")
        self.append_log("書き込み画面へ移動しました。自動書き込みは行いません。")
        self.host._log("ESP32書き込み画面へ移動しました。自動書き込みは行いません。")

    def move_to_serial_monitor(self) -> None:
        self.host.switch_to_tab("診断")
        self.append_log("シリアルモニタへ移動しました。書き込み後の出力確認に使ってください。")
        self.host._log("シリアルモニタへ移動しました。")

    def insert_template(self) -> None:
        name = self.template_combo.currentText()
        template, replace_all = TEMPLATES[name]
        if replace_all:
            answer = QMessageBox.question(
                self,
                "テンプレート確認",
                "現在の内容を置き換えますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.editor.setPlainText(template)
            self.append_log(f"テンプレートで置き換え: {name}")
            return
        self.editor.insertPlainText(template)
        self.append_log(f"テンプレート挿入: {name}")

    def _save_to_path(self, path: Path, update_current: bool = False) -> bool:
        path = path.resolve()
        show_info(self.operation_label, "保存中...")
        if not self._is_under_esp32(path):
            QMessageBox.warning(
                self,
                "編集範囲外",
                "このエディタでは安全のため esp32 フォルダ内のファイルだけ編集できます。",
            )
            return False
        if not self._confirm_safety("保存前の確認"):
            self.append_log("保存をキャンセルしました。")
            return False
        if path.exists() and not self._create_backup(path):
            if not self._ask_continue_after_backup_failure():
                self.append_log("バックアップ失敗のため保存をキャンセルしました。")
                return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.editor.toPlainText(), encoding="utf-8", newline="\n")
        except OSError as exc:
            QMessageBox.warning(self, "保存失敗", f"保存できませんでした。\n{exc}")
            return False
        if update_current:
            self.current_path = path
            self.path_edit.setText(str(path))
        self.dirty = False
        self._update_dirty_label()
        self.append_log(f"保存しました: {path}")
        self.host._log(f"ESP32プログラムを保存しました: {path.name}")
        show_success(self.operation_label, "保存完了")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"ファームウェアを保存しました: {path.name}", "success")
        return True

    def _create_backup(self, path: Path) -> bool:
        backup_dir = self.project_root / "backups" / "firmware"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.stem}_{timestamp}{path.suffix}"
        backup_path = backup_dir / backup_name
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)
        except OSError as exc:
            self.append_log(f"バックアップ作成失敗: {exc}")
            return False
        self.append_log(f"バックアップを作成しました: {backup_path}")
        return True

    def _confirm_safety(self, title: str) -> bool:
        warnings = scan_firmware_text(self.editor.toPlainText())
        if not warnings:
            return True
        message = (
            "注意が必要なコードが含まれています。\n"
            "現在モータは未接続でも、将来接続時に動作する可能性があります。\n"
            "内容を理解したうえで続行してください。\n\n"
            + "\n".join(f"- {warning}" for warning in warnings)
        )
        if any("MOTOR_OUTPUT_ENABLED 1" in warning for warning in warnings):
            message = (
                "MOTOR_OUTPUT_ENABLED 1 が含まれています。\n"
                "実モータ接続時はモータが動く可能性があります。\n\n"
                + message
            )
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(message)
        continue_button = box.addButton("続行", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() == continue_button

    def _ask_continue_after_backup_failure(self) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("バックアップ失敗")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("バックアップ作成に失敗しました。このまま保存しますか？")
        continue_button = box.addButton("続行", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() == continue_button

    def _ask_discard_changes(self) -> bool:
        answer = QMessageBox.question(
            self,
            "変更確認",
            "未保存の変更があります。破棄して読み込みますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _handle_compile_result(self, result: ArduinoCliResult) -> None:
        self.progress.hide()
        elapsed = format_elapsed_time(time.time() - self.compile_started_at) if self.compile_started_at else "-"
        if result.success:
            show_success(self.operation_label, f"コンパイル成功（{elapsed}）")
        else:
            show_error(self.operation_label, f"コンパイル失敗（{elapsed}）。ログを確認してください。")
        self.append_log(self._format_result("コンパイル", result))
        self.host.compile_checked = True
        self.host.compile_ok = result.success
        self.host._log("ファームウェアエディタからコンパイル成功" if result.success else "ファームウェアエディタからコンパイル失敗")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(
                "ファームウェアのコンパイルに成功しました" if result.success else "ファームウェアのコンパイルに失敗しました",
                "success" if result.success else "error",
            )
        if hasattr(self.host, "_update_workflow_state"):
            self.host._update_workflow_state()

    def _handle_compile_error(self, message: str) -> None:
        self.progress.hide()
        show_error(self.operation_label, f"コンパイルエラー: {message}")
        self.append_log(f"コンパイルエラー: {message}")
        self.host._log(f"ファームウェアエディタのコンパイルエラー: {message}")
        if hasattr(self.host, "notify_operation"):
            self.host.notify_operation(f"ファームウェアのコンパイルエラー: {message}", "error")

    def _clear_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _format_result(self, title: str, result: ArduinoCliResult) -> str:
        return "\n".join(
            [
                f"=== {title} ===",
                f"結果: {'成功' if result.success else '失敗'}",
                f"戻り値: {result.return_code}",
                "コマンド:",
                " ".join(result.command),
                "--- stdout ---",
                result.stdout.strip() or "(なし)",
                "--- stderr ---",
                result.stderr.strip() or "(なし)",
                "",
            ]
        )

    def _mark_dirty(self) -> None:
        if self.loading:
            return
        self.dirty = True
        self._update_dirty_label()

    def _update_dirty_label(self) -> None:
        self.status_label.setText("未保存の変更あり" if self.dirty else "未保存の変更なし")
        if self.dirty:
            self.status_label.setStyleSheet("color:#fde68a; font-weight:700;")
        else:
            self.status_label.setStyleSheet("color:#86efac; font-weight:700;")

    def _current_fqbn(self) -> str:
        return self.fqbn_edit.text().strip() or "esp32:esp32:esp32"

    def _is_under_esp32(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.esp32_root)
            return True
        except ValueError:
            return False

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {text}")


def create_firmware_editor_panel(host) -> QWidget:
    return boxed("ESP32プログラム編集", FirmwareEditorWidget(host))
