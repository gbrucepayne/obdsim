"""OBD2 sender utility to generate requests for vehicle sensor data."""
import logging
import os
from subprocess import PIPE, Popen
from time import sleep

import can
import obd
from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

DBC_FILE = os.getenv('DBC_FILE', './dbc/CSS-Electronics-OBD2-v1.4.1.dbc')
DBC_MSG_NAME = os.getenv('DBC_MSG_NAME', 'OBD2_REQUEST')

_log = logging.getLogger(__name__)


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
        self._parameters = {}

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
    
    def query(self, content: dict) -> 'dict|None':
        """Returns the result of an OBD2 query."""
        if 'request' not in content:
            content['request'] = 0
        if 'service' not in content:
            content['service'] = 1
        data = self.obd_message.encode(content)
        request = can.Message(arbitration_id=self.obd_message.frame_id,
                              data=data)
        response = None
        decoded = None
        self.bus.send(request)
        while response is None:
            response = self.bus.recv(timeout=self.timeout)
            if response:
                decoded = self.db.decode_message(response.arbitration_id,
                                                 response.data)
                _log.debug(f'CANbus received: {decoded}')
            sleep(0.1)
        return decoded

    def pids_supported(self):
        pid_commands = [
            'S1_PID_00_PIDsSupported_01_20',
            # 'S1_PID_20_PIDsSupported_21_40',
            # 'S1_PID_40_PIDsSupported_41_60',
        ]
        for cmd in pid_commands:
            content = {
                'length': 2,
                'ParameterID_Service01': int(cmd.split('_')[2], 16),
            }
            response = self.query(content)
            pid_bitmask = format(response[cmd], '#034b')[2:]
            offset = int(cmd.split('_')[4]) - 1
            for bit in pid_bitmask:
                offset += 1
                if bit == '1':
                    self._pids_supported.append(offset)
    
    def start(self):
        self.pids_supported()
        _log.info(f'PIDs supported: {self._pids_supported}')
        self._loop()
    
    def _loop(self):
        for pid in self._pids_supported:
            content = {
                'length': 3,
                'ParameterID_Service01': pid,
            }
            self._parameters[pid] = self.query(content)
            _log.info(f'Updated PID {pid} = {self._parameters[pid]}')
        sleep(self.interval)
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
