"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging

import obd
from obd import OBDStatus

from .. import ObdScanner, ObdSignal

_log = logging.getLogger(__name__)


class ElmScanner(ObdScanner):
    """Scans periodically via an ELM327-based OBD2 serial adapter.
    
    Subclass of ObdScanner.
    """
    
    __doc__ = f'{ObdScanner.__doc__}\n{__doc__}'
    
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._adapter: obd.OBD = None
        self._protocol = None   # obd.protocols.ISO_15765_4_11bit_500k.ELM_ID
        
    def connect(self, port: str = None):
        """Connects to the ELM327 adapter."""
        _log.info(f'Searching for ELM327 adapters...')
        self._adapter = obd.OBD(portstr=port, protocol=self._protocol)
        _log.info(f'Adapter Status: {self._adapter.status()}')
        if not self._adapter.status() in [OBDStatus.ELM_CONNECTED, OBDStatus.OBD_CONNECTED, OBDStatus.CAR_CONNECTED]:
            raise ConnectionError('Could not connect with ELM327 adapter')
    
    def query(self, pid: int, mode: int = 1) -> 'ObdSignal|None':
        """Queries the OBD2 vehicle bus for a specific PID and optional mode."""
        if self._adapter.status() != OBDStatus.CAR_CONNECTED:
            _log.warning('Vehicle not connected')
            return
        cmd = obd.commands[mode][pid]
        response = self._adapter.query(cmd)
        signal = None
        if response:
            try:
                assert isinstance(response, obd.OBDResponse)
                _log.debug(f'ELM327 received: {response.message}')
                signal = ObdSignal(mode, pid, response.value, response.time)
            except Exception as err:
                _log.error(err)
        return signal
