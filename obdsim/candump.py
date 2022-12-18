from cantools import logreader, database
from cantools.subparsers.__utils__ import format_message_by_frame_id

# The signals ParameterID_Service02 and ParameterID_Service01 are overlapping in message OBD2_REQ

def convert_candump(logfile: str):
    """Converts candump output to bytes.
    
    Format is n#n
    
    """
    db = database.load_file('./dbc/CSS-Electronics-OBD2-v1.4.dbc')
    db_ext = database.load_file('./dbc/CSS-Electronics-OBD2-Extended-v1.4.dbc')
    with open(logfile) as fd: #doctest: +SKIP
        parser = logreader.Parser(fd)
        count = 0
        for line, frame in parser.iterlines(keep_unknowns=True):
            if frame is not None:
                count += 1
                if frame.frame_id < 2**11:
                    dbase = db
                else:
                    dbase = db_ext
                decoded = format_message_by_frame_id(dbase,
                                                     frame.frame_id,
                                                     frame.data,
                                                     decode_choices=False,
                                                     single_line=True,
                                                     decode_containers=False)
                decoded = decoded.strip()
                if decoded.startswith('Unknown'):
                    decoded += f' data: 0x{frame.data.hex()}'
                print(f'Frame {count}: {decoded}')


if __name__ == '__main__':
    convert_candump('./tests/candump/can0.log')
