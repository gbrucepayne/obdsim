"""OBD2 scanner for native CANbus (ISO 15765-4)."""
import logging
import os
import time

import can

from .base_scanner import ObdScanner, ObdSignal

_log = logging.getLogger(__name__)


class CanScanner(ObdScanner):
    """Scans periodically on a native or virtual CANbus using ISO 15765-4.
    
    Subclass of ObdScanner.
    """
    
    __doc__ = f'{ObdScanner.__doc__}\n{__doc__}'
    
    def __init__(self, bus_name: str = None, **kwargs) -> None:
        """Create a CAN scanner.
        
        Args:
            bus_name (str): The CANbus name e.g. `can0`
            scan_interval (float): The interval in seconds to scan PIDs.
                Default `1.0`
            scan_timeout (float): The timeout waiting for a response.
                Default `0.1`
            dbc_filename (str): The filename/path of the `.dbc` reference
            dbc_msgename (str): The BO_ name of the request name in the
                `.dbc` file.
        
        """
        super().__init__(**kwargs)
        self._bus_name = bus_name
        self.bus: can.Bus = None

    def connect(self, bus_name: str = None):
        """Connects to the OBD2 CANbus.
        
        Args:
            bus_name: The CANbus name e.g. `can0`. Not required if the name
                was specified during creation.
        
        """
        if not bus_name:
            if not self._bus_name:
                raise ValueError('Missing bus_name')
            else:
                bus_name = self._bus_name
        elif not self._bus_name:
            self._bus_name = bus_name
        sys_name = f'/sys/class/net/{bus_name}'
        if not os.path.exists(sys_name):
            raise FileNotFoundError(f'Cannot find {sys_name}')
        _log.debug(f'Using CANbus {bus_name}')
        self.bus = can.Bus(bus_name, bustype='socketcan')
    
    @property
    def is_connected(self) -> bool:
        return self.bus is not None
    
    def query(self, pid: int, mode: int = 1) -> 'ObdSignal|None':
        """Returns the result of an OBD2 query via CANbus."""
        if mode == 9 and pid == 2:
            if not self.vin_message_count:
                raise ValueError('Must query mode 9 pid 1 first'
                                 'to determine response message count')
            vin = ''
        pid_mux = f'PID_S{mode:01x}'   #: Simplified DBC
        content = {
            'request': 0,
            'service': mode,
            'length': 2,
            pid_mux: pid,
        }
        data = self._obd_req.encode(content)
        request = can.Message(arbitration_id=self._obd_req.frame_id,
                              is_extended_id=self._obd_req.frame_id >= 2**1,
                              data=data)
        response_complete = False
        partial_responses = 0
        response = None
        signal = None
        self.bus.send(request)
        attempts = 0
        max_attempts = 3
        if mode == 9 and pid == 2:
            max_attempts += self.vin_message_count
        while not response_complete and attempts < max_attempts:
            attempts += 1
            response = self.bus.recv(timeout=self.scan_timeout)
            if response:
                response_time = time.time()
                if mode == 9 and pid == 2:
                    _log.info('Parsing multi-message response')
                    partial_responses += 1
                    _log.warning('Not implemented'
                                 f' - message part {partial_responses}'
                                 f'{response}')
                    vin += self._parse_vin_part(response.data, partial_responses)
                    if partial_responses == self.vin_message_count:
                        response_complete = True
                        signal = ObdSignal(1, pid, vin, ts=response_time)
                else:
                    decoded = self._db.decode_message(response.arbitration_id,
                                                      response.data)
                    _log.debug(f'CANbus received: {decoded}')
                    if pid_mux not in decoded:
                        continue
                    rx_mode = decoded['service'].value
                    rx_pid = decoded[pid_mux].value
                    value = decoded[ObdSignal.get_name_by_pid(rx_pid, rx_mode)]
                    if rx_mode == 9 and rx_pid == 1:
                        self.vin_message_count = value
                    signal = ObdSignal(mode, rx_pid, value, response_time)
        if not signal:
            _log.warning(f'No response received for mode {mode} PID {pid}')
        return signal
    
    def _parse_vin_part(self, data: bytes, part: int) -> str:
        if part == 1:
            vin_part_bytes = data[5:8]
        else:
            vin_part_bytes = data[1:]
        vin_part = ''.join(chr(c) for c in vin_part_bytes)
        _log.warning('VIN parsing not implemented')
        return vin_part
