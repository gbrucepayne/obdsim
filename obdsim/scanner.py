"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging
import os
import time
from subprocess import PIPE, Popen

import can
import obd
from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

from .obd_signal import ObdSignal

DBC_FILE = os.getenv('DBC_FILE', './dbc/python-obd.dbc')
DBC_MSG_NAME = os.getenv('DBC_MSG_NAME', 'OBD2_REQUEST')

_log = logging.getLogger(__name__)


class ObdScanner:
    def __init__(self) -> None:
        self.pids_supported: list = []
        self.scan_interval: float = 1.0
        self.scan_timeout: float = 0.1
        self.db: CanDatabase = None
        self._db_message_name: str
        self._signals = {}
        self._running = False
    
    def connect(self):
        """Overwrite with specific method in subclass."""
    
    def start(self):
        """Overwrite with specific method in subclass."""
        self._get_pids_supported()
        _log.info(f'PIDs supported: {self.pids_supported}')
        self._running = True
        self._loop()
    
    def stop(self):
        """"""
        self._running = False
    
    def query(self, pid: int, mode: int = 1) -> obd.OBDResponse:
        """Overwrite with specific method in subclass."""
    
    def _get_pids_supported(self):
        """"""
        pid_commands = []
        for command in pid_commands:
            _log.warning(f'Placeholder to query {command}')
            response = self.query(command).value
            pid_bitmask = format(response, '#034b')[2:]
            # TODO: determine offset based on command A/0x1-0x20, B/0x21-0x40, C/0x41-0x60
            offset = 1
            for bit in pid_bitmask:
                offset += 1
                if bit == '1':
                    if offset not in self.pids_supported:
                        self.pids_supported.append(offset)
        
    def _loop(self):
        """Loops through supported pids querying and populating signals."""
        if self._running:
            for pid in self.pids_supported:
                self._signals[pid] = self.query(pid)
                _log.info(f'Updated PID {pid} = {self._signals[pid]}')
            time.sleep(self.scan_interval)
            self._loop()


class CanScanner:
    def __init__(self,
                 db: str = DBC_FILE,
                 canbus: can.Bus = None,
                 timeout: float = 0.1,
                 interval: float = 1.0,
                 ) -> None:
        self.bus: can.Bus = canbus
        self.timeout: float = timeout
        self.db: CanDatabase = load_can_database(db)
        self.obd_message: CanMessage = self.db.get_message_by_name(DBC_MSG_NAME)
        self.interval = interval
        self._pids_supported: list = []
        # _signals as [mode][pid] = ObdSignal
        self._signals = { 1: {} }

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
    
    def query(self, content: dict) -> 'ObdSignal|None':
        """Returns the result of an OBD2 query."""
        obd_message = self.db.get_message_by_name(DBC_MSG_NAME)
        if 'request' not in content:
            content['request'] = 0
        if 'service' not in content:
            content['service'] = 1
        data = obd_message.encode(content)
        request = can.Message(arbitration_id=obd_message.frame_id,
                              data=data)
        response = None
        signal = None
        self.bus.send(request)
        while response is None:
            response = self.bus.recv(timeout=self.timeout)
            if response:
                try:
                    response_time = time.time()
                    decoded = self.db.decode_message(response.arbitration_id,
                                                     response.data)
                    _log.debug(f'CANbus received: {decoded}')
                    pid = ObdSignal.get_pid_by_name(decoded['PID_MODE_01'])
                    value = decoded[ObdSignal.get_name_by_pid(pid)]
                    signal = ObdSignal(1, pid, value, response_time)
                except Exception as err:
                    _log.error(err)
            time.sleep(0.1)
        return signal

    def pids_supported(self):
        pid_commands = ['PIDS_A', 'PIDS_B', 'PIDS_C']
        for cmd in pid_commands:
            pid = ObdSignal.get_pid_by_name(cmd)
            if pid is None:
                _log.warning(f'{cmd} undefined - skipping')
                continue
            content = {
                'length': 2,
                'PID_MODE_01': pid,
            }
            response = self.query(content)
            for pid in response.value:
                if pid not in self._pids_supported:
                    self._pids_supported.append(pid)
            self._pids_supported.sort()
    
    def start(self):
        self.pids_supported()
        _log.info(f'PIDs supported: {self._pids_supported}')
        self._loop()
    
    def _loop(self):
        for pid in self._pids_supported:
            content = {
                'length': 3,
                'PID_MODE_01': pid,
            }
            signal = self.query(content)
            self._signals[1][pid] = signal.value
            _log.info(f'Updated [1][{pid}] "{signal.name}"'
                      f' = {self._signals[1][pid]}')
        time.sleep(self.interval)
        self._loop()


class ElmScanner:
    def __init__(self) -> None:
        self.connection: obd.OBD = None
        self._sensor_cache = {}
        
    def connect(self, port: str = None):
        protocol = obd.protocols.ISO_15765_4_11bit_500k.ELM_ID
        self.connection = obd.OBD(portstr=port, protocol=protocol)
    
    def pids_supported(self) -> list:
        pids_supported = []
        pid_commands = [
            obd.commands.PIDS_A,
            obd.commands.PIDS_B,
            obd.commands.PIDS_C
        ]
        for cmd in pid_commands:
            res = self.connection.query(cmd)
            if res:
                pids_supported.append(res.value)
        return pids_supported
