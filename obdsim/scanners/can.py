"""OBD2 scanner for native CANbus (ISO 15765-4)."""
import logging
import os
import time

import can

from obdsim.scanners import ObdScanner
from obdsim import ObdSignal

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
        # pid_mode_str = f'PID_MODE_{mode:02d}'   #: for CSS example
        pid_mode_str = 'PID'   #: Simplified DBC
        content = {
            'request': 0,
            'service': mode,
            'length': 2,
            pid_mode_str: pid,
        }
        data = self._obd_req.encode(content)
        request = can.Message(arbitration_id=self._obd_req.frame_id,
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
