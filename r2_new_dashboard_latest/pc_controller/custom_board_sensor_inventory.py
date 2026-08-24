"""Formal R2 custom ESP32 sensor connector inventory."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CustomBoardSensor:
    name: str
    gpio: int | None
    purpose: str
    category: str
    unit: str
    note: str = ""

    @property
    def gpio_label(self) -> str:
        return f"GPIO{self.gpio}" if self.gpio is not None else "-"


CUSTOM_BOARD_GPIO_MAP: tuple[CustomBoardSensor, ...] = (
    CustomBoardSensor("FL", 13, "前左の距離センサ", "距離センサ", "RAW"),
    CustomBoardSensor("FR", 14, "前右の距離センサ", "距離センサ", "RAW"),
    CustomBoardSensor("RR", 27, "右後の距離センサ", "距離センサ", "RAW"),
    CustomBoardSensor("BR", 26, "後右の距離センサ", "距離センサ", "RAW"),
    CustomBoardSensor("BL", 25, "後左の距離センサ", "距離センサ", "RAW"),
    CustomBoardSensor("LB", 33, "左後の距離センサ", "距離センサ", "RAW"),
    CustomBoardSensor("LF", 32, "左前の距離センサ", "距離センサ", "RAW"),
    CustomBoardSensor(
        "US1",
        35,
        "超音波センサ1",
        "超音波",
        "mm",
        "GPIO35は入力専用。1線式Trig/Echo超音波ではTrig出力不可",
    ),
    CustomBoardSensor("US2", 23, "超音波センサ2", "超音波", "mm"),
)

R2_ADDITIONAL_SENSOR_CHECKS: tuple[CustomBoardSensor, ...] = (
    CustomBoardSensor("ENCODER", None, "4輪エンコーダー", "エンコーダー", "count/rpm", "Drive Diagnosticのテレメトリで確認"),
    CustomBoardSensor("IMU", None, "9軸IMU", "IMU", "deg/dps", "接続方式とGPIOは別資料で確定"),
    CustomBoardSensor("OPTICAL", None, "光学式オドメトリ", "光学式", "dx/dy", "接続方式とGPIOは別資料で確定"),
)

R2_SENSOR_CHECK_ORDER: tuple[CustomBoardSensor, ...] = (
    *CUSTOM_BOARD_GPIO_MAP,
    *R2_ADDITIONAL_SENSOR_CHECKS,
)

