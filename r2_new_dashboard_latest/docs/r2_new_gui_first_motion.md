# R2 first motion through the new GUI

This path uses the new shared dashboard as the operator application. It does
not launch either legacy dashboard or `run-pc-controller.cmd`. The shared GUI
owns one `ControllerApp`, one controller input, and one USB serial transport.

## Retained R2 reference

- Drive type: 4WIS (`FL`, `FR`, `RL`, `RR`)
- Transport: protocol-v1 NDJSON over USB serial
- Startup: `DISARM -> HELLO -> CONFIG -> READY_DISARMED`
- ARM: hold `L1 + R1 + Cross` for one second after releasing all ARM buttons once
- Current physical front is the configured `RL/RR` side because `logical_front=REAR`.
- The current-front `RL/RR` motors and encoders retain the common polarity used by forward translation. Pivot motor-direction corrections must not change this global forward polarity.
- All four servos currently use `direction_inverted=false` so an identical four-wheel steering command remains physically parallel. Re-check zero-radius pivot, parallel translation, and mixed translation/rotation after applying this hardware-specific setting.
- The current rear-side `FL/FR` hardware assignment is left/right swapped to match the reversed-front chassis: motor physical `[1,2]`, encoder physical `[1,0]`, and PCA9685 channels `[5,6]` with their corresponding center pulses `[1580,1490]`.
- SAFE: `OPTIONS`
- Logical front: `controller_mapping.json` `logical_front=REAR` rotates translation by 180 degrees while preserving rotation direction
- Current PS4 axis correction: `invert_vy=false` and `invert_omega=true`. The omega inversion makes a right-stick right command select the current-front right turn, including both pivot direction and the correct inner-wheel side.
- Pivot-only wheel correction is `[true,true,false,false]` in `FL/FR/RL/RR` order. With the reversed-front chassis this preserves the current rear pair and reverses only the current front pair relative to the previous operator input sign.
- First-motion output clamp: maximum PWM 120; a smaller value may be selected
- Window close: zero drive (when armed), then DISARM, then serial close

The existing `config/vehicle_config.json` and
`config/controller_mapping.json` retain the proven wheel mapping, servo
centres/inversions, axis mapping, and low-speed controller scaling. The old GUI
code is not copied into the new output path.

## 1. Actuator-output-disabled connection check

Connect the R2 ESP32 and controller, close Arduino Serial Monitor, then run:

```cmd
.\run-r2-new-dashboard.cmd --port COM7
```

Omit `--port COM7` to use drive-node auto-discovery. This mode performs the
safe handshake and displays real telemetry, but controller ARM and motion axes
are suppressed.

Confirm in the new GUI:

- R2 is `ONLINE`
- Safety is `SAFE`
- state becomes `READY_DISARMED`
- R1 remains `OFFLINE` and its selector is disabled
- the detected node is `mcb44_drive_main / drive`

## 2. Lifted-wheel first motion

Securely lift all wheels, keep an operator at the physical power cutoff, and
start with PWM 60:

```cmd
.\run-r2-new-dashboard.cmd --port COM7 --enable-motion --max-pwm 60
```

Release all ARM buttons once after startup. Then hold `L1 + R1 + Cross` for one
second. Test one small input at a time and press `OPTIONS` before changing the
test condition. Closing the GUI also sends zero drive and DISARM.

After wheel order, steering direction, motor direction, and encoder direction
match the GUI, repeat at no more than PWM 120:

```cmd
.\run-r2-new-dashboard.cmd --port COM7 --enable-motion --max-pwm 120
```

On 2026-08-24 the lifted-wheel check confirmed all four motor/encoder pairs,
right-pivot signs `[-,+,+,-]`, and final `SAFE / armed=false / PWM=0 / fault=0`.
For a current-front right arc, old-logical `FL/RL` are the inner pair and
`FR/RR` are the outer pair. Open-loop static compensation is enabled so the
inner pair does not stall below motor breakaway: measured PWM was
`[-50,-59,-44,-60]` with encoder deltas
`[-6430,-15645,-4407,-11729]`. Ground-contact and load behavior remain to be
validated by the operator.

## Deferred for first motion

Effect sounds, controller vibration/light feedback, live calibration apply,
autonomy, field navigation, and mechanism outputs are not part of this first
motion path.
