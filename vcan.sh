#!/bin/bash
# Creates a virtual CAN interface on a Linux host

sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 up
