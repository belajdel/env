"""
LCD 16x2 I2C Display Driver
MicroPython compatible
"""

import machine
import time
from typing import Optional
from ..config import (
    LCD_I2C_ADDR, LCD_SDA_PIN, LCD_SCL_PIN, LCD_COLS, LCD_ROWS
)


# PCF8574 I2C expander commands
LCD_CLEARDISPLAY = 0x01
LCD_RETURNHOME = 0x02
LCD_ENTRYMODESET = 0x04
LCD_DISPLAYCONTROL = 0x08
LCD_CURSORSHIFT = 0x10
LCD_FUNCTIONSET = 0x20
LCD_SETCGRAMADDR = 0x40
LCD_SETDDRAMADDR = 0x80

# Entry mode flags
LCD_ENTRYRIGHT = 0x00
LCD_ENTRYLEFT = 0x02
LCD_ENTRYSHIFTINCREMENT = 0x01
LCD_ENTRYSHIFTDECREMENT = 0x00

# Display control flags
LCD_DISPLAYON = 0x04
LCD_DISPLAYOFF = 0x00
LCD_CURSORON = 0x02
LCD_CURSOROFF = 0x00
LCD_BLINKON = 0x01
LCD_BLINKOFF = 0x00

# Function set flags
LCD_8BITMODE = 0x10
LCD_4BITMODE = 0x00
LCD_2LINE = 0x08
LCD_1LINE = 0x00
LCD_5x10DOTS = 0x04
LCD_5x8DOTS = 0x00

# Backlight control
LCD_BACKLIGHT = 0x08
LCD_NOBACKLIGHT = 0x00

# PCF8574 pin mapping (typical)
# P0=RS, P1=RW, P2=EN, P3=Backlight, P4-P7=D4-D7
EN_BIT = 0x04  # Enable bit
RW_BIT = 0x02  # Read/Write bit
RS_BIT = 0x01  # Register Select bit


class LCD16x2:
    """LCD 16x2 I2C display driver using PCF8574 expander."""
    
    def __init__(self, i2c_addr: int = LCD_I2C_ADDR, sda_pin: int = LCD_SDA_PIN,
                 scl_pin: int = LCD_SCL_PIN, cols: int = LCD_COLS, rows: int = LCD_ROWS):
        self.i2c_addr = i2c_addr
        self.cols = cols
        self.rows = rows
        self._backlight = True
        self._display_on = True
        
        # Initialize I2C
        self.i2c = machine.I2C(0, sda=machine.Pin(sda_pin), scl=machine.Pin(scl_pin), freq=100000)
        
        # Verify device exists
        devices = self.i2c.scan()
        if i2c_addr not in devices:
            raise OSError(f"LCD not found at address 0x{i2c_addr:02X}. Found: {[hex(d) for d in devices]}")
            
        self._init_display()
        print(f"LCD initialized at 0x{i2c_addr:02X}")
        
    def _init_display(self) -> None:
        """Initialize LCD in 4-bit mode."""
        time.sleep_ms(50)  # Wait for power-up
        
        # Send 0x03 three times (8-bit mode init sequence)
        self._write_nibble(0x03)
        time.sleep_ms(5)
        self._write_nibble(0x03)
        time.sleep_ms(1)
        self._write_nibble(0x03)
        time.sleep_ms(1)
        
        # Switch to 4-bit mode
        self._write_nibble(0x02)
        time.sleep_ms(1)
        
        # Function set: 4-bit, 2 lines, 5x8 dots
        self._command(LCD_FUNCTIONSET | LCD_4BITMODE | LCD_2LINE | LCD_5x8DOTS)
        
        # Display on, cursor off, blink off
        self._display_control = LCD_DISPLAYCONTROL | LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF
        self._command(self._display_control)
        
        # Clear display
        self.clear()
        
        # Entry mode: left to right, no shift
        self._command(LCD_ENTRYMODESET | LCD_ENTRYLEFT | LCD_ENTRYSHIFTDECREMENT)
        
    def _write_nibble(self, nibble: int) -> None:
        """Write 4-bit nibble to LCD."""
        # nibble is upper 4 bits of data
        data = (nibble << 4) & 0xF0
        self._send_i2c(data | EN_BIT | (LCD_BACKLIGHT if self._backlight else LCD_NOBACKLIGHT))
        self._send_i2c(data | (LCD_BACKLIGHT if self._backlight else LCD_NOBACKLIGHT))
        
    def _send_i2c(self, data: int) -> None:
        """Send byte to I2C expander."""
        self.i2c.writeto(self.i2c_addr, bytes([data]))
        
    def _command(self, cmd: int) -> None:
        """Send command to LCD."""
        # Upper nibble
        self._write_nibble(cmd >> 4)
        # Lower nibble
        self._write_nibble(cmd & 0x0F)
        time.sleep_us(50)
        
    def _data(self, data: int) -> None:
        """Send data to LCD."""
        # Upper nibble with RS=1
        self._write_nibble((data >> 4) | RS_BIT)
        # Lower nibble with RS=1
        self._write_nibble((data & 0x0F) | RS_BIT)
        time.sleep_us(50)
        
    def clear(self) -> None:
        """Clear display and return home."""
        self._command(LCD_CLEARDISPLAY)
        time.sleep_ms(2)
        
    def home(self) -> None:
        """Return cursor to home position."""
        self._command(LCD_RETURNHOME)
        time.sleep_ms(2)
        
    def set_cursor(self, col: int, row: int) -> None:
        """Set cursor position (0-indexed)."""
        row_offsets = [0x00, 0x40, 0x14, 0x54]  # For 2-line display
        if row >= self.rows:
            row = self.rows - 1
        if row < 0:
            row = 0
        self._command(LCD_SETDDRAMADDR | (col + row_offsets[row]))
        
    def write(self, text: str) -> None:
        """Write string at current cursor position."""
        for char in text:
            self._data(ord(char))
            
    def print_line(self, line: int, text: str, align: str = 'left') -> None:
        """Print text on specific line with alignment."""
        self.set_cursor(0, line)
        if align == 'center':
            text = text.center(self.cols)
        elif align == 'right':
            text = text.rjust(self.cols)
        else:
            text = text.ljust(self.cols)
        self.write(text[:self.cols])
        
    def print_two_lines(self, line1: str, line2: str) -> None:
        """Print two lines (common use case)."""
        self.print_line(0, line1)
        self.print_line(1, line2)
        
    def backlight_on(self) -> None:
        """Turn on backlight."""
        self._backlight = True
        self._command(self._display_control)  # Refresh with backlight
        
    def backlight_off(self) -> None:
        """Turn off backlight."""
        self._backlight = False
        self._command(self._display_control)
        
    def display_on(self) -> None:
        """Turn on display."""
        self._display_on = True
        self._display_control |= LCD_DISPLAYON
        self._command(self._display_control)
        
    def display_off(self) -> None:
        """Turn off display."""
        self._display_on = False
        self._display_control &= ~LCD_DISPLAYON
        self._command(self._display_control)
        
    def create_char(self, location: int, pattern: list) -> None:
        """Create custom character (0-7)."""
        if location < 0 or location > 7:
            return
        self._command(LCD_SETCGRAMADDR | (location << 3))
        for byte in pattern:
            self._data(byte)
        self._command(LCD_SETDDRAMADDR)  # Return to DDRAM


class DisplayManager:
    """High-level display manager for monitoring device."""
    
    def __init__(self, lcd: LCD16x2 = None):
        self.lcd = lcd or LCD16x2()
        self._last_update = 0
        self._update_interval = 2000  # ms
        
        # Custom characters
        self._define_custom_chars()
        
    def _define_custom_chars(self) -> None:
        """Define custom characters for status icons."""
        # WiFi signal
        self.lcd.create_char(0, [
            0b00000,
            0b00000,
            0b00100,
            0b01010,
            0b10001,
            0b00000,
            0b00000,
            0b00000,
        ])
        # MQTT connected
        self.lcd.create_char(1, [
            0b00000,
            0b01010,
            0b11111,
            0b11111,
            0b01110,
            0b00100,
            0b00000,
            0b00000,
        ])
        # Alert
        self.lcd.create_char(2, [
            0b00100,
            0b01010,
            0b01010,
            0b01010,
            0b01110,
            0b01110,
            0b00100,
            0b00000,
        ])
        # Temperature
        self.lcd.create_char(3, [
            0b00100,
            0b01010,
            0b01010,
            0b01110,
            0b01110,
            0b11111,
            0b11111,
            0b01110,
        ])
        # Humidity
        self.lcd.create_char(4, [
            0b00100,
            0b00100,
            0b01010,
            0b01010,
            0b10001,
            0b10001,
            0b10001,
            0b01110,
        ])
        
    def show_startup(self, device_id: str, version: str) -> None:
        """Show startup screen."""
        self.lcd.clear()
        self.lcd.print_line(0, f"Env Monitor v{version}", 'center')
        self.lcd.print_line(1, device_id, 'center')
        time.sleep(2)
        
    def show_connecting(self, stage: str) -> None:
        """Show connection status."""
        self.lcd.clear()
        self.lcd.print_line(0, "Connecting...", 'center')
        self.lcd.print_line(1, stage, 'center')
        
    def show_status(self, wifi_connected: bool, mqtt_connected: bool, 
                    alert_active: bool, readings: dict = None) -> None:
        """Show main status screen."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_update) < self._update_interval:
            return
        self._last_update = now
            
        # Line 1: Status icons + zone/device
        line1 = ""
        if wifi_connected:
            line1 += "\x00"  # WiFi icon
        else:
            line1 += " "
        line1 += " "
        if mqtt_connected:
            line1 += "\x01"  # MQTT icon
        else:
            line1 += " "
        line1 += " "
        if alert_active:
            line1 += "\x02"  # Alert icon
        else:
            line1 += " "
        line1 += " "
        # Add device ID (truncated)
        from ..config import DEVICE_ID
        line1 += DEVICE_ID[:10]
        
        # Line 2: Key readings
        line2 = ""
        if readings:
            temp = readings.get('temperature')
            hum = readings.get('humidity')
            if temp is not None:
                line2 += f"\x03{temp:.1f}C "
            if hum is not None:
                line2 += f"\x04{hum:.0f}% "
        if not line2:
            line2 = "Waiting for data"
            
        self.lcd.print_line(0, line1)
        self.lcd.print_line(1, line2)
        
    def show_readings(self, readings: dict) -> None:
        """Show detailed readings (cycles through parameters)."""
        # Show temperature & humidity
        temp = readings.get('temperature')
        hum = readings.get('humidity')
        line1 = f"T:{temp:.1f}C" if temp is not None else "T:---"
        line1 += f" H:{hum:.0f}%" if hum is not None else " H:---"
        
        # Show air quality & noise
        aq = readings.get('air_quality')
        noise = readings.get('noise')
        line2 = f"AQ:{aq:.0f}" if aq is not None else "AQ:---"
        line2 += f" N:{noise:.0f}dB" if noise is not None else " N:---"
        
        self.lcd.print_line(0, line1)
        self.lcd.print_line(1, line2)
        
    def show_alert(self, message: str, level: str = "WARNING") -> None:
        """Show alert message."""
        self.lcd.clear()
        self.lcd.print_line(0, f"ALERT: {level}", 'center')
        self.lcd.print_line(1, message[:16], 'center')
        # Blink backlight
        for _ in range(3):
            self.lcd.backlight_off()
            time.sleep_ms(200)
            self.lcd.backlight_on()
            time.sleep_ms(200)
            
    def show_relay_status(self, relay1: bool, relay2: bool) -> None:
        """Show relay status."""
        self.lcd.clear()
        self.lcd.print_line(0, "Relay Control", 'center')
        r1 = "ON" if relay1 else "OFF"
        r2 = "ON" if relay2 else "OFF"
        self.lcd.print_line(1, f"R1:{r1}  R2:{r2}", 'center')
        time.sleep(3)