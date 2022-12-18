import can
import os
import logging
import threading

from cantools.database import Database, Message
from cantools.database import load_file as load_dbc

DBC_FILE = os.getenv('DBC_FILE', './dbc/CSS-Electronics-OBD2-v1.4.1.dbc')
DBC_MSG_NAME = os.getenv('DBC_MSG_NAME', 'OBD2')

_log = logging.getLogger(__name__)


def _get_message(msg):
    return msg


class CanBus(object):

    RX_SDO = 0x600
    TX_SDO = 0x580
    RX_PDO = 0x200
    TX_PDO = 0x180

    id_unit_a = [120, 121, 122, 123]
    id_unit_b = [124, 125, 126, 127]

    def __init__(self,
                 channel: str = 'can0',
                 bustype: str = 'socketcan',
                 log: bool = False):
        if not os.path.exists(f'/sys/class/net/{channel}'):
            raise ValueError(f'Cannot find channel {channel}')
        _log.info(f'Initializing CANbus: {channel}')
        self.bus = can.Bus(channel=channel, bustype=bustype)
        self.buffer = can.BufferedReader()
        self.notifier = can.Notifier(self.bus, [_get_message, self.buffer])
        self.db: Database = load_dbc(DBC_FILE)
        self.obd: Message = self.db.get_message_by_name(DBC_MSG_NAME)
        self.logging_thread = threading.Thread(target=self._logger, daemon=True)
        if log:
            self.logging_thread.start()

    def _logger(self):
        while True:
            msg = self.buffer.get_message()
            if msg:
                _log.info(f'Received on CANbus: {msg}')
                
    def send_message(self, message):
        try:
            self.bus.send(message)
            return True
        except can.CanError:
            _log.error("message not sent!")
            return False

    def read_input(self, id):
        msg = can.Message(arbitration_id=self.RX_PDO + id,
                          data=[0x00],
                          is_extended_id=False)
        self.send_message(msg)
        return self.buffer.get_message()

    def flush_buffer(self):
        msg = self.buffer.get_message()
        while (msg is not None):
            msg = self.buffer.get_message()

    def cleanup(self):
        self.notifier.stop()
        self.bus.shutdown()

    def disable_update(self):
        for i in [50, 51, 52, 53]:
            msg = can.Message(arbitration_id=0x600 + i,
                              data=[0x23, 0xEA, 0x5F, 0x00, 0x00, 0x00, 0x00, 0x00],
                              is_extended_id=False)
            self.send_message(msg)
