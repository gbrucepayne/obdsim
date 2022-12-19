import time
from enum import IntEnum

from pint.unit import UnitRegistry, ScaleConverter, UnitDefinition

ureg = UnitRegistry()
Q = ureg.Quantity
ureg.define(UnitDefinition('percent', 'pct', (), ScaleConverter(1 / 100.0)))


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
    PID_DEFINITIONS = [
        # (mode, pid, name, unit/type, bytes)
        (0x1, 0x0, 'PIDS_A', 'bitmask'),
        (0x1, 0x1, 'STATUS', ObdStatus),
        # (0x1, 0x2, 'FREEZE_DTC', 'FreezeDtc'),
        # (0x1, 0x3, 'FUEL_STATUS', tuple[str, str]),
        (0x1, 0x4, 'ENGINE_LOAD', ureg.percent),
        (0x1, 0xc, 'RPM', ureg.rpm),
        (0x1, 0xd, 'SPEED', ureg.kph),
        # (0x9, 0x0, 'M09_PIDS_A', 'bitmask', 4),
    ]
    
    def __init__(self, mode: int, pid: int, value, ts: float = None) -> None:
        self.mode = mode
        self.pid = pid
        self._value = value
        self.ts = ts or time.time()

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
            bitmask = format(self._value, '#034b')[2:]
            offset = self.pid
            supported_pids = []
            for bit in bitmask:
                offset += 1
                if bit == '1' and offset not in supported_pids:
                    supported_pids.append(offset)
            return supported_pids
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
