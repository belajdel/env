# ESP32 Pin Configuration

## Hardware: ESP32-WROOM-32 (38-pin)

```
          ESP32-WROOM-32 Pinout
    ┌─────────────────────────────────────┐
    │  ● EN          3V3           GND  │
    │       VP         EN            25  │
    │       VN         36            26  │
    │       34         39            27  │
    │       35         34            14  │
    │       32         35            12  │
    │       33         32            13  │
    │       25         33            GND │
    │       26         25            15  │
    │       27         26            2   │
    │       14         27            0   │
    │       12         14            4   │
    │       13         12            16  │
    │       GND        13            17  │
    │       15          GND           5   │
    │       2           15           18  │
    │       0           2            19  │
    │       4            0           21  │
    │       16           4           22  │
    │       17           16          23  │
    │       5            17          24  │
    │       18           5           25  │
    │       19           18          26  │
    │       21           19          27  │
    │       22           21          28  │
    │       23           22          29  │
    │       24           23          30  │
    │       25           24          31  │
    └─────────────────────────────────────┘
```

---

## Pin Assignments

### Sensors

| Sensor | Parameter | GPIO | Interface | Notes |
|--------|-----------|------|-----------|-------|
| DHT22 | Temperature/Humidity | GPIO 4 | 1-Wire | 4.7kΩ pull-up to 3.3V |
| MQ135 | Air Quality | GPIO 34 | ADC1_CH6 | Input only, no pull-up |
| PMS5003 | PM2.5/PM10 | GPIO 16 (RX2), GPIO 17 (TX2) | UART2 | 9600 baud, 3.3V logic |
| ZMPT101B | Voltage | GPIO 35 | ADC1_CH7 | Input only, AC coupling |
| MAX4466 | Noise | GPIO 32 | ADC1_CH4 | DC biased at 1.65V |

### Actuators

| Device | Function | GPIO | Interface | Notes |
|--------|----------|------|-----------|-------|
| Relay 1 | Ventilation/AC | GPIO 21 | Digital Out | Active LOW (optocoupler) |
| Relay 2 | Heater/Dehumidifier | GPIO 22 | Digital Out | Active LOW (optocoupler) |

### Display

| Device | Function | GPIO | Interface | Notes |
|--------|----------|------|-----------|-------|
| LCD 1602 (I2C) | Status Display | GPIO 21 (SDA), GPIO 22 (SCL) | I2C | Shared with relays via I2C expander* |
| LED Red | Error Status | GPIO 2 | Digital Out | Onboard blue LED |
| LED Green | MQTT Connected | GPIO 23 | Digital Out | External |
| LED Yellow | Sampling Active | GPIO 19 | Digital Out | External |

*Note: LCD uses I2C on GPIO 21/22. Relays use separate GPIOs or I2C expander (PCF8574) at address 0x27.

### Communication

| Function | GPIO | Interface | Notes |
|----------|------|-----------|-------|
| WiFi/BT | Internal | - | Antenna on PCB |
| MQTT TLS | - | WiFi | Port 8883 |
| OTA Updates | - | WiFi | HTTPS |
| Debug Log | GPIO 1 (TX0), GPIO 3 (RX0) | UART0 | 115200 baud |

### Power

| Pin | Function | Notes |
|-----|----------|-------|
| 3V3 | Sensor power | Max 600mA total |
| VIN | External 5V | USB or barrel jack |
| GND | Common ground | All grounds connected |

---

## Detailed Pin Table

| GPIO | Pin Name | Function | Direction | Voltage | Pull | Notes |
|------|----------|----------|-----------|---------|------|-------|
| 0 | BOOT | Boot mode | Input | 3.3V | Up | Low = bootloader |
| 1 | TX0 | Debug TX | Output | 3.3V | - | UART0 |
| 2 | GPIO2 | Onboard LED | Output | 3.3V | - | Active LOW |
| 3 | RX0 | Debug RX | Input | 3.3V | - | UART0 |
| 4 | GPIO4 | DHT22 Data | I/O | 3.3V | Up | 4.7kΩ external |
| 5 | GPIO5 | VSPI SS | - | - | - | Reserved |
| 12 | GPIO12 | VSPI MISO | - | - | - | Reserved (MTDI) |
| 13 | GPIO13 | VSPI MOSI | - | - | - | Reserved (MTCK) |
| 14 | GPIO14 | VSPI CLK | - | - | - | Reserved (MTMS) |
| 15 | GPIO15 | VSPI CS0 | - | - | - | Reserved (MTDO) |
| 16 | RX2 | PMS5003 RX | Input | 3.3V | - | UART2 |
| 17 | TX2 | PMS5003 TX | Output | 3.3V | - | UART2 |
| 18 | GPIO18 | VSPI CLK | - | - | - | Reserved |
| 19 | GPIO19 | LED Yellow | Output | 3.3V | - | Sampling indicator |
| 21 | GPIO21 | I2C SDA / Relay 1 | I/O | 3.3V | Up | Shared I2C |
| 22 | GPIO22 | I2C SCL / Relay 2 | I/O | 3.3V | Up | Shared I2C |
| 23 | GPIO23 | LED Green | Output | 3.3V | - | MQTT connected |
| 25 | GPIO25 | DAC1 | - | - | - | Reserved |
| 26 | GPIO26 | DAC2 | - | - | - | Reserved |
| 27 | GPIO27 | - | - | - | - | Reserved |
| 32 | GPIO32 | MAX4466 Noise | Input | 3.3V | - | ADC1_CH4 |
| 33 | GPIO33 | - | - | - | - | Reserved |
| 34 | GPIO34 | MQ135 AQI | Input | 3.3V | - | ADC1_CH6 (input only) |
| 35 | GPIO35 | ZMPT101B Voltage | Input | 3.3V | - | ADC1_CH7 (input only) |
| 36 | VP | - | Input | 3.3V | - | ADC1_CH0 (input only) |
| 39 | VN | - | Input | 3.3V | - | ADC1_CH3 (input only) |

---

## ADC Configuration

### ADC1 (WiFi compatible)
| Channel | GPIO | Sensor | Attenuation | Resolution |
|---------|------|--------|-------------|------------|
| CH4 | 32 | MAX4466 Noise | 11dB (0-3.3V) | 12-bit |
| CH6 | 34 | MQ135 Air Quality | 11dB (0-3.3V) | 12-bit |
| CH7 | 35 | ZMPT101B Voltage | 11dB (0-3.3V) | 12-bit |

**Note**: ADC2 cannot be used when WiFi is active. All sensors use ADC1.

### Calibration Formulas

```python
# Noise (MAX4466) - DC biased at 1.65V
# Vpp = (max - min) * 3.3 / 4095
# dB = 20 * log10(Vpp / 0.0063) + 94  # Calibrated for 94dB @ 1Pa

# Air Quality (MQ135) - R0 calibration needed
# PPM = 116.6020682 * (Rs/R0)^-2.769034857
# Rs = (3.3 - Vout) / Vout * Rload

# Voltage (ZMPT101B) - AC RMS measurement
# Samples 2000 points over 200ms (10 cycles @ 50Hz)
# Vrms = sqrt(sum(v^2)/n) * calibration_factor
# Calibration: 230V AC = ~1.65V DC offset ±1.0V
```

---

## I2C Devices

| Device | Address | GPIO | Notes |
|--------|---------|------|-------|
| LCD 1602 (PCF8574) | 0x27 | 21/22 | 4-bit mode |
| Relay Expander (PCF8574) | 0x20 | 21/22 | Alternative to direct GPIO |

### I2C Scanner Code
```python
from machine import I2C, Pin
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
devices = i2c.scan()
print([hex(d) for d in devices])  # Should show [0x27, 0x20]
```

---

## Relay Circuit

```
                    ┌─────────────┐
        GPIO 21 ───►│             │
        (Active LOW)│  Optocoupler│───► Relay Coil ──► Load (230V AC)
                    │   (PC817)   │
                    └─────────────┘
                           │
                          GND

        GPIO 22 ───► Same circuit for Relay 2
```

- **Active LOW**: GPIO HIGH = Relay OFF, GPIO LOW = Relay ON
- **Fail-safe**: On reset/boot, GPIOs float HIGH → Relays OFF
- **Optocoupler**: 3.3V logic side, isolates from relay coil
- **Flyback diode**: Across relay coil (built into module)

---

## LED Indicators

| LED | GPIO | Color | Behavior |
|-----|------|-------|----------|
| Onboard | 2 | Blue | Boot: blink 3x, Error: fast blink, Normal: off |
| External 1 | 23 | Green | MQTT: solid=connected, blink=reconnecting |
| External 2 | 19 | Yellow | Sampling: pulse on each sample (100ms) |

---

## Power Budget

| Component | Current (mA) | Duty Cycle | Avg (mA) |
|-----------|-------------|------------|----------|
| ESP32 (WiFi active) | 240 | 100% | 240 |
| DHT22 | 2.5 | 10% (1s/10s) | 0.25 |
| MQ135 (heater) | 150 | 100% | 150 |
| PMS5003 | 100 | 100% | 100 |
| MAX4466 | 0.6 | 100% | 0.6 |
| ZMPT101B | 5 | 100% | 5 |
| LCD (backlight) | 20 | 100% | 20 |
| 2x Relays (coil) | 70 each | 10% | 14 |
| 2x Optocouplers | 10 each | 10% | 2 |
| LEDs | 10 each | 50% | 15 |
| **Total** | | | **~547 mA** |

**Power Supply**: 5V 2A (USB-C or barrel jack) → 3.3V regulator (AMS1117 or similar)

---

## Firmware Build Configuration

### `platformio.ini`
```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = micropython
board_build.flash_mode = dio
board_build.flash_size = 4MB
board_build.partitions = default_4MB.csv
monitor_speed = 115200
upload_speed = 921600
```

### MicroPython Modules (Frozen)
```c
// micropython/ports/esp32/boards/manifest.py
freeze("firmware/sensors/dht22.py")
freeze("firmware/sensors/mq135.py")
freeze("firmware/sensors/pms5003.py")
freeze("firmware/sensors/zmpt101b.py")
freeze("firmware/sensors/max4466.py")
freeze("firmware/display/lcd_i2c.py")
freeze("firmware/actuators/relay.py")
freeze("firmware/mqtt/client.py")
freeze("firmware/main.py")
```

### Memory Optimization
- Use `gc.collect()` after sensor reads
- Pre-allocate bytearrays for UART/ADC buffers
- Freeze modules to reduce RAM usage
- Target: < 80KB free heap during operation

---

## OTA Update

### Partition Table (4MB)
```
# Name,   Type, SubType, Offset,  Size, Flags
nvs,      data, nvs,     0x9000,  0x4000,
otadata,  data, ota,     0xd000,  0x2000,
phy_init, data, phy,     0xf000,  0x1000,
factory,  app,  factory, 0x10000, 0x180000,
ota_0,    app,  ota_0,   0x190000,0x180000,
ota_1,    app,  ota_1,   0x310000,0x180000,
spiffs,   data, spiffs,  0x490000,0x70000,
```

### OTA Process
1. Backend sends `ota_available` via MQTT command topic
2. Firmware downloads `.bin` from HTTPS URL
3. Writes to inactive OTA partition
4. Sets boot partition, reboots
5. On boot: health check → mark valid or rollback

---

## Debugging

### Serial Console
```bash
# Connect
picocom -b 115200 /dev/ttyUSB0

# Or with esptool
esptool.py -p /dev/ttyUSB0 -b 115200 read_flash 0x10000 0x180000 firmware_backup.bin
```

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Guru Meditation | Stack overflow | Increase stack size, reduce recursion |
| WiFi disconnect | Power save | Disable WiFi modem sleep |
| ADC noisy | WiFi interference | Use ADC1 only, average samples |
| I2C timeout | Pull-up missing | Add 4.7kΩ on SDA/SCL |
| Relay chatter | Floating GPIO | Add pull-up, check optocoupler |
| OTA fails | Partition size | Check `.bin` < 1.5MB |

---

## Bill of Materials (Per Zone)

| Qty | Part | Description | Est. Cost |
|-----|------|-------------|-----------|
| 1 | ESP32-WROOM-32 | Dev board or bare module | $8 |
| 1 | DHT22 | Temp/Humidity sensor | $3 |
| 1 | MQ135 | Air quality sensor | $2 |
| 1 | PMS5003 | PM2.5/PM10 sensor | $15 |
| 1 | ZMPT101B | Voltage sensor | $3 |
| 1 | MAX4466 | Electret microphone amp | $2 |
| 2 | 5V Relay Module | Optocoupled, 10A | $2 |
| 1 | LCD 1602 + I2C | 16x2 character display | $3 |
| 3 | LED + 220Ω | Status indicators | $0.50 |
| 1 | Perfboard/PCB | Custom or protoboard | $2 |
| 1 | 5V 2A PSU | USB-C or barrel jack | $4 |
| 1 | Enclosure | IP65 rated | $10 |
| **Total** | | | **~$54** |

---

## Firmware Flashing

```bash
# Erase flash
esptool.py -p /dev/ttyUSB0 erase_flash

# Flash MicroPython firmware
esptool.py -p /dev/ttyUSB0 -b 460800 \
  write_flash -z 0x1000 esp32-20240101-v1.22.0.bin

# Flash frozen modules (via rshell/ampy)
rshell -p /dev/ttyUSB0
cp -r firmware/ /pyboard/
```

---

## Pin Conflict Resolution

| Conflict | Resolution |
|----------|------------|
| GPIO 21/22: I2C vs Relays | Use PCF8574 expander at 0x20 for relays, keep LCD at 0x27 |
| ADC2 unavailable with WiFi | All sensors on ADC1 (GPIO 32, 34, 35) |
| UART0 for debug vs boot | Use UART2 (GPIO 16/17) for PMS5003 |
| Strapping pins (0, 2, 12, 15) | Avoid as inputs during boot, use as outputs only |

---

## Safety Notes

1. **230V AC Isolation**: Relays must be rated for 250VAC/10A, optocoupled
2. **Creepage Distance**: >3mm between HV and LV on PCB
3. **Fuse**: 2A slow-blow on 5V input
4. **Enclosure**: IP65, cable glands for sensor cables
5. **Grounding**: Metal enclosure grounded, sensor shields connected
6. **Certification**: CE/FCC for commercial deployment