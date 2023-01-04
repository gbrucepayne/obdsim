"""A basic vehicle simulator generating responses to supported OBD2 queries."""
import logging
import os
import threading
from time import sleep

import can
from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

from . import ObdSignal

DBC_FILE = os.getenv('DBC_FILE', './dbc/python-obd.dbc')
DBC_MSG_NAME = os.getenv('DBC_RESPONSE_BO_NAME', 'OBD2_RESPONSE')

_log = logging.getLogger(__name__)


class ObdSimulator:
    """A simulator for OBD2 responses.
    
    Attributes:
        timeout (float): The CANbus timeout seconds to wait for a query.
        signals (dict): The signals being simulated, defined as
            e.g. { 'SPEED': 50 }
        
    """
    def __init__(self,
                 canbus_name: str = None,
                 dbc: str = DBC_FILE,
                 dbc_bo_name: str = DBC_MSG_NAME,
                 timeout: float = 0.1,
                 ) -> None:
        """Instantiates the class.
        
        Args:
            canbus_name (str): The name of the CAN bus interface e.g. `can0`.
                Optional, can be specified with connect method.
            dbc (str): The `DBC` path/filename. Can use environment variable
                `DBC_FILE`, defaults to `./dbc/python-obd.dbc`.
            dbc_bo_name: The name of the BO_ definition in the DBC file.
                Supports environment variable `DBC_RESPONSE_BO_NAME`.
                Defaults to `OBD2_RESPONSE`.
            timeout: The bus timeout in seconds.
        """
        self._db: CanDatabase = load_can_database(dbc)
        self._obd_msg: CanMessage = self._db.get_message_by_name(dbc_bo_name)
        self._bus_name: str = canbus_name
        self._bus: can.Bus = None
        self.timeout: float = timeout
        self._listener = threading.Thread(target=self._listen,
                                          name='obd_listener',
                                          daemon=True)
        self.signals = {}
    
    def start(self):
        """Starts listening for queries on the CANbus."""
        self._listener.start()
        
    def connect(self, bus_name: str = None):
        """Connects to the CANbus."""
        if not bus_name:
            if not self._bus_name:
                raise ValueError('Missing bus_name')
            else:
                bus_name = self._bus_name
        elif not self._bus_name:
            self._bus_name = bus_name
        sys_name = f'/sys/class/net/{bus_name}'
        if not os.path.exists(sys_name):
            raise FileNotFoundError(f'Cannot find {sys_name}')
        _log.debug(f'Using CANbus {bus_name}')
        self._bus = can.Bus(bus_name, bustype='socketcan')
    
    def _listen(self):
        """Loops checking for incoming requests on the CANbus."""
        while True:
            if self._bus is None:
                continue
            received = self._bus.recv(timeout=self.timeout)
            if received:
                _log.debug(f'CANbus received: {received.data}')
                try:
                    decoded = self._db.decode_message(received.arbitration_id,
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
        """Sends a response message on the CANbus."""
        if not isinstance(message, can.Message):
            raise ValueError('Invalid CAN Message')
        _log.debug(f'Sending raw CAN data: {message.data}')
        self._bus.send(message)
        
    def _process_request(self, request):
        """Parses a request and generates a response."""
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
            data = self._obd_msg.encode(response)
            message = can.Message(arbitration_id=self._obd_msg.frame_id,
                                  data=data)
            self.send_response(message)
        else:
            _log.warning(f'No response for {request}')


def pids_a_supported() -> int:
    """Generates the bitmask for a response to supported pids 0x01-0x20
    
    Returns:
        Integer of the 32-bit bitmask.
        
    """
    supported_signals = ['RPM', 'SPEED']
    bitmask = 0
    for sig in supported_signals:
        pid = ObdSignal.get_pid_by_name(sig)
        bitmask = bitmask | 1 << (32 - pid)
    return bitmask
