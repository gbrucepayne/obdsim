import logging
import os
import threading
from subprocess import PIPE, Popen
from time import sleep

import can
from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

from .obdsignal import ObdSignal

DBC_FILE = os.getenv('DBC_FILE', './dbc/python-obd.dbc')
DBC_MSG_NAME = os.getenv('DBC_MSG_NAME', 'OBD2_RESPONSE')

_log = logging.getLogger(__name__)


class ObdSimulator:
    """A simulator for OBD2 responses."""
    def __init__(self,
                 db: str = DBC_FILE,
                 canbus: can.Bus = None,
                 timeout: float = 0.1,
                 ) -> None:
        self.db: CanDatabase = load_can_database(db)
        self.obd_message: CanMessage = self.db.get_message_by_name(DBC_MSG_NAME)
        self.bus: can.Bus = canbus
        self.timeout: float = timeout
        self._listener = threading.Thread(target=self._listen,
                                          name='obd_listener',
                                          daemon=True)
        self.signals = {}
    
    def start(self):
        self._listener.start()
        
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
    
    def _listen(self):
        """"""
        while True:
            if self.bus is None:
                continue
            received = self.bus.recv(timeout=self.timeout)
            if received:
                _log.debug(f'CANbus received: {received.data}')
                try:
                    decoded = self.db.decode_message(received.arbitration_id,
                                                     received.data)
                    _log.debug(f'Decoded: {decoded}')
                    if 'request' in decoded:
                        self._process_request(decoded)
                    else:
                        _log.debug(f'Ignoring message: {decoded}')
                except Exception as err:
                    _log.error(f'Error decoding CAN message: {err}')
                    raise err
            sleep(0.1)
    
    def send_response(self, message: can.Message):
        """"""
        if not isinstance(message, can.Message):
            raise ValueError('Invalid CAN Message')
        _log.debug(f'Sending raw CAN data: {message.data}')
        self.bus.send(message)
        
    def _process_request(self, request):
        """"""
        # request = {
        #     'length': 3,
        #     'request': 0,
        #     'service': 1,   # mode
        #     'ParameterID_Service01': 13,   # pid (decimal)
        #     'S1_PID_0D_VehicleSpeed': 50,
        # }
        _log.debug(f'Processing {request}')
        response = None
        if 'service' not in request:
            raise ValueError('OBD request or db missing mode')
        if request['service'] == 1:
            _log.debug(f'Simulating mode 1 response')
            if 'PID_MODE_01' not in request:
                raise ValueError('Missing PID for Mode 1')
            pid = request['PID_MODE_01']
            response = {
                'response': 4,
                'service': 1,
                'PID_MODE_01': pid,
            }
            if pid == 0:
                response['length'] = 6
                response['PIDS_A'] = pids_a_supported()
            elif pid == 0xC:
                if 'RPM' not in self.signals:
                    self.signals['RPM'] = 1165
                response['length'] = 4
                response['RPM'] = self.signals['RPM']
            elif pid == 0xD:
                if 'SPEED' not in self.signals:
                    self.signals['SPEED'] = 50
                response['length'] = 3
                response['SPEED'] = self.signals['SPEED']
            else:
                _log.warning(f'Unhandled Mode 01 PID {pid}')
                response = None
        if response:
            data = self.obd_message.encode(response)
            message = can.Message(arbitration_id=self.obd_message.frame_id,
                                  data=data)
            self.send_response(message)
        else:
            _log.warning(f'No response for {request}')


def pids_a_supported() -> int:
    """"""
    supported_signals = ['RPM', 'SPEED']
    bitmask = 0
    for sig in supported_signals:
        pid = ObdSignal.get_pid_by_name(sig)
        bitmask = bitmask | 1 << (32 - pid)
    return bitmask
