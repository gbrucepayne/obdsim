"""A model for simulated OBD2 PID signals."""
import time
from enum import IntEnum

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
    bitmask = f'{value:032b}'
    for i, bit in enumerate(reversed(bitmask)):
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


class ObdIgnitionType(IntEnum):
    SPARK = 0
    COMPRESSION = 1


class ObdStatus:
    def __init__(self,
                 mil: bool,
                 dtc_count: int,
                 ignition_type: ObdIgnitionType,
                 ) -> None:
        self.mil = mil
        self.dtc_count = dtc_count
        self.ignition_type = ignition_type


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
    PID_DEFINITIONS = [
        # (mode, pid, name, unit/type, bytes)
        (0x1, 0x0, 'PIDS_A', 'bitmask', 4),
        (0x1, 0x1, 'STATUS', ObdStatus),
        # (0x1, 0x2, 'FREEZE_DTC', 'FreezeDtc'),
        # (0x1, 0x3, 'FUEL_STATUS', tuple[str, str]),
        (0x1, 0x4, 'ENGINE_LOAD', ureg.percent),
        (0x1, 0xc, 'RPM', ureg.rpm),
        (0x1, 0xd, 'SPEED', ureg.kph),
        (0x9, 0x0, 'S9_PIDS_01_20', 'bitmask', 4),
        (0x9, 0x1, 'S9_VIN_MCOUNT', ureg.count, 4),
        (0x9, 0x0, 'S9_VIN', None, 4),
    ]
    
    def __init__(self, mode: int, pid: int, value, ts: float = None) -> None:
        """Creates an ObdSignal.
        
        Args:
            mode: The OBD2 service/mode number
            pid: The Parameter ID number
            value: The decoded (raw) value
            ts: The timestamp of the decoded value
            
        """
        self.mode: int = mode
        self.pid: int = pid
        self._length: int = 0
        self._value = value
        self.ts: float = ts or time.time()

    @classmethod
    def get_pid_by_name(cls, name: str, mode: int = 1) -> 'int|None':
        for pid_def in cls.PID_DEFINITIONS:
            if pid_def[2] == name and pid_def[0] == mode:
                return pid_def[1]
        
    @classmethod
    def get_name_by_pid(cls, pid: int, mode: int = 1) -> 'str|None':
        for pid_def in cls.PID_DEFINITIONS:
            if pid_def[1] == pid and pid_def[0] == mode:
                return pid_def[2]
        
    @property
    def name(self) -> str:
        for pid_def in self.PID_DEFINITIONS:
            if pid_def[0] == self.mode and pid_def[1] == self.pid:
                return pid_def[2]
    
    @property
    def unit(self):
        for pid_def in self.PID_DEFINITIONS:
            if pid_def[0] == self.mode and pid_def[1] == self.pid:
                return pid_def[3]
        
    @property
    def value_raw(self):
        return self._value
    
    @property
    def value(self) -> ureg.Quantity:
        if self.unit == 'bitmask':
            pid_list = decode_pids_supported(self.mode, self.pid, self._value)
            return pid_list[self.mode]
        elif isinstance(self.unit, ObdStatus):
            raise NotImplementedError
        elif self.unit == ureg.percent:
            return self._value * ureg.percent
        elif self.unit == ureg.rpm:
            return self._value * ureg.rpm
        elif self.unit == ureg.kph:
            return self._value * ureg.kph
        # elif self.pid in PIDS_UNIT_DEGREE:
        #     return self._value * ureg.degree
        # elif self.pid in PIDS_UNIT_GPS:
        #     return self._value * ureg.grams_per_second
        # elif self.pid in PIDS_UNIT_V:
        #     return self._value * ureg.volt
        # elif self.pid in PIDS_UNIT_SEC:
        #     return self._value * ureg.second
        # elif self.pid in PIDS_UNIT_KM:
        #     return self._value * ureg.kilometer
        # elif self.pid in PIDS_UNIT_COUNT:
        #     return self._value * ureg.count
        # elif self.pid in PIDS_UNIT_PASCAL:
        #     return self._value * ureg.pascal
        # elif self.pid in PIDS_UNIT_MA:
        #     return self._value * ureg.milliamp
        # elif self.pid in PIDS_UNIT_RATIO:
        #     return self._value * ureg.ratio
        # elif self.pid in PIDS_UNIT_MIN:
        #     return self._value * ureg.minute
        # elif self.pid in PIDS_UNIT_LPH:
        #     return self._value * ureg.litre_per_hour
        # elif self.pid in PIDS_STRING:
        #     return str(self._value)
        else:
            return self._value
    
    @value.setter
    def value(self, value):
        raise NotImplementedError
    
    @property
    def length(self) -> int:
        # TODO: populate length for different parameters
        return self._length


def pid_definitions(dbc_filename: str) -> 'list':
    """Builds PID definitions from a DBC file."""
    raise NotImplementedError
    return []
