"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging
import os
import time
from subprocess import PIPE, Popen

import can

from obdsim.obdsignal import ObdSignal
from obdsim.obdscanner import ObdScanner

_log = logging.getLogger(__name__)


class CanScanner(ObdScanner):
    """Scans on a native or virtual CANbus using OBDII."""
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

    def connect(self, bus_name: str = 'vcan0'):
        sys_name = f'/sys/class/net/{bus_name}'
        if not os.path.exists(sys_name):
            _log.debug(f'Attempting to create virtual {bus_name}')
            script_dir = f'{os.getcwd()}/vcan.sh'
            with Popen(['bash', script_dir], stdout=PIPE) as proc:
                _log.debug(proc.stdout.read())
        if not os.path.exists(sys_name):
            raise FileNotFoundError(f'Cannot find {sys_name}')
        _log.debug(f'Using CANbus {bus_name}')
        self.bus = can.Bus(bus_name, bustype='socketcan')
    
    def query(self, pid: int, mode: int = 1) -> 'ObdSignal|None':
        """Returns the result of an OBD2 query."""
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