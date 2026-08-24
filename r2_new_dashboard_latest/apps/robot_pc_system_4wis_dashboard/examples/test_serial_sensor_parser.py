from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PC_DIR = PROJECT_ROOT / "pc"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from sensors import ImuState, parse_serial_sensor_line, sanitize_number


def require(line: str, expected_type: str) -> dict:
    parsed = parse_serial_sensor_line(line)
    print(f"入力: {line} -> {parsed}")
    if parsed is None or parsed.get("type") != expected_type:
        raise SystemExit(f"失敗: {line} を {expected_type} として解析できませんでした")
    return parsed


def assert_lidar_zero(state: ImuState, label: str) -> None:
    data = state.to_sensor_data()
    values = [data.lidar_front_mm, data.lidar_left_mm, data.lidar_right_mm, data.lidar_rear_mm]
    if any(value != 0 for value in values):
        raise SystemExit(f"失敗: {label} のLiDAR値が0ではありません: {values}")


def main() -> None:
    print("シリアルセンサパーサのテストを開始します。")
    imu_dummy = require("IMU_STATUS,DUMMY", "IMU_STATUS")
    imu_ok = require("IMU_STATUS,OK", "IMU_STATUS")
    imu_error = require("IMU_STATUS,ERROR", "IMU_STATUS")
    lidar_dummy = require("LIDAR_STATUS,DUMMY", "LIDAR_STATUS")
    lidar_ok = require("LIDAR_STATUS,OK", "LIDAR_STATUS")
    lidar_error = require("LIDAR_STATUS,ERROR", "LIDAR_STATUS")
    lidar = require("LIDAR,850,1200,600,2000", "LIDAR")
    imu_type = require("IMU_TYPE,BNO055", "IMU_TYPE")
    imu_addr = require("IMU_ADDR,0x28", "IMU_ADDR")
    imu = require("IMU,45.2,1.0,-0.5", "IMU")
    gyro = require("GYRO,0.01,-0.03,0.20", "GYRO")
    accel = require("ACC,0.1000,-0.0500,0.9800", "ACCEL")
    status = require("STATUS,OK", "STATUS")
    firmware = require("FW,drive_controller,0.1.0", "FW")
    lsb_id = require("LSB,ID,2026F3F_LSB_REVA_VER0,0.1.0", "LSB_ID")
    lsb_i2c = require("LSB,I2C,0x20:OK,0x29:OK", "LSB_I2C")
    lsb_pong = require("LSB,PONG,12345", "LSB_PONG")
    lsb_rate = require("LSB,RATE,100", "LSB_RATE")
    lsb_tof = require("LSB,TOF,0x29,OK,TYPE=VL53L1X,READY=1,DIST_MM=2076", "LSB_TOF")
    lsb_sens = require("LSB,SENS,7,tof=850/1200/2000/900,us=800/820/900/920/1500/1480/1200/1180,imu=45.2/1.0/-0.5", "LSB_SENS")
    lsb_err = require("LSB,ERR,I2C_TIMEOUT,0x29", "LSB_ERR")
    enc = require("ENC,698,703", "ENC")
    enc_status = require("ENC_STATUS,DUMMY", "ENC_STATUS")
    odom_status = require("ODOM_STATUS,DUMMY", "ODOM_STATUS")
    optical_status = require("OPTICAL_STATUS,OK", "OPTICAL_STATUS")
    optical_unconnected = require("OPTICAL_STATUS,UNCONNECTED", "OPTICAL_STATUS")
    odom = require("ODOM,10.5,20.0,3.2", "ODOM")
    optical = require("OPTICAL,1.5,-2.0", "OPTICAL")
    dist_status = require("DIST_STATUS,DUMMY", "DIST_STATUS")
    dist = require("DIST,front,800", "DIST")
    line_status = require("LINE_STATUS,DUMMY", "LINE_STATUS")
    line = require("LINE,reflection,80", "LINE")
    color_status = require("COLOR_STATUS,DUMMY", "COLOR_STATUS")
    color = require("COLOR,unknown", "COLOR")
    drive = require("DRIVE,100,100", "DRIVE")

    if firmware["name"] != "drive_controller" or firmware["version"] != "0.1.0":
        raise SystemExit("失敗: FW行を正しく解析できませんでした")
    if lsb_id["board"] != "2026F3F_LSB_REVA_VER0" or lsb_i2c["items"][-1] != "0x29:OK" or lsb_pong["uptime_ms"] != 12345:
        raise SystemExit("失敗: LSB ID/I2C/PONG行を正しく解析できませんでした")
    if lsb_rate["interval_ms"] != 100 or lsb_tof["tof_type"] != "VL53L1X" or lsb_tof["distance_mm"] != 2076:
        raise SystemExit("失敗: LSB RATE/TOF行を正しく解析できませんでした")
    if lsb_sens["seq"] != 7 or int(lsb_sens["tof"][0]) != 850 or int(lsb_sens["ultrasonic"][7]) != 1180:
        raise SystemExit("失敗: LSB SENS行を正しく解析できませんでした")
    if lsb_err["code"] != "I2C_TIMEOUT" or lsb_err["detail"] != "0x29":
        raise SystemExit("失敗: LSB ERR行を正しく解析できませんでした")
    if imu_type["name"] != "BNO055" or imu_addr["address"] != "0x28":
        raise SystemExit("失敗: IMU_TYPE/IMU_ADDR行を正しく解析できませんでした")
    if abs(accel["x_g"] - 0.1) > 0.001 or abs(accel["y_g"] + 0.05) > 0.001:
        raise SystemExit("失敗: ACC行を正しく解析できませんでした")
    if enc_status["status"] != "DUMMY" or odom_status["status"] != "DUMMY" or optical_status["status"] != "OK":
        raise SystemExit("失敗: STATUS行を正しく解析できませんでした")
    if optical_unconnected["status"] == "OK":
        raise SystemExit("失敗: OPTICAL_STATUS,UNCONNECTED行がOK扱いになっています")
    if int(dist["value"]) != 800 or dist["direction"] != "front":
        raise SystemExit("失敗: DIST行を正しく解析できませんでした")
    if line["name"] != "reflection" or int(line["value"]) != 80:
        raise SystemExit("失敗: LINE行を正しく解析できませんでした")
    if color["name"] != "unknown" or color_status["status"] != "DUMMY":
        raise SystemExit("失敗: COLOR行を正しく解析できませんでした")
    if abs(odom["x"] - 10.5) > 0.001 or abs(optical["dy"] + 2.0) > 0.001:
        raise SystemExit("失敗: ODOM/OPTICAL行を正しく解析できませんでした")

    invalid = parse_serial_sensor_line("UNKNOWN,abc")
    malformed_lidar = parse_serial_sensor_line("LIDAR,abc,1200")
    print(f"不正行: {invalid}")
    print(f"壊れたLiDAR行: {malformed_lidar}")
    if invalid is not None or malformed_lidar is not None:
        raise SystemExit("失敗: 不正行は無視される必要があります")

    for value in [None, "", "nan", "inf", "-inf", float("nan"), float("inf")]:
        if sanitize_number(value) != 0:
            raise SystemExit("失敗: None/NaN/inf は0に丸める必要があります")

    state = ImuState()
    for message in [lsb_id, lsb_i2c, lsb_sens]:
        state.update_from_message(message)
    data = state.to_sensor_data()
    if data.lsb_status != "OK" or data.lsb_board_id != "2026F3F_LSB_REVA_VER0" or int(data.lsb_seq) != 7:
        raise SystemExit("失敗: LSB状態がSensorDataへ反映されていません")
    if int(data.lsb_tof_front_mm) != 850 or int(data.lidar_right_mm) != 1200 or int(data.lidar_left_mm) != 900:
        raise SystemExit("失敗: LSB ToF値がLSB/LiDAR欄へ反映されていません")
    if int(data.lsb_us_rear_l_mm) != 1480 or int(data.distance_sensor_mm) != 800:
        raise SystemExit("失敗: LSB超音波値が反映されていません")
    if data.imu_source != "LSB IMU" or abs(data.imu_yaw - 45.2) > 0.001:
        raise SystemExit("失敗: LSB IMU値が反映されていません")
    state.update_from_message(lsb_err)
    data = state.to_sensor_data()
    if data.lsb_status != "ERROR" or "I2C_TIMEOUT" not in data.lsb_error:
        raise SystemExit("失敗: LSB ERR状態が反映されていません")

    state = ImuState()
    state.update_from_message(lidar_dummy)
    state.update_from_message(lidar)
    assert_lidar_zero(state, "LIDAR_STATUS,DUMMY")
    data = state.to_sensor_data()
    if data.lidar_status != "DUMMY" or data.lidar_source != "ESP32ダミー出力":
        raise SystemExit("失敗: LIDAR_STATUS,DUMMY が状態に反映されていません")

    state.update_from_message(lidar_error)
    state.update_from_message(lidar)
    assert_lidar_zero(state, "LIDAR_STATUS,ERROR")

    state.update_from_message(lidar_ok)
    state.update_from_message(lidar)
    data = state.to_sensor_data()
    if data.lidar_status != "OK" or data.lidar_source != "実データ":
        raise SystemExit("失敗: LIDAR_STATUS,OK が状態に反映されていません")
    if int(data.lidar_front_mm) != 850 or int(data.lidar_left_mm) != 1200 or int(data.lidar_rear_mm) != 2000:
        raise SystemExit("失敗: LIDAR_STATUS,OK のときだけLiDAR値が反映される必要があります")
    state.last_update_time = time.monotonic() - 10.0
    state.last_lidar_update_time = time.monotonic() - 10.0
    data = state.to_sensor_data()
    if data.lidar_status != "未接続" or any([data.lidar_front_mm, data.lidar_left_mm, data.lidar_right_mm, data.lidar_rear_mm]):
        raise SystemExit("失敗: LiDAR信号が途切れた場合は未接続・0表示に戻る必要があります")

    state = ImuState()
    for message in [imu_dummy, imu, gyro, accel, enc_status, enc, odom_status, odom, dist_status, dist, line_status, line, color_status, color]:
        state.update_from_message(message)
    data = state.to_sensor_data()
    if any([data.imu_yaw, data.gyro_x, data.accel_x_g, data.encoder_left, data.odom_dx, data.distance_sensor_mm, data.line_value]):
        raise SystemExit("失敗: DUMMY状態のセンサ値は0表示である必要があります")

    state.update_from_message(imu_ok)
    state.update_from_message(imu)
    state.update_from_message(accel)
    if state.imu_status != "OK" or state.imu_source != "実IMU":
        raise SystemExit("失敗: IMU_STATUS,OK が状態に反映されていません")
    data = state.to_sensor_data()
    if abs(data.accel_x_g - 0.1) > 0.001:
        raise SystemExit("失敗: ACC値がIMU状態へ反映されていません")

    state.update_from_message(imu_error)
    data = state.to_sensor_data()
    if state.imu_status != "ERROR" or data.imu_yaw != 0:
        raise SystemExit("失敗: IMU_STATUS,ERROR では値が0になる必要があります")

    state.update_from_message(status)
    state.update_from_message(drive)
    print("結果: 成功")


if __name__ == "__main__":
    main()
