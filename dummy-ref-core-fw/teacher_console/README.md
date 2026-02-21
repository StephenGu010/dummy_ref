# Teacher Console (Ubuntu22.04)

Desktop GUI teacher console for a 6-axis robot arm, based on the existing ASCII firmware protocol.

## What Is New

- Legacy motion commands kept compatible (`!START`, `!STOP`, `!DISABLE`, `#CMDMODE`, `#GETJPOS`, `>`, `$...`)
- Added lighting commands:
  - `!LEDON`, `!LEDOFF`
  - `!RGBON`, `!RGBOFF`
  - `#RGBMODE <mode>`
  - `#RGBCOLOR <r> <g> <b>`
- Added status queries:
  - `#GETMODE`
  - `#GETENABLE`
  - `#GETRGB`
- UI layout adjusted for 1366x768, with collapsible advanced panels
- Serial connect path now accepts both `timeout` and `timeout_s` for compatibility

## CMDMODE Naming

Mode IDs are unchanged; display naming is normalized:

- `1`: `SEQ_POINT` (sequential point-to-point)
- `2`: `INT_POINT` (interruptible point-to-point)
- `3`: `CONT_TRAJ` (continuous trajectory stream)
- `4`: `MOTOR_TUNE` (motor tuning)
- `5`: `COMP_CURRENT` (compliant current mode, `$i1..i6`)

## Safety Semantics

- `!STOP` behavior is kept for compatibility (legacy semantics).
- Recommended emergency chain in host app is:
  - `!STOP`
  - `$0,0,0,0,0,0`
  - `!DISABLE`

Why this matters:

- `$0,0,0,0,0,0` means current setpoints become zero.
- It does **not** mean motor disable.
- To fully release holding behavior, send `!DISABLE`.

## Runtime Dependencies

```bash
python3 -m pip install -r teacher_console/requirements.txt
```

## Launch

From project root:

```bash
python3 -m teacher_console.main --config config/robot_profile.yaml
```

Optional serial override:

```bash
python3 -m teacher_console.main --config config/robot_profile.yaml --port /dev/ttyACM0
```

## Step-By-Step First Run

1. Connect robot USB serial and confirm device node:
   - Example: `/dev/ttyACM0`
2. Start GUI.
3. Top bar:
   - choose port
   - click `Connect`
4. Dashboard -> `Setup / Diagnostics`:
   - click `Select URDF`
   - confirm top label shows `Model: Loaded`
5. Click `!START`.
6. Start `Zero-G` or `Impedance` in `Modes`.
7. Emergency test:
   - click `EMERGENCY`
   - verify chain executed and robot disabled.

## Lighting Control

You can control lighting from serial console or GUI `Modes -> Lighting`.

Serial examples:

```text
!LEDON
!LEDOFF
!RGBON
!RGBOFF
#RGBMODE 0
#RGBCOLOR 255 120 40
#GETRGB
```

RGB mode table:

- `0 RAINBOW`
- `1 FADE`
- `2 BLINK`
- `3 ALL_RED`
- `4 ALL_GREEN`
- `5 ALL_BLUE`
- `6 ALL_OFF`
- `7 CUSTOM_COLOR`

## Teach And Program

- Teach supports recording while connected, even when robot is disabled.
- `Play Recorded` auto-starts robot when needed.
- Program page keeps primary actions visible; edit actions are in collapsible panel.

## Troubleshooting

### 1) `SerialClient.connect() got an unexpected keyword argument 'timeout'`

Cause: mixed versions of `serial_client.py`.

Fix:

- Use this repo as single source.
- Relaunch after updating files.
- Current code supports both `timeout` and `timeout_s`.

### 2) `timeout waiting reply for '!HOME'`

`!HOME` remains manual only. It is not used in automatic startup flow.

If you trigger it manually, ensure:

- device is connected
- no concurrent blocking request is running
- firmware is responsive

### 3) `model is not loaded`

Check:

1. URDF path exists and readable
2. pinocchio import is valid in current Python env
3. `joint_map`, `joint_sign`, `joint_offset_deg` are valid

## Notes

- Current clamp is still `±1.5 A` by default.
- In mode `5`, `$...` commands are meaningful; in other modes they do not drive current control logic.
