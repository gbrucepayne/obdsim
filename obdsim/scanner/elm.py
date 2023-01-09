"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging
import time

from obdsim.elm import Elm327, ElmStatus

from .base_scanner import ObdScanner, ObdSignal

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
        self.elm.initialize(auto_protocol=kwargs.get('auto_protocol', True))
    
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
            response_time = time.time()
            while len(res) < 8:
                _log.debug(f'Padding ELM response with zero byte')
                res = bytearray(res + b'\x00')
            decoded = self._db.decode_message(self._obd_res.frame_id, res)
            rx_mode = decoded['service'].value
            pid_mux = f'PID_S{mode:01x}'
            rx_pid = decoded[pid_mux].value
            if rx_mode != mode or rx_pid != pid:
                _log.warning('Mode or PID mismatch')
            value = decoded[ObdSignal.get_name_by_pid(rx_pid)]
            return ObdSignal(rx_mode, rx_pid, value, response_time)
        _log.warning(f'No response to query')
