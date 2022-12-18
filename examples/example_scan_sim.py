import logging
import os
import sys

sys.path.append(f'{os.getcwd()}')

from obdsim import scanner, simulator

format_csv = ('%(asctime)s.%(msecs)03dZ,[%(levelname)s],(%(threadName)s)'
              '%(module)s.%(funcName)s:%(lineno)d, %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter(format_csv)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def main():
    vehicle = simulator.ObdSimulator()
    vehicle.connect()
    vehicle.start()
    app = scanner.CanScanner()
    app.connect()
    app.start()


if __name__ == '__main__':
    main()
