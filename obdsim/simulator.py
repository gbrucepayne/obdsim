"""A basic vehicle simulator generating responses to supported OBD2 queries."""
import logging
import os
import threading

import can
from cantools.database import Database as CanDatabase
from cantools.database import Message as CanMessage
from cantools.database import load_file as load_can_database

from obdsim.obdsignal import ObdSignal, ObdSupportedPids

DBC_FILE = os.getenv('DBC_FILE', './dbc/python-obd.dbc')
DBC_REQUEST = os.getenv('DBC_REQUEST', 'OBD2_REQUEST')
DBC_RESPONSE = os.getenv('DBC_RESPONSE', 'OBD2_ECU_RESPONSE')
SIMULATOR_VIN = os.getenv('SIMULATOR_VIN', '1OBDIISIMULATORXX')

SIMULATED_SIGNALS = {
    'S1_PIDS_01_20': None,
    'S1_PIDS_21_40': None,
    'S1_PIDS_41_60': None,
    'S1_PIDS_61_80': None,
    'S1_PIDS_81_A0': None,
    'S1_PIDS_A1_C0': None,
    'S1_PIDS_C1_E0': None,
    'ENGINE_SPEED': 0,
    'VEHICLE_SPEED': 0,
    'OIL_TEMP': 20 + 40,
    'S9_PIDS_01_20': None,
    'VIN_MCOUNT': 3,
    'VIN': SIMULATOR_VIN,
}

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
                _log.debug(f'CANbus received: {received.data}')
                try:
                    decoded = self._db.decode_message(received.arbitration_id,
                                                      received.data)
                    _log.debug(f'Decoded: {decoded}')
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
        #     'length': 2,   # number of bytes in request or response
        #     'request': 0,   # first 4 bits of Mode indicating direction
        #     'service': 1,   # mode mux defined in DBC
        #     'PID_S1': 13,   # PID mux defined in DBC
        #     'SPEED': 50,   # derived from DBC
        # }
        _log.info(f'Processing {request}')
        if 'service' not in request:
            raise ValueError('OBD request or db missing mode')
        service_mode = request['service']
        pid_mux = f'PID_S{service_mode:01x}'
        if pid_mux not in request:
            raise ValueError(f'Missing PID value for {pid_mux}')
        pid = request[pid_mux]
        response = {
            'response': 4,
            'service': service_mode,
            pid_mux: pid,
        }
        response = self.sim_response(service_mode, pid, response)
        if response is None:
            return
        if 'length' not in response:
            _log.warning(f'No simulation for mode {service_mode} PID {pid}')
        else:
            _log.info(f'Simulating response: {response}')
            data = self._obd_res.encode(response)
            self.send_response_data(data, extended_id)

    def send_response_data(self, data: bytes, extended_id: bool = None):
        """Sends a response message on the CANbus."""
        if extended_id is None:
            extended_id = self._obd_res.frame_id >= 2**11
        message = can.Message(arbitration_id=self._obd_res.frame_id,
                              is_extended_id=extended_id,
                              data=data)
        _log.debug(f'Sending raw CAN data: {message}')
        self._bus.send(message)
        
    def pids_supported(self, pid: int, mode: int = 1) -> int:
        """Generates the bitmask for a response to supported pids 0x01-0x20
        
        Returns:
            Integer of the 32-bit bitmask.
            
        """
        supported = []
        for sim in SIMULATED_SIGNALS:
            candidate_pid = ObdSignal.get_pid_by_name(sim, mode)
            if candidate_pid and candidate_pid in range(pid + 1, pid + 32 + 1):
                supported.append(candidate_pid)
        o = ObdSupportedPids(mode, pid)
        o.pids = supported
        return o.value

    def sim_response(self, mode: int, pid: int, response: dict) -> 'dict|None':
        """Populates the response dictionary"""
        pid_name = ObdSignal.get_name_by_pid(pid, mode)
        if pid_name not in SIMULATED_SIGNALS:
            _log.warning(f'Unsupported mode {mode} pid {pid}')
            return
        if pid_name not in self.signals or self.signals[pid_name] is None:
            if '_PIDS_' in pid_name:
                self.signals[pid_name] = self.pids_supported(pid, mode)
            else:
                self.signals[pid_name] = SIMULATED_SIGNALS[pid_name]
        if pid_name.endswith('VIN'):
            self.sim_vin()
            return None
        signal = ObdSignal(mode, pid, self.signals[pid_name])
        response['length'] = signal.length
        response[pid_name] = signal.value_raw
        return response
        
    def sim_vin(self, extended_id: bool = None):
        if len(SIMULATOR_VIN) != 17:
            _log.warning(f'Invalid VIN {SIMULATOR_VIN}')
        vin_parts = (
            SIMULATOR_VIN[:3],
            SIMULATOR_VIN[3:10],
            SIMULATOR_VIN[10:17]
        )
        for i, part in enumerate(vin_parts):
            if i == 0:
                data_hex = '1014490201'
            else:
                data_hex = f'{20 + i}'
            for c in part:
                data_hex += f'{ord(c):02x}'.upper()
            data = bytes.fromhex(data_hex)
            _log.debug(f'Sending VIN part {i + 1} of {len(vin_parts)}')
            self.send_response_data(data, extended_id)
