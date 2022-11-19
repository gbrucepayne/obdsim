import os
from pprint import pprint

import can
import cantools
from cantools.database.can.database import Database as CanDatabase

db: CanDatabase = cantools.database.load_file('./dbc/CSS-Electronics-OBD2-v1.3.dbc')
obd_message = db.get_message_by_name('OBD2')
# for signal in obd_message.signals:
#     print(f'{signal.name}: length={signal.length}')
#     if signal.choices:
#         pprint(signal.choices, indent=2)
can_bus = None
if os.path.exists('/sys/class/net/vcan0'):
    print('Using virtual CAN')
    can_bus = can.interface.Bus('vcan0', bustype='socketcan')
content = {
    'length': 3,
    'response': 4,
    'service': 1,
    'ParameterID_Service01': 13,
    'S1_PID_0D_VehicleSpeed': 50,
}
data = obd_message.encode(content)
message = can.Message(arbitration_id=obd_message.frame_id, data=data)
print(f'ODB2 raw data: {message.data}')
print(f'Decoded: {db.decode_message(message.arbitration_id, message.data)}')
if can_bus:
    can_bus.send(message)
    # received = can_bus.recv()
    # pprint(db.decode_message(received.arbitration_id, received.data))
