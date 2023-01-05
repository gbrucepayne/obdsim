"""A basic vehicle simulator generating responses to supported OBD2 queries."""
import logging
import os
import threading
import time

import can
from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

from . import ObdSignal

DBC_FILE = os.getenv('DBC_FILE', './dbc/python-obd.dbc')
DBC_REQUEST = os.getenv('DBC_REQUEST', 'OBD2_REQUEST')
DBC_RESPONSE = os.getenv('DBC_RESPONSE', 'OBD2_RESPONSE')

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
                 dbc_filename: str = DBC_FILE,
                 dbc_request: str = DBC_REQUEST,
                 dbc_response: str = DBC_RESPONSE,
                 timeout: float = 0.1,
                 ) -> None:
        """Instantiates the class.
        
        Args:
            canbus_name (str): The name of the CAN bus interface e.g. `can0`.
                Optional, can be specified with connect method.
            dbc_filename: The file path/name of the DBC to be used.
                Can be set using environment variable `DBC_FILE`.
                Defaults to `./dbc/python-obd.dbc`
            dbc_request: The name of the request message set in the `BO_`
                definition within the DBC file.
            dbc_response: The name of the response message set in the `BO_`
                definition within the DBC file.
            timeout: The bus timeout in seconds.
        """
        self._db: CanDatabase = load_can_database(dbc_filename)
        self._obd_req: CanMessage = self._db.get_message_by_name(dbc_request)
        self._obd_res: CanMessage = self._db.get_message_by_name(dbc_response)
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
        _log.info(f'Listening on {self._bus_name}...')
        while True:
            received = self._bus.recv(timeout=self.timeout)
            if received:
                _log.info(f'CANbus received: {received.data}')
                try:
                    decoded = self._db.decode_message(received.arbitration_id,
                                                      received.data)
                    _log.info(f'Decoded: {decoded}')
                    if 'request' in decoded:
                        extended_id = received.arbitration_id >= 2**11
                        self._process_request(decoded, extended_id)
                    else:
                        _log.debug(f'Ignoring message: {decoded}')
                except KeyError:
                    _log.error(f'Error decoding CAN message: {received}')
    
    def _process_request(self, request, extended_id: bool = None):
        """Parses a request and generates a response."""
        # request = {
        #     'length': 3,
        #     'request': 0,
        #     'service': 1,   # mode
        #     'PID': 13,   # pid (decimal)
        #     'SPEED': 50,   # derived from DBC
        # }
        _log.info(f'Processing {request}')
        response = None
        if 'service' not in request:
            raise ValueError('OBD request or db missing mode')
        if request['service'] == 1:
            _log.debug(f'Simulating mode 1 response')
            if 'PID' not in request:
                raise ValueError('Missing PID for Mode 1')
            pid = request['PID']
            response = {
                'response': 4,
                'service': 1,
                'PID': pid,
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
            _log.info(f'Simulating response: {response}')
            data = self._obd_res.encode(response)
            if extended_id is None:
                extended_id = self._obd_res.frame_id < 2**11
            else:
                _log.info(f'Simulator forcing extended ID: {extended_id}')
            message = can.Message(arbitration_id=self._obd_res.frame_id,
                                  is_extended_id=extended_id,
                                  data=data)
            self.send_response(message)
        else:
            _log.warning(f'No response for {request}')

    def send_response(self, message: can.Message):
        """Sends a response message on the CANbus."""
        if not isinstance(message, can.Message):
            raise ValueError('Invalid CAN Message')
        _log.info(f'Sending raw CAN data: {message}')
        self._bus.send(message)
        

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
