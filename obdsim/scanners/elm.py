"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging
import time

from obdsim.elm import Elm327, ElmStatus
from obdsim.obdsignal import ObdSignal
from obdsim.scanners import ObdScanner

_log = logging.getLogger(__name__)


class ElmScanner(ObdScanner):
    """Scans periodically via an ELM327-based OBD2 serial adapter.
    
    Subclass of ObdScanner.
    """
    
    __doc__ = f'{ObdScanner.__doc__}\n{__doc__}'
    
    def __init__(self, **kwargs) -> None:
        """Instantiate a scanner.
        
        Args:
            bluetooth (tuple): A tuple with (MAC, channel), if not using serial
            serial_name (str): The serial port name, if not using bluetooth
            
        """
        self._connection_kwargs = {}
        if 'bluetooth' in kwargs:
            if (not isinstance(kwargs['bluetooth'], tuple)):
                raise ValueError('Invalid bluetooth parameters')
            if 'serial_port' in kwargs:
                raise ValueError('Use only one of bluetooth or serial_name')
            self._connection_kwargs['bluetooth'] = kwargs.pop('bluetooth')
        elif not 'serial_name' in kwargs:
            raise ValueError('Missing serial_name or bluetooth parameters')
        else:
            self._connection_kwargs['serial_name'] = kwargs.pop('serial_name')
        scanner_kwargs = {}
        valid_scanner_kwargs = [
            'scan_interval',
            'scan_timeout',
            'dbc_filename',
            'dbc_msgname',
        ]
        for kwarg in kwargs:
            if kwarg in valid_scanner_kwargs:
                scanner_kwargs[kwarg] = kwargs.get(kwarg)
            else:
                self._connection_kwargs[kwarg] = kwargs.get(kwarg)
        super().__init__(**scanner_kwargs)
        self.elm = Elm327(**self._connection_kwargs)
        
    def connect(self, **kwargs):
        """Connects to the ELM327 adapter."""
        self.elm.connect()
        self.elm.initialize()
    
    @property
    def is_connected(self) -> bool:
        return self.elm.status == ElmStatus.CAR_CONNECTED
    
    def query(self, pid: int, mode: int = 1) -> 'ObdSignal|None':
        """Queries the OBD2 vehicle bus for a specific PID and optional mode."""
        if not self.is_connected:
            _log.warning('Vehicle not connected or ignition is off - skipping')
            return
        res: bytes = self.elm.query_pid(pid, mode)
        if res:
            res_mode = res[0]
            res_pid = res[1]
            res_data = res[2:]
            decoded = self._db.decode_message(self._obd_res.frame_id, res)
            # TODO: decode result
            value = 999   #: placeholder
            response_time = time.time()
            return ObdSignal(mode, pid, value, response_time)
