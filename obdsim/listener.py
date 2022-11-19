from time import sleep

from can.interface import Bus as CanBus


def obd_listen(canbus: CanBus, callback = None):
    while True:
        received = canbus.recv(timeout=0.1)
        if received:
            print(f'Received: {received.data}')
            if callable(callback):
                callback(received)
        else:
            sleep(0.1)
