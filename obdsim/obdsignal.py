"""A model for simulated OBD2 PID signals."""
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import pint

# from pint.unit import ScaleConverter, UnitDefinition

ureg = pint.UnitRegistry()
ureg.define('percent = [] = %')
ureg.define('ratio = []')
ureg.define('gps = gram / second = GPS = grams_per_second')
ureg.define('lph = liter / hour = LPH = liters_per_hour')
ureg.define('ppm = count / 1000000 = PPM = parts_per_million')
# ureg.define(UnitDefinition('percent', 'pct', (), ScaleConverter(1 / 100.0)))
Q_ = ureg.Quantity


def decode_pids_supported(mode: int,
                          pid: int,
                          value: int,
                          previous: dict = {},
                          ) -> 'dict[int, list]':
    """Decodes the PIDs supported bitmask to dictionary of PID lists.
    
    If a previous pids_supported dictionary is provided it will be updated
    with the new mode and/or PIDs.
    
    Args:
        mode: The service/mode number.
        pid: The parameter ID number.
        value: The raw value of the PID response.
        previous: Optional previous dictionary to be updated.
    
    Returns:
        A dictionary formatted as `{ mode: [<pids>] }
        
    """
    supported = []
    bitmask_str = f'{value:032b}'
    for i, bit in enumerate(reversed(bitmask_str)):
        if bit == '1':
            supported.append(pid + i + 1)
    supported.sort()
    if previous:
        if mode not in previous:
            previous[mode] = []
        previous[mode] = [p for p in supported if p not in previous[mode]].sort()
        return previous
    return { mode: supported }
    

def encode_pids_supported(pid: int, pid_list: 'list[int]') -> int:
    """Encodes a list of pids for a reference PIDs supported.
    
    Args:
        pid: The reference PID being encoded.
        pid_list: The list of supported PIDs (within the given mode and range)
    
    Returns:
        A 32-bit integer bitmask.
        
    """
    if any(p not in range(0, 256) for p in pid_list):
        raise ValueError('Invalid PID in list')
    if any(p > pid + 32 for p in pid_list):
        raise ValueError('PIDs in list must be within 32 of reference pid')
    bitmask = 0
    for p in list(set(pid_list)):
        bitmask = bitmask | 1 << (p - 1)
    return bitmask


@dataclass
class ObdSupportedPids:
    """A class representing a supported PIDS bitmask."""
    mode: int
    pid: int
    value: int = 0
    
    @property
    def pids(self) -> 'list[int]':
        supported = []
        bitmask_str = f'{self.value:032b}'
        for i, bit in enumerate(reversed(bitmask_str)):
            if bit == '1':
                supported.append(self.pid + i + 1)
        supported.sort()
        return supported
    
    @pids.setter
    def pids(self, pid_list: 'list[int]'):
        if any(p not in range(0, 256) for p in pid_list):
            raise ValueError('Invalid PID in list')
        if any(p > self.pid + 32 for p in pid_list):
            raise ValueError('PIDs in list must be within 32 of reference pid')
        bitmask = 0
        for p in list(set(pid_list)):
            bitmask = bitmask | 1 << (p - self.pid - 1)
        self.value = bitmask


class ObdIgnitionType(IntEnum):
    SPARK = 0
    COMPRESSION = 1


@dataclass
class ObdStatus:
    """A class representing OBD Status."""
    mil: bool
    dtc_count: int
    ignition_type: ObdIgnitionType


@dataclass
class ObdPidDefinition:
    """A class representing a PID definition."""
    mode: int
    pid: int
    length: int
    name: str
    data_type: Any
    scale: float = 1
    offset: int = 0
    unit: Any = None


@dataclass
class ObdVin:
    """"""
    packet_number: int
    packet_value: str


PID_DEFINITIONS: 'list[ObdPidDefinition]' = [
    ObdPidDefinition(0x1, 0x00, 6, 'S1_PIDS_01_20', ObdSupportedPids),
    ObdPidDefinition(0x1, 0x20, 6, 'S1_PIDS_21_40', ObdSupportedPids),
    ObdPidDefinition(0x1, 0x40, 6, 'S1_PIDS_41_60', ObdSupportedPids),
    ObdPidDefinition(0x1, 0x60, 6, 'S1_PIDS_61_80', ObdSupportedPids),
    ObdPidDefinition(0x1, 0x80, 6, 'S1_PIDS_81_A0', ObdSupportedPids),
    ObdPidDefinition(0x1, 0xA0, 6, 'S1_PIDS_A1_C0', ObdSupportedPids),
    ObdPidDefinition(0x1, 0x01, 6, 'STATUS', ObdStatus),
    ObdPidDefinition(0x1, 0x0C, 4, 'ENGINE_SPEED', int, 0.25, 0, ureg.rpm),
    ObdPidDefinition(0x1, 0x0D, 3, 'VEHICLE_SPEED', int, 1, 0, ureg.kph),
    ObdPidDefinition(0x1, 0x21, 4, 'DISTANCE_W_MIL', int, 1, 0, ureg.km),
    ObdPidDefinition(0x1, 0x5C, 3, 'OIL_TEMP', int, 1, -40, ureg.degC),
    ObdPidDefinition(0x9, 0x00, 6, 'S9_PIDS_01_20', ObdSupportedPids),
    ObdPidDefinition(0x9, 0x01, 4, 'VIN_MCOUNT', int, 1, 0, ureg.count),
    ObdPidDefinition(0x9, 0x02, 6, 'VIN', ObdVin),
]


class ObdSignal:
    """A class defining a simulated OBD2 signal.
    
    Attributes:
        mode (int): The OBD2 mode / service.
        pid (int): The OBD2 PID parameter number (service-dependent).
        length (int): The number of bytes used by the PID.
        value: A measurement value with units from the `pint` module.
        value_raw: The raw measurement value without units.
        ts (float): The (unix) timestamp of the measurement.
        
    """
    def __init__(self, mode: int, pid: int, value: Any, ts: float = None) -> None:
        """Creates an ObdSignal.
        
        Args:
            mode: The OBD2 service/mode number
            pid: The Parameter ID number
            value: The decoded (raw) value
            ts: The timestamp of the decoded value
            
        """
        self.mode: int = mode
        self.pid: int = pid
        self.pid_def: ObdPidDefinition = None
        for pid_def in PID_DEFINITIONS:
            if pid_def.mode == mode and pid_def.pid == pid:
                self.pid_def = pid_def
                break
        if self.pid_def is None:
            raise ValueError(f'Undefined PID {pid} (mode {mode})')
        self._data_type = None
        self._length: int = 0
        self._value = None
        self.ts: float = ts or time.time()
        self.value = value

    @classmethod
    def get_pid_by_name(cls, name: str, mode: int = 1) -> 'int|None':
        for pid_def in PID_DEFINITIONS:
            if pid_def.name == name and pid_def.mode == mode:
                return pid_def.pid
        
    @classmethod
    def get_name_by_pid(cls, pid: int, mode: int = 1) -> 'str|None':
        for pid_def in PID_DEFINITIONS:
            if pid_def.pid == pid and pid_def.mode == mode:
                return pid_def.name
        
    @property
    def name(self) -> str:
        return self.pid_def.name
    
    @property
    def unit(self):
        return self.pid_def.unit
        
    @property
    def length(self) -> int:
        return self.pid_def.length
    
    @property
    def value_raw(self):
        return self._value
    
    @property
    def value(self) -> Any:
        if self.pid_def.data_type.__name__ == 'ObdSupportedPids':
            return ObdSupportedPids(self.mode, self.pid, self._value).pids
        if self.pid_def.data_type.__name__ == 'int':
            return self.pid_def.offset + self.pid_def.scale * self._value
        return self._value
    
    @value.setter
    def value(self, value):
        if self.pid_def.data_type.__name__ == 'ObdSupportedPids':
            if isinstance(value, int):
                self._value = value
            elif isinstance(value, list):
                if any(p not in range(0, 256) for p in value):
                    raise ValueError('Invalid list of PIDs')
                obj = ObdSupportedPids(self.mode, self.pid)
                obj.pids = value
                self._value = obj.value
            else:
                raise ValueError(f'Unexpected data type {type(value)}')
        elif self.pid_def.data_type.__name__ == 'int':
            self._value = int((value - self.pid_def.offset) /
                              self.pid_def.scale)
        elif self.pid_def.data_type.__name__ == 'ObdVin':
            if not isinstance(value, str) or len(value) != 17:
                raise ValueError('Invalid VIN')
        self._value = value

    @property
    def quantity(self) -> Any:
        if self.pid_def.data_type.__name__ == 'int':
            return Q_(self.value, self.pid_def.unit)
        return self.value


def pid_definitions(dbc_filename: str) -> 'list':
    """Builds PID definitions from a DBC file."""
    raise NotImplementedError
    return []
