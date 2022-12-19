"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging
import os
import time

from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

from .obdsignal import ObdSignal

DBC_FILE = os.getenv('DBC_FILE', './dbc/python-obd.dbc')
DBC_MSG_NAME = os.getenv('DBC_MSG_NAME', 'OBD2_REQUEST')

_log = logging.getLogger(__name__)


class ObdScanner:
    """An OBDII Scanner class.
    
    Attributes:
        scan_interval (float): The interval in seconds to scan PIDs. Default `1`
        scan_timeout (float): The timeout waiting for a response. Default `0.1`
        dbc_filename (str): The filename/path of the `.dbc` reference
        dbc_msgename (str): The BO_ name of the request name in the `.dbc` file.
        
    """
    def __init__(self,
                 scan_interval: float = 1.0,
                 scan_timeout: float = 0.1,
                 dbc_filename: str = DBC_FILE,
                 dbc_msgname: str = DBC_MSG_NAME,
                 ) -> None:
        self.scan_interval = scan_interval
        self.scan_timeout = scan_timeout
        self._db: CanDatabase = load_can_database(dbc_filename)
        self._obd_message: CanMessage = self._db.get_message_by_name(dbc_msgname)
        self._pids_supported: 'dict[list[int]]' = {}
        # _signals as [mode][pid] = ObdSignal
        self._signals: dict = {}
        self._running = False
    
    @property
    def pids_supported(self) -> 'dict[list[int]]':
        return self._pids_supported
    
    @property
    def signals(self) -> dict:
        return self._signals
    
    def connect(self):
        """Overwrite with specific method in subclass."""
        raise NotImplementedError('Subclass must provide connect method.')
    
    def start(self):
        """Starts OBD scanning."""
        self._pids_supported = { 1: [] }
        self._signals = { 1: {} }
        self._get_pids_supported()
        _log.info(f'PIDs supported: {self.pids_supported}')
        self._running = True
        self._loop()
    
    def stop(self):
        """Stops OBD scanning."""
        self._running = False
    
    def query(self, pid: int, mode: int = 1) -> ObdSignal:
        """Overwrite with specific method in subclass."""
        raise NotImplementedError('Subclass must provide query method.')
    
    def _get_pids_supported(self):
        """Queries the vehicle bus for supported PIDs."""
        pid_commands = {
            1: ['PIDS_A', 'PIDS_B', 'PIDS_C'],
        }
        for mode, cmds in pid_commands.items():
            for cmd in cmds:
                if mode not in self._pids_supported:
                    self._pids_supported[mode] = []
                pid = ObdSignal.get_pid_by_name(cmd)
                if pid is None:
                    _log.warning(f'{cmd} undefined - skipping')
                    continue
                response = self.query(pid, mode)
                for pid in response.value:
                    pids_supported: list = self._pids_supported[mode]
                    if pid not in pids_supported:
                        pids_supported.append(pid)
                    pids_supported.sort()
        
    def _loop(self):
        """Loops through supported pids querying and populating signals."""
        if self._running:
            for mode, pids_supported in self.pids_supported.items():
                for pid in pids_supported:
                    signal = self.query(pid, mode)
                    if (not isinstance(self._signals, dict) or
                        mode not in self._signals):
                        # create mode signals dictionary
                        self._signals[mode] = {}
                    self._signals[mode][pid] = signal.value
                    _log.info(f'Updated [{mode}][{pid}] "{signal.name}"'
                              f' = {self._signals[mode][pid]}')
        time.sleep(self.scan_interval)
        self._loop()
