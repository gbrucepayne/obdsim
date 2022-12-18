#!/bin/bash
# Creates or destroys a virtual CAN interface on a Linux host
echo "Parameters: $1"
IFNAME="vcan0"
[ -z "$1" ] && IFNAME="$1"
sudo modprobe vcan
sudo ip link add dev "${IFNAME}" type vcan
sudo ip link set "${IFNAME}" up
