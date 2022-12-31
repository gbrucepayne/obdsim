"""OBD2 scanner for native CANbus (ISO 15765-4)."""
import logging
import os
import time

import can

from .. import ObdScanner, ObdSignal

_log = logging.getLogger(__name__)


class CanScanner(ObdScanner):
    """Scans periodically on a native or virtual CANbus using ISO 15765-4.
    
    Subclass of ObdScanner.
    """
    
    __doc__ = f'{ObdScanner.__doc__}\n{__doc__}'
    
    def __init__(self, canbus: can.Bus = None, **kwargs) -> None:
        """Create a CAN scanner.
        
        Args:
            canbus (can.Bus): The CANbus name e.g. `vcan0`
            scan_interval (float): The interval in seconds to scan PIDs.
                Default `1.0`
            scan_timeout (float): The timeout waiting for a response.
                Default `0.1`
            dbc_filename (str): The filename/path of the `.dbc` reference
            dbc_msgename (str): The BO_ name of the request name in the
                `.dbc` file.
        
        """
        super().__init__(**kwargs)
        self.bus: can.Bus = canbus

    def connect(self, bus_name):
        """Connects to the OBD2 CANbus."""
        if not bus_name:
            raise ValueError('Missing bus_name')
        sys_name = f'/sys/class/net/{bus_name}'
        if not os.path.exists(sys_name):
            raise FileNotFoundError(f'Cannot find {sys_name}')
        _log.debug(f'Using CANbus {bus_name}')
        self.bus = can.Bus(bus_name, bustype='socketcan')
    
    def query(self, pid: int, mode: int = 1) -> 'ObdSignal|None':
        """Returns the result of an OBD2 query via CANbus."""
        pid_mode_str = f'PID_MODE_{mode:02d}'
        content = {
            'request': 0,
            'service': mode,
            'length': 2,
            pid_mode_str: pid,
        }
        data = self._obd_message.encode(content)
        request = can.Message(arbitration_id=self._obd_message.frame_id,
                              data=data)
        response = None
        signal = None
        self.bus.send(request)
        while response is None:
            response = self.bus.recv(timeout=self.scan_timeout)
            if response:
                try:
                    response_time = time.time()
                    decoded = self._db.decode_message(response.arbitration_id,
                                                      response.data)
                    _log.debug(f'CANbus received: {decoded}')
                    pid = ObdSignal.get_pid_by_name(decoded[pid_mode_str])
                    value = decoded[ObdSignal.get_name_by_pid(pid)]
                    signal = ObdSignal(1, pid, value, response_time)
                except Exception as err:
                    _log.error(err)
            time.sleep(0.1)
        return signal
