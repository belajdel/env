"""
PMS5003 PM2.5/PM10 Sensor Driver (UART)
MicroPython compatible
"""

import machine
import time
import struct
from typing import Optional, Tuple
from ..config import (
    PMS5003_UART, PMS5003_TX_PIN, PMS5003_RX_PIN, PMS5003_BAUDRATE,
    VALIDATION_RANGES
)


class PMS5003Sensor:
    """PMS5003 particulate matter sensor driver via UART."""
    
    # Frame format: 0x42 0x4D + 30 bytes data + 2 bytes checksum
    FRAME_START = b'\x42\x4d'
    FRAME_LENGTH = 32
    
    def __init__(self, uart_id: int = PMS5003_UART, tx_pin: int = PMS5003_TX_PIN,
                 rx_pin: int = PMS5003_RX_PIN, baudrate: int = PMS5003_BAUDRATE):
        self.uart = machine.UART(uart_id, baudrate=baudrate, tx=tx_pin, rx=rx_pin,
                                  bits=8, parity=None, stop=1, timeout=1000, rxbuf=256)
        self._last_pm25 = None
        self._last_pm10 = None
        self._last_pm100 = None
        self._consecutive_errors = 0
        self._buffer = bytearray()
        
    def read(self) -> Optional[Tuple[float, float, float]]:
        """
        Read PM1.0, PM2.5, PM10 in μg/m³ (CF=1, standard particles).
        Returns (pm10, pm25, pm100) or None on failure.
        """
        # Read available data
        data = self.uart.read()
        if data:
            self._buffer.extend(data)
            
        # Find frame start
        while len(self._buffer) >= self.FRAME_LENGTH:
            start_idx = self._buffer.find(self.FRAME_START)
            if start_idx < 0:
                # No start sequence, discard all but last byte (might be start of next frame)
                if len(self._buffer) > 1:
                    self._buffer = self._buffer[-1:]
                break
                
            if start_idx > 0:
                # Discard garbage before frame start
                self._buffer = self._buffer[start_idx:]
                
            if len(self._buffer) < self.FRAME_LENGTH:
                # Incomplete frame, wait for more data
                break
                
            # Extract frame
            frame = self._buffer[:self.FRAME_LENGTH]
            self._buffer = self._buffer[self.FRAME_LENGTH:]
            
            # Verify checksum
            if self._verify_checksum(frame):
                result = self._parse_frame(frame)
                if result:
                    self._consecutive_errors = 0
                    return result
            else:
                self._consecutive_errors += 1
                print(f"PMS5003 checksum error ({self._consecutive_errors})")
                
        return None
    
    def _verify_checksum(self, frame: bytearray) -> bool:
        """Verify frame checksum (sum of bytes 0-29 == bytes 30-31)."""
        calc_sum = sum(frame[:30])
        recv_sum = struct.unpack('>H', frame[30:32])[0]
        return calc_sum == recv_sum
    
    def _parse_frame(self, frame: bytearray) -> Optional[Tuple[float, float, float]]:
        """Parse valid frame into PM values."""
        try:
            # Unpack: 13 x uint16 (big endian) after start bytes
            # Indices: 0=frame_len, 1=pm1.0_cf1, 2=pm2.5_cf1, 3=pm10_cf1,
            #          4=pm1.0_atm, 5=pm2.5_atm, 6=pm10_atm,
            #          7=count_0.3, 8=count_0.5, 9=count_1.0, 10=count_2.5, 11=count_5.0, 12=count_10
            data = struct.unpack('>13H', frame[2:28])
            
            # Use atmospheric environment values (indices 4, 5, 6)
            pm10 = float(data[4])
            pm25 = float(data[5])
            pm100 = float(data[6])
            
            # Validate ranges
            if not (VALIDATION_RANGES['pm25'][0] <= pm25 <= VALIDATION_RANGES['pm25'][1]):
                return None
            if not (VALIDATION_RANGES['pm10'][0] <= pm100 <= VALIDATION_RANGES['pm10'][1]):
                return None
                
            self._last_pm10 = pm10
            self._last_pm25 = pm25
            self._last_pm100 = pm100
            
            return (pm10, pm25, pm100)
            
        except Exception as e:
            print(f"PMS5003 parse error: {e}")
            return None
    
    def read_pm25(self) -> Optional[float]:
        """Read PM2.5 only."""
        result = self.read()
        return result[1] if result else self._last_pm25
    
    def read_pm10(self) -> Optional[float]:
        """Read PM10 only."""
        result = self.read()
        return result[2] if result else self._last_pm10
    
    def sleep(self) -> None:
        """Put sensor into sleep mode (not implemented - requires pin control)."""
        # PMS5003 has SET and RESET pins for sleep/wake
        # Would need additional GPIO control
        pass
    
    def wake(self) -> None:
        """Wake sensor from sleep mode."""
        pass
    
    def get_status(self) -> dict:
        """Get sensor status."""
        return {
            'last_pm10': self._last_pm10,
            'last_pm25': self._last_pm25,
            'last_pm100': self._last_pm100,
            'errors': self._consecutive_errors,
        }