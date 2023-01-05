import atexit
import logging
import socket
import time
from enum import IntEnum
from socket import socket as Socket

import serial

AUTO_BAUD = [38400, 9600]

_log = logging.getLogger(__name__)
TEST_MODE = True


class ElmStatus(IntEnum):
    NOT_CONNECTED = 0
    ELM_CONNECTED = 1
    OBD_CONNECTED = 2
    CAR_CONNECTED = 3


class ElmProtocol(IntEnum):
    AUTO = 0
    SAE_J1850_PWM = 1
    SAE_J1850_VPW = 2
    ISO_9141_2 = 3
    ISO_14230_4_KWP = 4
    ISO_14230_4_KWP_FAST = 5
    ISO_15765_4_11_500 = 6
    ISO_15765_4_29_500 = 7
    ISO_15765_4_11_250 = 8
    ISO_15765_4_29_250 = 9
    SAE_J1939_29_250 = 10
    USER_1 = 11
    USER_2 = 12


class ObdResponseFormat(IntEnum):
    RAW_BYTES = 0
    HEX_STRING = 1
    OBJECT = 2


class Elm327:
    PROMPT = '>'
    TERMINATOR = '\r'
    def __init__(self, **kwargs) -> None:
        """Instantiate an ELM327-based device.
        
        Args:
            bluetooth (tuple): A tuple with (<mac> (str), <channel> (int)) if
                not using serial.
            serial_name (str): The name of the serial port if not using
                bluetooth.
                
        """
        if 'bluetooth' in kwargs:
            if 'serial_name' in kwargs:
                raise ValueError('Use exclusively bluetooth or serial_name')
            self._connection = Socket(socket.AF_BLUETOOTH,
                                      socket.SOCK_STREAM,
                                      socket.BTPROTO_RFCOMM)
            self._connection.settimeout(kwargs.get('timeout', 10))
            self._connection_kwargs = { 'bluetooth': kwargs.pop('bluetooth')}
        elif 'serial_name' in kwargs:
            self._connection: serial.Serial = None
            self._connection_kwargs = { 'port': kwargs.pop('serial_name') }
            serial_kwargs = []
            self._parse_kwargs(kwargs, self._connection_kwargs, serial_kwargs)
            if 'timeout' not in self._connection_kwargs:
                self._connection_kwargs['timeout'] = 0
        else:
            raise ValueError('Missing bluetooth or serial_name')
        self._elm_kwargs = {}
        elm_kwargs = ['protocol']
        self._parse_kwargs(kwargs, self._elm_kwargs, elm_kwargs)
        atexit.register(self.disconnect)
        self._version = None
        self._low_power: bool = None
        self._initialized = False
        self._timeout_count: int = 0
        self._max_timeouts = int(kwargs.get('max_timeouts', 3))
        self._protocol_confirmed = None
    
    def _parse_kwargs(self,
                      src_kwargs: dict,
                      dst_kwargs: dict,
                      filter: 'list[str]') -> None:
        for kwarg in src_kwargs:
            if kwarg in filter:
                dst_kwargs[kwarg] = src_kwargs.get(kwarg)
        for kwarg in dst_kwargs:
            src_kwargs.pop(kwarg)
        
    def connect(self):
        if isinstance(self._connection, Socket):
            try:
                self._connection.connect(self._connection_kwargs['bluetooth'])
                return
            except (OSError) as err:
                if isinstance(err, OSError) and err.errno != 115:
                    if err.errno == 52:
                        _log.error('Suspected Bluetooth PIN code error')
                    raise err
        else:
            auto_baud = False
            if 'baudrate' in self._connection_kwargs:
                if self._connection_kwargs['baudrate'] == 'auto':
                    self._connection_kwargs.pop('baudrate')
                    auto_baud = True
            self._connection = serial.Serial(**self._connection_kwargs)
            if auto_baud:
                self._auto_baudrate(self._connection_kwargs['baudrate'])
    
    def disconnect(self):
        try:
            self._connection.close()
        except Exception as err:
            _log.error(f'Error closing connection: {err}')
        
    def _auto_baudrate(self):
        if not isinstance(self._connection, serial.Serial):
            raise ConnectionError('Connection is not a serial instance')
        _log.debug('Attempting to detect serial baud rate...')
        # old_write_timeout = self._connection.write_timeout
        # old_read_timeout = self._connection.timeout
        # self._connection.write_timeout = 0.1
        # self._connection.timeout = 0.1
        auto_baudrate = None
        for baud in AUTO_BAUD:
            self._connection.baudrate = baud
            self._connection.reset_input_buffer()
            self._connection.reset_output_buffer()
            self._connection.write(b'ATZ\r')
            res = self._connection.read(1024)
            if res.endswith(self.PROMPT.encode()):
                auto_baudrate = baud
                _log.debug(f'Using baudrate {auto_baudrate}')
                break
        # self._connection.write_timeout = old_write_timeout
        # self._connection.timeout = old_read_timeout
        if not auto_baudrate:
            raise ConnectionError('Failed to determine serial baud rate')
    
    def flush(self) -> None:
        if isinstance(self._connection, Socket):
            timeout = self._connection.timeout
            self._connection.settimeout(0.5)
            try:
                flushed = self._connection.recv(1024)
            except (socket.timeout, TimeoutError) as err:
                pass
            self._connection.settimeout(timeout)
        else:
            self._connection.reset_input_buffer()
            self._connection.reset_output_buffer()
        
    def get_response(self,
                     data: str,
                     timeout: float = 1,
                     remove_echo: bool = True,
                     remove_prompt: bool = True) -> 'list[str]':
        """Sends the data and returns the decoded response(s).
        
        Args:
            data: The command or query to send.
            timeout: The time to wait after sending data, in seconds.
        
        Returns:
            A list of non-empty strings.
            
        """
        if not data.startswith('AT'):
            _log.debug(f'Transmitting on OBD2: {data}')
        self.flush()
        to_send = f'{data}{self.TERMINATOR}'.encode('utf-8')
        if isinstance(self._connection, Socket):
            self._connection.sendall(to_send)
        else:
            self._connection.write(to_send)
        send_time = time.time()
        read = bytearray(b'')
        while not read.endswith(self.PROMPT.encode()):
            if time.time() - send_time > timeout and not TEST_MODE:
                raise TimeoutError(f'{data} Timed out waiting for response')
            try:
                if isinstance(self._connection, Socket):
                    read.extend(self._connection.recv(1024))
                else:
                    read.extend(self._connection.read(1024))
            except (socket.timeout, TimeoutError):
                time.sleep(0.1)
        recv_time = time.time()
        _log.debug(f'{data} round-trip: {round(recv_time - send_time)} seconds')
        received = read.decode('utf-8', 'backslashreplace')
        response = [r.strip() for r in received.split('\r') if r.strip()]
        if response[0] == data:
            if remove_echo:
                response.remove(data)
        if response[-1] == self.PROMPT:
            if remove_prompt:
                response.remove(self.PROMPT)
        else:
            _log.warning(f'No prompt received after command {data}')
            self._timeout_count += 1
            if self._timeout_count > self._max_timeouts:
                self._handle_disconnect()
        return response
    
    def _handle_disconnect(self):
        _log.warning('Not implemented')
        self._initialized = False
        self._protocol_confirmed = None
        self._timeout_count = 0
        
    def initialize(self,
                   attempts: int = 0,
                   max_attempts: int = 3,
                   protocol: ElmProtocol = None,
                   auto_protocol: bool = True):
        """Initializes the ELM device.
        
        Args:
            attempts: Only used if retrying due to non-response.
            max_attempts: Optional threshold for failing after non-response.
            protocol: Optional specify protocol to be used, uses AUTO if None.
            auto_protocol: Optional, set False to override automatic fallback.
        
        Raises:
            `ConnectionError` if no response from ELM device after max_attempts.
            
        """
        _log.info('Initializing ELM device...')
        if attempts >= max_attempts:
            raise ConnectionError('No response from ELM')
        reset = self.get_response('ATZ', remove_prompt=False)
        if '>' not in reset:
            attempts += 1
            _log.warning('Invalid response from ELM reset - retrying...')
            time.sleep(1)
            self.initialize(attempts=attempts)
        for s in reset:
            if s.startswith('ELM'):
                self._version = s
                break
        if not protocol:
            protocol = self._elm_kwargs.get('protocol', ElmProtocol.AUTO)
        settings = {
            'echo_off': 'ATE0',
            'headers_off': 'ATH0',
            'linefeed_off': 'ATL0',
            'adaptive_timing': 'ATAT1',
            'protocol': f'ATSPA{protocol.value}',
        }
        for tag, command in settings.items():
            if tag == 'protocol' and protocol.value > ElmProtocol.AUTO:
                _log.info(f'Using protocol {protocol.name}')
                if auto_protocol is False:
                    command = command.replace('PA', 'P')
            res = self.get_response(command)
            if 'OK' not in res:
                _log.warning(f'{tag} unexpected {command} response: {res}')
        self._initialized = True
        _log.debug(f'{self._version} initialized')
        
    @property
    def initialized(self) -> bool:
        return self._initialized
    
    @property
    def version(self) -> str:
        return self._version
    
    @property
    def voltage(self) -> float:
        res = self.get_response('ATRV')
        try:
            return float(res[0].lower().replace('v', ''))
        except ValueError as err:
            _log.error(f'Unexpected response from ATRV: {res}')
            return None
    
    @property
    def protocol(self) -> ElmProtocol:
        if self._protocol_confirmed is not None:
            return self._protocol_confirmed
        protocol = self.get_response('ATDPN')
        try:
            protocol_number = int(protocol[0].lower().replace('a', ''))
            return ElmProtocol(protocol_number)
        except ValueError as err:
            _log.error(f'Unexpected response from ATDPN: {protocol}')
            return None
    
    @property
    def status(self) -> ElmStatus:
        if self._protocol_confirmed is None:
            _log.info('Attempting to detect vehicle protocol...')
            pids_a = self.get_response('0100', timeout=10, remove_prompt=False)
            if 'UNABLE TO CONNECT' not in pids_a:
                self._protocol_confirmed = self.protocol
                return ElmStatus.CAR_CONNECTED
            return ElmStatus.OBD_CONNECTED
        protocol = self.protocol
        if protocol > 0:
            return ElmStatus.CAR_CONNECTED
        if self.voltage and self.voltage > 6:
            return ElmStatus.OBD_CONNECTED
        if self.initialized:
            return ElmStatus.ELM_CONNECTED
        return ElmStatus.NOT_CONNECTED
    
    def query_pid(self,
                  pid: int,
                  mode: int = 1,
                  format: ObdResponseFormat = ObdResponseFormat.RAW_BYTES,
                  ) -> 'bytes|str|object':
        """Gets the value of the PID requested.
        
        Args:
            pid: The PID number (0..255)
            mode: The Mode/service (0..9), defaults to Mode 1
            ascii_hex: If True will return a hex string
        
        Returns:
            A set of bytes or the hex string equivalent.
            
        Raises:
            `ConnectionError` if no vehicle connection is present.
            
        """
        if not self.status == ElmStatus.CAR_CONNECTED:
            raise ConnectionError('Vehicle is not connected')
        if mode not in range(0,2):
            raise ValueError(f'Unsupported Mode: {mode}')
        if pid not in range(0,256):
            raise ValueError(f'Invalid PID: {pid}')
        res = self.get_response(f'{mode:02x}{pid:02x}')
        if 'NO DATA' in res:
            raise ConnectionError('ELM timeout indicates NO DATA')
        if 'SEARCHING...' in res:
            res.remove('SEARCHING...')
        if 'UNABLE TO CONNECT' in res:
            _log.warning('Unable to connect')
            raise ConnectionError('Vehicle is not connected')
        data = res[0].replace(' ', '')
        if format == ObdResponseFormat.HEX_STRING:
            return data
        elif format == ObdResponseFormat.RAW_BYTES:
            return bytes.fromhex(data)
        else:
            raise NotImplementedError
