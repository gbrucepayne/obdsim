from obdsim.scanner import ObdScanner
from obdsim.obdsignal import decode_pids_supported, encode_pids_supported


def test_pids_supported_codec():
    scanner = ObdScanner()
    # Response from F150 2014 using Elm 327 v1.5 command `0100`
    # ELM headers enabled to get transmitter / arbitration ID (7E8 prefix)
    # ELM response excludes unused 8th byte so we pad with an arbitrary byte
    elm_response = '7E8064100BF9FA893\r'
    pad_byte_8 = '00'
    response_arbitration_id = int(elm_response[:3], 16)
    response_data = bytes.fromhex(elm_response.strip()[3:] + pad_byte_8)
    expected_pids = [1, 2, 5, 8, 12, 14, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27,
                     28, 29, 30, 32]
    decoded = scanner._db.decode_message(response_arbitration_id,
                                         response_data)
    mode = decoded['service'].value
    pid = decoded[f'PID_S{mode}'].value
    value = decoded['PIDS_A']
    assert mode == 1
    assert pid == 0
    assert value == 3214911635
    supported_pids = decode_pids_supported(mode, pid, value)
    assert supported_pids == { 1: expected_pids }
    bm = encode_pids_supported(0, supported_pids[1])
    assert bm == value


def test_vin_codec():
    scanner = ObdScanner()
    # Response from F150 2014 using Elm 327 v1.5 command `0902`
    # ELM headers enabled to get transmitter / arbitration ID (7E8 prefix)
    # ELM response excludes unused 8th byte so we pad with an arbitrary byte
    elm_response = '7E81014490201314654\r7E82146573145465845\r7E82246423334343739\r'
    response_parts = elm_response.split('\r')
    for i, part in enumerate(response_parts):
        response_arbitration_id = int(part[:3], 16)
        response_data = bytearray(bytes.fromhex(part.strip()[3:]))
        pad = bytearray()
        for p in range(0, 8 - len(response_data)):
            pad.append(b'\x00')
        assert False, 'VIN parsing not implemented'


if __name__ == '__main__':
    # test_pids_supported_codec()
    test_vin_codec()
