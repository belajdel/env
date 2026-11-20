"""
Local Filtering for Sensor Readings
Moving average and outlier rejection
MicroPython compatible
"""

from typing import Optional, List, Any
from collections import deque
import math
from ..config import MOVING_AVERAGE_WINDOW, OUTLIER_THRESHOLD_STD


class MovingAverageFilter:
    """Simple moving average filter with fixed window size."""
    
    def __init__(self, window_size: int = MOVING_AVERAGE_WINDOW):
        self.window_size = window_size
        self.values = deque(maxlen=window_size)
        
    def add(self, value: float) -> float:
        """Add value and return current average."""
        self.values.append(value)
        return self.get_average()
    
    def get_average(self) -> Optional[float]:
        """Get current moving average."""
        if not self.values:
            return None
        return sum(self.values) / len(self.values)
    
    def get_std_dev(self) -> Optional[float]:
        """Get standard deviation of current window."""
        if len(self.values) < 2:
            return None
        mean = self.get_average()
        variance = sum((x - mean) ** 2 for x in self.values) / len(self.values)
        return math.sqrt(variance)
    
    def clear(self) -> None:
        """Clear the filter buffer."""
        self.values.clear()
    
    def is_ready(self) -> bool:
        """Check if filter has enough samples for reliable average."""
        return len(self.values) >= self.window_size // 2


class OutlierRejectionFilter:
    """Outlier rejection using standard deviation threshold."""
    
    def __init__(self, threshold_std: float = OUTLIER_THRESHOLD_STD, 
                 base_filter: MovingAverageFilter = None):
        self.threshold_std = threshold_std
        self.base_filter = base_filter or MovingAverageFilter()
        self._last_accepted = None
        
    def add(self, value: float) -> Optional[float]:
        """
        Add value, reject if outlier.
        Returns filtered value if accepted, None if rejected.
        """
        # If no history, accept first values
        if self._last_accepted is None:
            self._last_accepted = value
            self.base_filter.add(value)
            return value
            
        # Get current statistics
        mean = self.base_filter.get_average()
        std = self.base_filter.get_std_dev()
        
        if mean is None or std is None or std == 0:
            # Not enough data or no variation, accept
            self._last_accepted = value
            self.base_filter.add(value)
            return value
            
        # Check if outlier
        if abs(value - mean) > self.threshold_std * std:
            # Outlier detected, reject and return last accepted
            print(f"Outlier rejected: {value:.2f} (mean={mean:.2f}, std={std:.2f})")
            return self._last_accepted
            
        # Accept value
        self._last_accepted = value
        self.base_filter.add(value)
        return value
    
    def get_filtered(self) -> Optional[float]:
        """Get current filtered value."""
        return self._last_accepted
    
    def reset(self) -> None:
        """Reset filter state."""
        self.base_filter.clear()
        self._last_accepted = None


class SensorFilter:
    """Combined filter for a single sensor parameter."""
    
    def __init__(self, parameter: str, window_size: int = MOVING_AVERAGE_WINDOW,
                 outlier_std: float = OUTLIER_THRESHOLD_STD):
        self.parameter = parameter
        self.ma_filter = MovingAverageFilter(window_size)
        self.outlier_filter = OutlierRejectionFilter(outlier_std, self.ma_filter)
        
    def process(self, raw_value: float) -> Optional[float]:
        """Process raw reading through both filters."""
        # First apply outlier rejection (which uses moving average internally)
        return self.outlier_filter.add(raw_value)
    
    def get_current(self) -> Optional[float]:
        """Get current filtered value."""
        return self.outlier_filter.get_filtered()
    
    def get_average(self) -> Optional[float]:
        """Get moving average."""
        return self.ma_filter.get_average()
    
    def is_stable(self) -> bool:
        """Check if filter has stabilized."""
        return self.ma_filter.is_ready()


class MultiParameterFilter:
    """Manages filters for all sensor parameters."""
    
    def __init__(self, parameters: List[str] = None):
        from ..config import VALID_PARAMETERS
        self.parameters = parameters or list(VALID_PARAMETERS)
        self.filters = {p: SensorFilter(p) for p in self.parameters}
        
    def process_all(self, readings: dict) -> dict:
        """Process all readings, return filtered values."""
        filtered = {}
        for param, value in readings.items():
            if param in self.filters:
                filtered[param] = self.filters[param].process(value)
            else:
                filtered[param] = value  # Pass through unknown parameters
        return filtered
    
    def get_filtered(self) -> dict:
        """Get all current filtered values."""
        return {p: f.get_current() for p, f in self.filters.items()}
    
    def get_averages(self) -> dict:
        """Get all moving averages."""
        return {p: f.get_average() for p, f in self.filters.items()}
    
    def is_ready(self, parameter: str) -> bool:
        """Check if filter for parameter is ready."""
        if parameter in self.filters:
            return self.filters[parameter].is_stable()
        return True
    
    def all_ready(self) -> bool:
        """Check if all filters are ready."""
        return all(f.is_stable() for f in self.filters.values())