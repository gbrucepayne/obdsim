# obdsim

This project is intended to provide a basic simulation for interacting with
a low cost Bluetooth OBDII reader without needing to connect to a vehicle. It
is limited to the CANbus OBDII transport.

A listener is run on a physical or virtual CAN interface that processes incoming
requests and ignores responses. It passes requests to a sender that generates
a response for supported requests.

This must run on a Linux host (typically Raspberry Pi).
The following packages help:
* `can-utils`

## Equipment Used

* Raspberry Pi Zero 2 W
* Waveshare [RS485 CAN HAT](https://www.waveshare.com/rs485-can-hat.htm)
* TONWON ODBII Scan Tool - iOS and Android compatible
* 12V DC power supply, with breadboard termination
* OBD2 Diagnostic Cable breakout
* Mini breadboard
* 120&Omega; resistor(s)
* Various breadboard jumper wires

## Reverse Engineering Process

The first step was to use the available libraries to parse an existing OBDII
database file, which is available courtesy of CSS Electonics. Some basic
manipulation using examples from the `cantools` repository allowed me to create
a sample response starting with vehicle speed.
>:warning: Not sure if the padded values from a given vehicle will be zeros or
ones or something else (e.g. `0xAA`) - this will come from connecting to a real
vehicle and monitoring via Bluetooth which is a separate project.

I assume the OBDII reader sends various requests and that the OBD2 communication
model is primarily request/response (rather than broadcast by each ECM).

### Diagnostic Cable

Using a OBD2 connector specification and a multimeter I mapped and labeled
the relevant wires to connect to a breadboard:
|Pin|Function|
|---|---|
|16|12V DC input|
|4|Ground|
|5|Ground|
|6|CAN-H (ISO15765-4)|
|14|CAN-L (ISO15765-4)|

## References

Many thanks to the great resources and open source elements of the following:

* [CSS Electronics](https://csselectonics.com) have some fantasic resources and
for commercial projects you should consider using their products and services.
* [Collection of CAN packages and tools](https://gist.github.com/jackm/f33d6e3a023bfcc680ec3bfa7076e696)