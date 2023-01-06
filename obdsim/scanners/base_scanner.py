"""OBD2 sender base class to generate requests for vehicle sensor data.

"""
import logging
import os
import time

from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

from obdsim import ObdSignal

DBC_FILE = os.getenv('DBC_FILE', './dbc/python-obd.dbc')
DBC_REQUEST = os.getenv('DBC_REQUEST', 'OBD2_REQUEST')
DBC_RESPONSE = os.getenv('DBC_RESPONSE', 'OBD2_ECU_RESPONSE')

_log = logging.getLogger(__name__)


class ObdScanner:
    """An OBDII Scanner class.
    
    Attributes:
        scan_interval (float): The interval in seconds to scan PIDs. Default `1`
        scan_timeout (float): The timeout waiting for a response. Default `0.1`
        dbc_filename (str): The filename/path of the `.dbc` reference
        dbc_msgename (str): The BO_ name of the request name in the `.dbc` file.
        pids_supported (dict): The PIDs supported by the vehicle, described
            as { mode: [pid, ...]} where mode and pid are integers.
        signals (dict): The decoded values of the PIDs most recently queried.
            Described by { mode: { pid: ObdSignal }}
        
    """
    def __init__(self,
                 scan_interval: float = 1.0,
                 scan_timeout: float = 0.1,
                 dbc_filename: str = DBC_FILE,
                 dbc_request: str = DBC_REQUEST,
                 dbc_response: str = DBC_RESPONSE,
                 ) -> None:
        """Instantiates the class.
        
        Args:
            scan_interval: The refresh interval in seconds for supported PIDs.
            scan_timeout: The time in seconds to wait for a response.
            dbc_filename: The file path/name of the DBC to be used.
                Can be set using environment variable `DBC_FILE`.
                Defaults to `./dbc/python-obd.dbc`
            dbc_request: The name of the request message set in the `BO_`
                definition within the DBC file.
            dbc_response: The name of the response message set in the `BO_`
                definition within the DBC file.
        
        """
        self.scan_interval = scan_interval
        self.scan_timeout = scan_timeout
        self._db: CanDatabase = load_can_database(dbc_filename)
        self._obd_req: CanMessage = self._db.get_message_by_name(dbc_request)
        self._obd_res: CanMessage = self._db.get_message_by_name(dbc_response)
        self._pids_supported: 'dict[list[int]]' = {}
        # _signals as [mode][pid] = ObdSignal
        self._signals: dict = {}
        self._running = False
    
    @property
    def pids_supported(self) -> 'dict[list[int]]':
        """PIDS supported by the vehicle."""
        return self._pids_supported
    
    @property
    def signals(self) -> 'dict[dict[ObdSignal]]':
        """Decoded signal values read from the vehicle."""
        return self._signals
    
    def connect(self):
        """Connects to the vehicle OBD2 bus."""
        raise NotImplementedError('Subclass must provide connect method.')
    
    @property
    def is_connected(self) -> bool:
        """Indicates if vehicle is connected and available for queries."""
        raise NotImplementedError('Subclass must provide is_connected property')
    
    def start(self):
        """Starts OBD scanning."""
        _log.info('Starting PID scanning')
        self._pids_supported = { 1: [] }
        self._signals = { 1: {} }
        self._get_pids_supported()
        if not self.pids_supported:
            raise ConnectionError('Unable to determine supported PIDs')
        _log.info(f'PIDs supported: {self.pids_supported}')
        self._running = True
        self._loop()
    
    def stop(self):
        """Stops OBD scanning."""
        self._running = False
    
    def query(self, pid: int, mode: int = 1) -> ObdSignal:
        """Queries a specific PID with optional mode."""
        raise NotImplementedError('Subclass must provide query method.')
    
    def _get_pids_supported(self):
        """Queries the vehicle bus for supported PIDs."""
        # if not self.is_connected:
        #     _log.warning('Vehicle is not connected - skipping')
        #     self._pids_supported = {}
        #     return
        pid_commands = {
            1: ['PIDS_A', 'PIDS_B', 'PIDS_C'],
            # 9: [],
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
        """Loops through supported pids querying and populating signals.
        
        Repeats at the scan_interval.
        """
        if self._running:
            # if not self.pids_supported:
            #     _log.warning('No PIDS found - re-initializing')
            #     self._get_pids_supported()
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
