"""OBD2 sender utility to generate requests for vehicle sensor data.

OBSOLETE - deprecate. replaced by obdscanner module with subclasses.

"""
import logging
import os
import time
from subprocess import PIPE, Popen

import can
import obd
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


class ElmScanner:
    def __init__(self) -> None:
        self.connection: obd.OBD = None
        self._sensor_cache = {}
        
    def connect(self, port: str = None):
        protocol = obd.protocols.ISO_15765_4_11bit_500k.ELM_ID
        self.connection = obd.OBD(portstr=port, protocol=protocol)
    
    def query(self, pid: int, mode: int = 1) -> 'ObdSignal|None':
        """"""
        cmd = obd.commands[mode][pid]
        response = self.connection.query(cmd)
        signal = None
        if response:
            try:
                signal = ObdSignal(mode, pid, response.value, response.time)
            except Exception as err:
                _log.error(err)
        return signal
        
    # def pids_supported(self) -> list:
    #     pids_supported = []
    #     pid_commands = [
    #         obd.commands.PIDS_A,
    #         obd.commands.PIDS_B,
    #         obd.commands.PIDS_C,
    #     ]
    #     for cmd in pid_commands:
    #         res = self.connection.query(cmd)
    #         if res:
    #             pids_supported.append(res.value)
    #     return pids_supported
