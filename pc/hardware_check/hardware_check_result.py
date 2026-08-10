from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class HardwareCheckResult:
    timestamp: str
    selected_com_port: str
    baudrate: int
    esp32_connected: bool = False
    status_received: bool = False
    imu_received: bool = False
    imu_status: str = "no_data"
    lidar_received: bool = False
    lidar_status: str = "no_data"
    encoder_received: bool = False
    motor_dummy_received: bool = False
    test_command_sent: bool = False
    test_response_received: bool = False
    stop_sent: bool = False
    stop_response_received: bool = False
    final_result: str = "failure"
    error_message: str = ""
    raw_lines: list[str] = field(default_factory=list)
    hardware_profile_summary: str = ""
    safety_checklist: dict[str, bool] = field(default_factory=dict)
    motor_output_enabled: str = "0"
    use_real_imu: str = "0"
    use_real_lidar: str = "0"

    def to_dict(self) -> dict:
        return asdict(self)

    def result_text(self) -> str:
        labels = {
            "success": "成功",
            "partial_failure": "一部失敗",
            "failure": "失敗",
        }
        return labels.get(self.final_result, self.final_result)

    @staticmethod
    def ok_text(value: bool) -> str:
        return "OK" if value else "未確認"

    @staticmethod
    def sensor_status_text(status: str) -> str:
        labels = {
            "dummy": "OK（ESP32ダミー出力）",
            "ok": "OK",
            "error": "エラー",
            "no_data": "未確認",
        }
        return labels.get(status, status)

    def to_text(self) -> str:
        lines = [
            "ロボットPC 実機クイック確認結果",
            f"日時: {self.timestamp}",
            f"COMポート: {self.selected_com_port or '-'}",
            f"通信速度: {self.baudrate}",
            "",
            f"結果: {self.result_text()}",
        ]
        if self.error_message:
            lines.append(f"エラー: {self.error_message}")
        lines.extend(
            [
                "",
                "チェック項目:",
                f"ESP32接続: {self.ok_text(self.esp32_connected)}",
                f"STATUS受信: {self.ok_text(self.status_received)}",
                f"IMU受信: {self.sensor_status_text(self.imu_status)}",
                f"LiDAR受信: {self.sensor_status_text(self.lidar_status)}",
                f"エンコーダ受信: {self.ok_text(self.encoder_received)}",
                f"モータダミー受信: {self.ok_text(self.motor_dummy_received)}",
                f"テスト送信: {self.ok_text(self.test_command_sent)}",
                f"テスト応答: {self.ok_text(self.test_response_received)}",
                f"STOP送信: {self.ok_text(self.stop_sent)}",
                f"STOP応答: {self.ok_text(self.stop_response_received)}",
                "",
                "受信ログ:",
            ]
        )
        if self.raw_lines:
            lines.extend(self.raw_lines)
        else:
            lines.append("受信ログなし")
        if self.hardware_profile_summary:
            lines.extend(["", self.hardware_profile_summary])
        if self.safety_checklist:
            lines.append("")
            lines.append("実機接続前チェックリスト:")
            for name, checked in self.safety_checklist.items():
                lines.append(f"{name}: {'OK' if checked else '未確認'}")
        lines.extend(
            [
                "",
                "安全フラグ:",
                f"MOTOR_OUTPUT_ENABLED: {self.motor_output_enabled}",
                f"USE_REAL_IMU: {self.use_real_imu}",
                f"USE_REAL_LIDAR: {self.use_real_lidar}",
            ]
        )
        return "\n".join(lines) + "\n"
