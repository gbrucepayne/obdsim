# obdsim

This project is intended to provide a basic simulation for interacting with
a low cost Bluetooth OBD2 reader without needing to connect to a vehicle. It
is limited to the CANbus OBD2 transport.

A sender connects to an ELM327-based scanner tool using Bluetooth to query
various OBD codes using serial AT commands via the
[`python-obd`](https://github.com/brendan-w/python-OBD) module.

>For utility I bought the low cost TONWON BLE 4.0 adapter since it works with
both iPhone and Android apps.

>:warning: Beware of wireless OBD adapters as a potential cyber attack surface.
For example see [this paper](https://www.usenix.org/system/files/sec20summer_wen_prepub.pdf).

A listener runs on a physical or virtual CAN interface that processes incoming
requests and generates simulated responses. The physical CAN interface uses a
HAT for the Raspberry Pi.

This must run on a Linux host (typically Raspberry Pi).
The following packages help:
* `can-utils`
* `bluetooth-dev`

## Equipment Used

* Raspberry Pi Zero 2 W
* Waveshare [RS485 CAN HAT](https://www.waveshare.com/rs485-can-hat.htm)
* [TONWON Pro BLE4.0 ODBII Scanner](https://www.obdsoftware.net/scantools/product/3)
* 12V DC power supply, with breadboard termination
* OBD2 Diagnostic Cable breakout
* Mini breadboard
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