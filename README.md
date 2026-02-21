# dummy_ref 固件改动说明


## 1. 改动总览

本次版本基于木子晓文固件进行开发，仓库链接：https://gitee.com/switchpi/dummy/tree/auk/firmware
在指令完全兼容稚晖君原版固件指令的前提下，并沿用其命名风格，完成了三类功能添加：

1. 增加RGB开关功能：可通过RGB指令 控制和查询状态。
2. 增加RGB颜色自定义：可通过#RGBCOLOR <r> <g> <b>自定义rgb颜色
3. 增加电流控制功能：`$i1..i6` 输入、`±1.5A` 限幅、200ms 看门狗清零。

## 2. 改了哪里


1. `UserApp/protocols/ascii_protocol.cpp`
2. `Robot/instances/dummy_robot.h`
3. `Robot/instances/dummy_robot.cpp`
4. `UserApp/main.cpp`
5. `Bsp/gpio/rgb.hpp`
6. `Bsp/gpio/rgb.cpp`


## 3. 增加了哪些功能

### 3.1 灯光控制能力

新增/可用命令：

- `!LEDON`, `!LEDOFF`
- `!RGBON`, `!RGBOFF`
- `#RGBMODE <mode>`
- `#RGBCOLOR <r> <g> <b>`
- `#GETRGB`

并支持 `CUSTOM_COLOR`（模式号见下文）。

### 3.2 状态查询能力

新增查询：

- `#GETMODE`
- `#GETENABLE`
- `#GETRGB`

### 3.3 模式命名标准化

- 协议短名：`SEQ_POINT / INT_POINT / CONT_TRAJ / MOTOR_TUNE / COMP_CURRENT`
- OLED 短名：`SEQ / INT / TRJ / TUNE / CURR`

### 3.4 柔顺电流模式强化

- `$i1..i6` 仅在 `CMDMODE=5` 解析生效
- 每轴电流限幅：`±1.5A`
- 看门狗：超过 `200ms` 未收到新 `$...` 自动清零

### 3.5 安全语义明确

- `!STOP` 语义保持兼容
- `$0,0,0,0,0,0` 仅清电流，不等于去使能
- 彻底释放请执行 `!DISABLE`

## 4. 通信方式与通道行为

### 4.1 USB CDC ASCII

支持完整命令前缀：`!`, `#`, `>`, `@`, `&`, `$`。

### 4.2 UART4 ASCII

当前实现与 USB 一致，也支持：`!`, `#`, `>`, `@`, `&`, `$`。

### 4.3 UART5

当前函数为空实现（占位），不处理 ASCII 命令。

### 4.4 CAN（内部执行层通信）

关节执行层走 CAN，不作为上位机 ASCII 命令接口。

## 5. 串口命令清单（ASCII）

### 5.1 全局规则

| 项 | 规则 |
|---|---|
| 命令前缀 | `!` 系统控制，`#` 查询/设置，`>` `@` `&` 运动流，`$` 电流流 |
| 行结束 | 建议 `\n` |
| 典型回包 | 成功 `ok ...`；失败 `error ...` |
| 流命令回包 | 先回队列余量（整数），执行完成后再回 `ok` |

### 5.2 `!` 系统控制命令

| 命令 | 输入格式 | 成功回包 | 备注 |
|---|---|---|---|
| `!START` | `!START` | `Started ok` | 仅使能 |
| `!STOP` | `!STOP` | `Stopped ok` | 兼容旧语义 |
| `!DISABLE` | `!DISABLE` | `Disabled ok` | 彻底去使能 |
| `!HOME` | `!HOME` | `Homing ok` | 回包已规范为 Homing |
| `!RESET` | `!RESET` | `Started ok` | 回到 resting |
| `!CALIBRATION` | `!CALIBRATION` | `calibration ok` | 标定入口 |
| `!LEDON` | `!LEDON` | `ok LED ON` | 开 LED |
| `!LEDOFF` | `!LEDOFF` | `ok LED OFF` | 关 LED |
| `!RGBON` | `!RGBON` | `ok RGB ON` | 开 RGB |
| `!RGBOFF` | `!RGBOFF` | `ok RGB OFF` | 关 RGB |

### 5.3 `#` 查询与设置命令

#### 5.3.1 状态查询

| 命令 | 输入格式 | 成功回包 |
|---|---|---|
| `#GETJPOS` | `#GETJPOS` | `ok j1 j2 j3 j4 j5 j6` |
| `#GETLPOS` | `#GETLPOS` | `ok x y z a b c` |
| `#GETMODE` | `#GETMODE` | `ok <num> <name>` |
| `#GETENABLE` | `#GETENABLE` | `ok 0/1` |
| `#GETRGB` | `#GETRGB` | `ok <rgb_enable> <rgb_mode> <r> <g> <b> <led_enable>` |

#### 5.3.2 模式与灯光设置

| 命令 | 输入格式 | 成功回包 | 失败回包 |
|---|---|---|---|
| `#CMDMODE` | `#CMDMODE <1~5>` | `ok Set command mode to [m] (<name>)` | `error BAD_CMDMODE`（仅格式错误时） |
| `#RGBMODE` | `#RGBMODE <mode>` | `ok RGBMODE [m]` | `error BAD_RGBMODE` |
| `#RGBCOLOR` | `#RGBCOLOR <r> <g> <b>` | `ok RGBCOLOR [r g b]` | `error BAD_RGBCOLOR` / `error RGB_OUT_OF_RANGE` |

#### 5.3.3 电机维护命令

| 命令 | 输入格式 | 成功回包 | 失败回包 |
|---|---|---|---|
| `#SET_DCE_KP` | `#SET_DCE_KP <node> <kp>` | `ok SET MOTOR [n] DCE_KP [v]` | `error ... is wrong` |
| `#SET_DCE_KI` | `#SET_DCE_KI <node> <ki>` | `ok SET MOTOR [n] DCE_KI [v]` | `error ... is wrong` |
| `#SET_DCE_KD` | `#SET_DCE_KD <node> <kd>` | `ok SET MOTOR [n] DCE_KD [v]` | `error ... is wrong` |
| `#REBOOT` | `#REBOOT <node>` | `ok REBOOT MOTOR [n]` | `error ... is wrong` |

`node` 允许范围：`1~6`。

### 5.4 `>` `@` `&` 运动流命令

| 命令 | 输入格式 | 前置条件 | 立即回包 | 执行回包 |
|---|---|---|---|---|
| `>` | `>j1,j2,j3,j4,j5,j6[,speed]` | mode1/2/3 | 队列余量整数 | `ok` |
| `&` | `&j1,j2,j3,j4,j5,j6[,speed]` | mode1/2/3 | 队列余量整数 | `ok` |
| `@` | `@x,y,z,a,b,c[,speed]` | mode1/2/3 | 队列余量整数 | `ok` |

说明：

1. 队列入队失败时，返回值可能为 `255`（内部 `0xFF`）。
2. `COMMAND_TARGET_POINT_SEQUENTIAL/CONTINUES_TRAJECTORY` 会等待运动完成再回 `ok`。
3. `COMMAND_TARGET_POINT_INTERRUPTABLE` 不阻塞等待末端到位。

### 5.5 `$` 电流流命令

| 命令 | 输入格式 | 前置条件 | 成功回包 | 失败回包 |
|---|---|---|---|---|
| `$` | `$i1,i2,i3,i4,i5,i6` | `!START` 且 `#CMDMODE 5` | `ok` | `error BAD_CURRENT_CMD` |

入队失败时（USB/UART4 入口），会返回：`error CMD FIFO FULL`。

### 5.6 CMDMODE 对照表

| 编号 | 协议短名 | OLED短名 | 说明 |
|---|---|---|---|
| 1 | `SEQ_POINT` | `SEQ` | 顺序点位 |
| 2 | `INT_POINT` | `INT` | 可中断点位 |
| 3 | `CONT_TRAJ` | `TRJ` | 连续轨迹 |
| 4 | `MOTOR_TUNE` | `TUNE` | 电机调参 |
| 5 | `COMP_CURRENT` | `CURR` | 柔顺电流 |

### 5.7 RGB 模式号

以 `Bsp/gpio/rgb.hpp` 枚举为准：

| 模式号 | 名称 |
|---|---|
| 0 | `RAINBOW` |
| 1 | `FADE` |
| 2 | `BLINK` |
| 3 | `ALLRed` |
| 4 | `ALLGreen` |
| 5 | `ALLBlue` |
| 6 | `ALLOff` |
| 7 | `CUSTOM_COLOR` |

## 6. 关键语义与安全边界

1. `!START` 只使能，不自动进入柔顺。  
2. `$...` 只在 `CMDMODE=5` 解析生效。  
3. `$0,0,0,0,0,0` 只清电流，不去使能。  
4. 建议急停链路：`!STOP -> $0,0,0,0,0,0 -> !DISABLE`。  
5. 当前限流默认 `±1.5A`，超时 `200ms` 自动清零。  

