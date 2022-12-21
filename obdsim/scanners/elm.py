"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging

import obd

from .. import ObdScanner, ObdSignal

_log = logging.getLogger(__name__)


class ElmScanner(ObdScanner):
    def __init__(self) -> None:
        self.connection: obd.OBD = None
        
    def connect(self, port: str = None):
        protocol = obd.protocols.ISO_15765_4_11bit_500k.ELM_ID
        _log.info(f'Searching for ELM327 adapters...')
        self.connection = obd.OBD(portstr=port, protocol=protocol)
        if not self.connection.is_connected():
            raise ConnectionError('Could not connect with ELM327 adapter')
    
    def query(self, pid: int, mode: int = 1) -> 'ObdSignal|None':
        """"""
        cmd = obd.commands[mode][pid]
        response = self.connection.query(cmd)
        signal = None
        if response:
            try:
                assert isinstance(response, obd.OBDResponse)
                _log.debug(f'ELM327 received: {response.message}')
                signal = ObdSignal(mode, pid, response.value, response.time)
            except Exception as err:
                _log.error(err)
        return signal
