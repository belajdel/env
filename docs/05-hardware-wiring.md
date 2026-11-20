# Phase 1 — ESP32 Hardware and Wiring

**Reference design:** one ESP32-WROOM-32 DevKitC per zone, replicated 7 times.
**Logic level:** 3.3 V. The ESP32 is **not 5 V tolerant** on GPIO.
**Safety:** mains AC is never wired on a breadboard. Use an enclosed, fused, isolated module; for the PFE bench use a low-voltage AC source or a certified isolation transformer.

**Sensor assumptions:** PMS5003 (UART) for both PM2.5 and PM10, ZMPT101B for AC RMS voltage, MAX4466 for noise, and MQ135 for indicative air quality. If the lab uses an analog GP2Y1010 dust sensor or a different voltage module, replace only that sensor section and its pin/calibration rows.

## 1. Bill of materials (per zone)

| # | Component | Recommended model | Qty | Interface | Purpose |
|---:|---|---|---:|---|---|
| 1 | ESP32 dev board | ESP32-WROOM-32 DevKitC (30/38-pin) | 1 | Wi-Fi | Acquisition, MQTT, local control |
| 2 | Temperature/humidity | DHT22 / AM2302 | 1 | 1-wire | Temperature + humidity |
| 3 | Air quality | MQ135 module | 1 | Analog | CO₂-equivalent / VOC trend |
| 4 | Dust | PMS5003 | 1 | UART 9600 8N1 | PM2.5 and PM10 |
| 5 | Noise | MAX4466 electret module (3.3 V) | 1 | Analog | Sound level |
| 6 | Voltage | ZMPT101B module | 1 | Analog | AC RMS voltage |
| 7 | Display | LCD 16×2 with I2C backpack (PCF8574) | 1 | I2C | Local readings/status |
| 8 | Relays | 2-channel 5 V relay module, opto input, 10 A | 1 | GPIO | Ventilation / extraction |
| 9 | LEDs | Green, orange, red 5 mm | 3 | GPIO | Local status |
| 10 | Resistors | 220 Ω ×3; 10 kΩ ×4; 20 kΩ ×2 | — | — | LED limiting, pull-ups, dividers |
| 11 | Power | 5 V 3 A certified adapter | 1 | — | 5 V rail |
| 12 | Passives | 470 µF electrolytic, 100 nF ceramic | 2+ | — | Bulk/decoupling |
| 13 | Prototyping | Breadboard, dupont wires, terminal blocks | — | — | Bench prototype |
| 14 | Safety | Fuse, RCD, DIN enclosure, cable glands | 1 set | — | Mains/industrial installation |

## 2. Power rails

| Rail | Source | Loads | Notes |
|---|---|---|---|
| 5 V | Certified 5 V / 3 A adapter | ESP32 `VIN`/`5V`, MQ135, PMS5003, ZMPT101B, relay module, LCD backpack (if 5 V) | Do not power 5 V loads from the ESP32 3.3 V regulator. |
| 3.3 V | ESP32 board regulator | DHT22, MAX4466 (3.3 V version), I2C pull-ups, level-shifter low side | Keep total 3.3 V load < 500 mA. |
| GND | Common star point | All modules | Single common ground; star wiring to reduce sensor noise. |

Do not feed the DevKit through `VIN` and USB at the same time unless the board documents power-path safety. Disconnect USB before connecting the 5 V rail, or use a board with an ideal-diode input.

**Current budget:** ESP32 ≈240 mA peak, PMS5003 ≈100 mA, MQ135 ≈150 mA, relays ≈2 × 70 mA, LCD ≈20 mA, sensors ≈20 mA → ≈700 mA peak. A 3 A supply leaves margin for relay inrush and the PMS fan.

Add 470 µF bulk capacitance near the 5 V input and 100 nF decoupling at each sensor. Keep the PMS5003 5 V and ground returns separate from the analog sensor returns until the star point.

## 3. Pin assignment

### 3.1 Signal table

| Function | Module pin | ESP32 pin | GPIO | Direction | Notes |
|---|---|---|---|---:|---|
| DHT22 data | `DATA` (pin 2) | `D4` | 4 | Bidirectional | 10 kΩ pull-up to **3.3 V**; keep cable < 1 m. |
| MQ135 analog | `AO` via divider | `D34` | 34 | Input | ADC1_CH6; input-only; 10 kΩ/20 kΩ divider from 0–5 V to 0–3.3 V. |
| PMS5003 TX | `TX` | `RX2` (`D16`) | 16 | Input | PMS TX → ESP32 RX; 3.3 V logic. |
| PMS5003 RX | `RX` | `TX2` (`D17`) | 17 | Output | ESP32 TX → PMS RX; 3.3 V logic. |
| PMS5003 SET/RESET | `SET` | `3V3` | — | — | Tie high for normal operation; optional GPIO18 if sleep control is added. |
| Noise analog | `OUT` | `D35` | 35 | Input | ADC1_CH7; input-only; 3.3 V module, biased around 1.65 V. |
| Voltage analog | `OUT` via divider | `D36` | 36 | Input | ADC1_CH0; input-only; 10 kΩ/20 kΩ divider; measure RMS. |
| LCD SDA | `SDA` | `D21` | 21 | Bidirectional | 4.7 kΩ pull-up to **3.3 V**; address `0x27` or `0x3F`. |
| LCD SCL | `SCL` | `D22` | 22 | Output | 4.7 kΩ pull-up to **3.3 V**. |
| Relay 1 input | `IN1` | `D25` | 25 | Output | Active-low module; 10 kΩ pull-up to 3.3 V to keep de-energized at boot. |
| Relay 2 input | `IN2` | `D26` | 26 | Output | Same as relay 1. |
| LED green | Anode via 220 Ω | `D32` | 32 | Output | Active-high; cathode to GND. |
| LED orange | Anode via 220 Ω | `D33` | 33 | Output | Active-high; cathode to GND. |
| LED red | Anode via 220 Ω | `D27` | 27 | Output | Active-high; cathode to GND. |
| Spare | — | `D18`, `D19`, `D23` | 18/19/23 | — | Reserved; do not repurpose silently. |
| UART0 | `TX0`/`RX0` | `D1`/`D3` | 1/3 | — | Reserved for flashing/REPL. |

### 3.2 Reserved / forbidden pins

| Pins | Reason |
|---|---|
| GPIO 6–11 | Connected to SPI flash; using them bricks the board. |
| GPIO 34–39 | Input-only; no internal pull-up/pull-down; use only as ADC/input. |
| GPIO 0, 2, 5, 12, 15 | Boot strapping; external pull-up/down can prevent boot. Avoid for relays/LEDs. |
| GPIO 1, 3 | UART0 debug/flash. |
| ADC2 pins | Not usable while Wi-Fi is active; all analog inputs above use ADC1 (GPIO 32–39). |

### 3.3 I2C and UART

| Bus | Pins | Settings |
|---|---|---|
| I2C0 | SDA 21, SCL 22 | 100 kHz (400 kHz optional), 3.3 V pull-ups, LCD address `0x27`/`0x3F`. |
| UART2 | RX 16, TX 17 | 9600 baud, 8 data bits, no parity, 1 stop bit; PMS5003 frame length 32 bytes. |

Run `i2c.scan()` at boot; if the LCD is absent, continue acquisition and report a `degraded` device status rather than rebooting.

## 4. Sensor characteristics and warm-up

| Sensor | Measures | Range / accuracy | Interface | Warm-up before valid data |
|---|---|---|---|---|
| DHT22 | Temperature, humidity | −40…80 °C ±0.5 °C; 0…100 %RH ±2–5 % | 1-wire | 2 s; discard the first reading. |
| MQ135 | Air quality (NH₃, NOₓ, alcohol, benzene, smoke, CO₂ trend) | ≈10…1000 ppm (not gas-selective) | Analog | **24–48 h burn-in**; 3–5 min after each power-up. |
| PMS5003 | PM1.0, PM2.5, PM10 | 0…1000 µg/m³, ±10 % ±10 µg/m³ | UART | 30 s fan/laser stabilization; discard the first 3 frames. |
| MAX4466 | Sound level | ≈30…130 dB(A), module-dependent | Analog | ≈1 s; requires SPL-meter calibration. |
| ZMPT101B | AC RMS voltage | 0…250 V AC, module-dependent | Analog | ≈1 s; RMS over 20 mains cycles. |
| LCD 16×2 | Local display | — | I2C | ≈200 ms after power-up. |
| Relay module | Actuation | Load-dependent | GPIO | Instant; observe boot state. |

**Warm-up policy**

1. On boot, initialize I2C/UART/ADC, then show `WARMUP` on the LCD and set LEDs to orange.
2. Wait for DHT22 (2 s), PMS5003 (30 s), and noise/voltage (1 s) before publishing `quality: "good"`.
3. MQ135 publishes `quality: "suspect"` until its 3–5 min warm-up completes; it never blocks the other sensors.
4. Wait for NTP sync (max 60 s). If sync fails, buffer locally and show `NO TIME`; do not publish fabricated timestamps.
5. Mark the device `degraded` if any sensor fails; keep publishing the healthy parameters.

## 5. Voltage levels and signal conditioning

| Item | Value / rule |
|---|---|
| ESP32 logic | 3.3 V; **never** apply 5 V to a GPIO. |
| ADC input | 0–3.3 V, 12-bit, `ATTN_11DB`; stay below ≈3.1 V for linearity. |
| MQ135 output | 0–5 V → 10 kΩ series / 20 kΩ to GND (ratio 2/3) → 0–3.33 V. |
| ZMPT101B output | 0–5 V biased AC → same 10 kΩ/20 kΩ divider → 0–3.33 V. |
| I2C pull-ups | To **3.3 V**, not 5 V. Many LCD backpacks ship with 5 V pull-ups; verify or modify. |
| Relay inputs | Module is typically active-low and 5 V; ESP32 drives the opto input, never the coil. Add 10 kΩ pull-ups to 3.3 V so relays stay off while GPIOs float at boot. |
| Relay contacts | Use a contactor/relay rated for the load; add snubber/RC or MOV for inductive loads. |
| Relay input drive | Some 5 V boards pull `IN` to 5 V internally; a 3.3 V high may not fully release the opto. Verify the module, or use a 3.3 V-compatible active-high board / transistor driver. |
| Isolation | Keep mains/relay contact side physically separated from the 3.3 V side; maintain creepage/clearance. |

**ADC notes**

- ESP32 ADC is non-linear near the rails; calibrate each channel with a multimeter and store offsets/scales in `devices.sensors[].calibration`.
- Average 16 samples after discarding min/max; never alert on a single ADC sample.
- The relay GPIOs (25/26) are ADC2-capable but used digitally; do not use ADC2 for analog inputs while Wi-Fi is active.

## 6. Mains safety and relay wiring

- **Do not breadboard mains.** Use a DIN-rail enclosure, fuse, RCD, cable glands, and certified terminal blocks. The ZMPT101B provides isolation, but the installation still requires proper clearances.
- For the PFE demonstration, use a 12 V AC transformer or a signal generator to validate the voltage channel; do not energize a 230 V load on an open bench.
- Relay `COM`/`NO`/`NC` selection is a safety decision:
  - Ventilation/extraction: the fail-safe state may be **ON** (de-energized = ventilation running) depending on the hazard analysis.
  - Default seed value is `off`; the safety review must explicitly change it if the process requires otherwise.
- Add a flyback/snubber across inductive loads; the relay module's optocoupler does not protect the contacts from arc damage.
- Label every cable; keep a wiring diagram inside the enclosure.

## 7. Local indicators and display

| Indicator | Meaning |
|---|---|
| Green LED | All sensors healthy; latest values within info thresholds. |
| Orange LED | Warning threshold active, sensor warm-up, degraded link, or offline buffer non-empty. |
| Red LED | Critical threshold active, relay fault, or sensor failure requiring attention. |
| LCD line 1 | `T:31.4C H:54%` |
| LCD line 2 | Rotates every 2 s: `AQ:812 PM2.5:22`, `PM10:41 V:231`, `NET:online BUF:0`. |

LED states must also be represented by text/icon in the dashboard (not color-only) for accessibility.

## 8. Filtering and sampling (firmware behavior)

| Parameter | Local processing | Publish cadence |
|---|---|---|
| Temperature / humidity | Median of 5 samples + EMA α=0.3; reject DHT checksum errors | 10 s |
| Air quality | Median of 9; baseline subtraction; 1-min mean | 10 s (raw), 1 min aggregate in backend |
| PM2.5 / PM10 | Discard first 3 frames after boot; 1-min mean; reject >3× rolling median | 1 s read, 10 s publish |
| Noise | 1 s A-weighted Leq; 1-min Leq for alerts | 10 s |
| Voltage | RMS over 20 cycles; 10 s mean; flag sag/swell | 10 s |

The device publishes filtered values; the backend stores them and computes 1-minute aggregates for charts. Raw high-rate frames are not sent to MQTT.

## 9. Bench test checklist (Phase 1 exit)

1. Verify 5 V and 3.3 V rails with a multimeter before connecting sensors.
2. Run `i2c.scan()` and confirm the LCD address; display `Hello` for 2 s.
3. Read DHT22 and confirm plausible temperature/humidity after 2 s.
4. Read MQ135 raw ADC and confirm a stable baseline after 3–5 min (burn-in continues).
5. Read PMS5003 frames at 9600 baud and decode PM2.5/PM10.
6. Inject a known tone and confirm the noise channel responds; calibrate against a phone SPL meter as a rough check.
7. Apply a safe low AC voltage and confirm RMS scaling; never connect mains to the breadboard.
8. Toggle both relays from code and verify `off` at boot with GPIO floating/pulled up.
9. Confirm green/orange/red LED patterns and LCD rotation.
10. Disconnect Wi-Fi and confirm the buffer grows; reconnect and confirm replay.
