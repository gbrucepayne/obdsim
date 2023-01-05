import logging
import os
import sys

sys.path.append(f'{os.getcwd()}')

from obdsim.simulator import ObdSimulator

VEHICLE_BUS = os.getenv('VEHICLE_BUS', 'can0')

format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
              '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(format_csv)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def main():
    try:
        vehicle = ObdSimulator(VEHICLE_BUS)
        vehicle.connect()
        vehicle.start()
    except Exception as err:
        logger.exception(err)


if __name__ == '__main__':
    main()
