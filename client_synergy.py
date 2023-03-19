#!/usr/bin/env python3

import socket
import time
import struct

# First message from server (Synergy 1.6):
# b'\x00\x00\x00\x0bSynergy\x00\x01\x00\x06'

def test_parser():
    protocol = Protocol()
    msg = b'Synergy\x00\x01\x00\x06'
    print(protocol._parse(ProtocolMsg.kMsgHello, msg))
    msg = b'DSOP\x00\x00\x00\x02CLPS\x00\x00\x00\x01'
    print(protocol._parse(ProtocolMsg.kMsgDSetOptions, msg))

def main():

    host = socket.gethostname()
    # host = '192.168.162.201'
    port = 24800
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    stream = Stream(sock)
    protocol = Protocol()

    handler = MessageHandler(stream, protocol)

    try:
        while True:
            msg = stream.read()
            if msg is None: continue

            print('From server:', msg)
            # [msg_name, *msg_args] 
            msg_info = protocol.parse(msg)
            print('            ', msg_info)
            
            response = handler.handle(msg_info)


            if response == None: continue

            print('To   server:', response)
            stream.send(response)
    finally:
        stream.close()


################################################

class MessageHandler:
    """A class to handle (normally by responding to) various received synergy messages
    Message handler methods are found automatically by name
    'on_' + msg_name[4:].lower()
    So that 'kMsgHello' message is handled by 'on_hello' method
    """
    def __init__(self, stream, protocol):
        self.stream   = stream
        self.protocol = protocol

    def get_handler(self, msg_name):
        """See class documentation for details on method_name
        """
        method_name = 'on_' + msg_name[4:].lower()
        try:
            return self.__getattribute__(method_name)
        except AttributeError:
            raise KeyError('Could not find handler for', msg_name)

    def handle(self, msg_info):
        msg_name = msg_info[0]
        method = self.get_handler(msg_name)
        return method(msg_info)

    def on_hello(self, msg_info):
        # Expected message: b'Synergy\x00\x01\x00\x06'
        ver_maj, ver_min = msg_info[1:]
        print(f'Connected to server v{ver_maj}.{ver_min}')
        return self.protocol.format(ProtocolMsg.kMsgHelloBack, 1, 6, 'tablet')
    def on_ckeepalive(self, msg_info):
        # Keepalive packet
        return self.protocol.format(ProtocolMsg.kMsgCKeepAlive)
    def on_qinfo(self, msg_info):
        print(f'Informing about display info')
        values = [
          0,     # leftmost pixel x
          0,     # topmost pixel y
          1920,  # width
          1080,  # height
          0,     # obsolete
          0,     # mouse_x
          0,     # mouse_y
        ]
        return self.protocol.format(ProtocolMsg.kMsgDInfo, *values)
    def on_cinfoack(self, msg_info):
        # Just a response to kMsgDInfo
        pass
    def on_cresetoptions(self, msg_info):
        print('TODO: reset options to defaults')
    def on_dsetoptions(self, msg_info):
        print('TODO: set options')
        continue

################################################

class Stream:
    def __init__(self, sock):
        """
        @param sock  Socket for the connection to synergy server
        """
        self.sock = sock
    def read(self):
        # Packet size is sent as big-endian int
        size = self.sock.recv(4)
        if len(size) == 0: return None
        size = struct.unpack('>i', size)[0]
        #
        data = self.sock.recv(size)
        return data
    def send(self, data):
        # Packet size is sent as big-endian int
        size = len(data)
        size = struct.pack('>i', size)
        #
        print(size + data)
        self.sock.sendall(size + data)

    def close(self):
        self.sock.close()

class Protocol:
    """The class to parse and generate messages supported by Synergy v1.11 protocol
    """
    def __init__(self):
        self.msg_types = {
            msg_name : msg_fmt for msg_name, msg_fmt in vars(ProtocolMsg).items()
            if msg_name.startswith('kMsg')
        }
    def __read_int(self, buf):
        ret = 0
        while buf[0] in '0123456789':
            ret = ret * 10 + int(buf[0])
            buf = buf[1:]
            if len(buf) == 0: return (None, None)
        return (ret, buf)

    def __unpack_int(self, buf, width):
        """Unpack big-endian integer of specified width
        """
        if width == 1: struct_fmt = '>b'
        if width == 2: struct_fmt = '>h'
        if width == 4: struct_fmt = '>i'
        val_buf = buf[:width]
        buf     = buf[width:]
        val = struct.unpack(struct_fmt, val_buf)[0]
        return (val, buf)

    def parse(self, msg_bytes):
        """Parse message bytes to determine the received Synergy message.
        """
        for msg_name, msg_fmt in self.msg_types.items():
            # First 4 bytes always serve as a message identifier
            msg_identifier = msg_fmt[:4].encode('ascii')
            if msg_bytes[:4] != msg_identifier: continue

            return [msg_name] + self._parse(msg_fmt, msg_bytes)
        raise ValueError('Could not parse message', msg_bytes)

    def format(self, fmt, *args):
        """Generate synergy command
        @return message bytes
        """
        msg = b''
        while len(fmt) > 0:
            if fmt[0] == '%':
                fmt = fmt[1:]
                # if len(fmt) == 0: return None
                width, fmt = self.__read_int(fmt)
                # if width is None: return None
                # if len(fmt) == 0: return None
                fmt_id = fmt[0]
                fmt = fmt[1:]
                if   fmt_id == 'i':
                    if width == 0: raise ValueError('Width should be non-zero')
                    val  = args[0]
                    args = args[1:]
                    if width == 1: struct_fmt = '>b'
                    if width == 2: struct_fmt = '>h'
                    if width == 4: struct_fmt = '>i'
                    val_buf = struct.pack(struct_fmt, val)
                    msg += val_buf
                elif fmt_id == 's':
                    val  = args[0].encode('ascii')
                    args = args[1:]
                    strlen = struct.pack('>i', len(val))
                    msg += strlen
                    msg += val
                else:
                    raise KeyError('Format %s not supported' % fmt_id)
            else:
                msg += fmt[0].encode('ascii')
                fmt = fmt[1:]
        # while len(fmt) > 0:

        return msg
    def _parse(self, fmt, msg):
        """Basically simplified version of scanf,
        returns the list of scanned %i arguments
        """
        ret = []
        while len(fmt) > 0:
            if fmt[0] == '%':
                fmt = fmt[1:]
                # if len(fmt) == 0: return None
                width, fmt = self.__read_int(fmt)
                # if width is None: return None
                # if len(fmt) == 0: return None
                fmt_id = fmt[0]
                fmt = fmt[1:]
                if   fmt_id == 'i':
                    if width == 0: raise ValueError('Width should be non-zero')
                    val, msg = self.__unpack_int(msg, width)
                    # val_buf = msg[:width]
                    # msg     = msg[width:]
                    # if width == 1: struct_fmt = '>b'
                    # if width == 2: struct_fmt = '>h'
                    # if width == 4: struct_fmt = '>i'
                    # val = struct.unpack(struct_fmt, val_buf)[0]
                    ret.append(val)
                elif fmt_id == 'I':
                    if width == 0: raise ValueError('Width should be non-zero')
                    vec_vals     = []
                    vec_len, msg = self.__unpack_int(msg, 4)
                    for i in range(vec_len):
                        if i % 2 == 0:
                            val = msg[:4].decode('ascii')
                            msg = msg[4:]
                        else:
                            val, msg = self.__unpack_int(msg, 4)
                        vec_vals.append(val)
                    ret.append(vec_vals)
                elif fmt_id == 's':
                    strlen = msg[:4]
                    msg = msg[4:]
                    ret.append(msg[:strlen].decode('ascii'))
                    msg = msg[strlen:]
                else:
                    raise KeyError('Format %s not supported' % fmt_id)

            elif fmt[0] != chr(msg[0]):
                # If some plain character doesn't match, terminate processing
                return None
            else:
                fmt = fmt[1:]
                msg = msg[1:]

        return ret


class ProtocolMsg:
    # say hello to client;  primary -> secondary
    # $1 = protocol major version number supported by server.
    # $2 = protocol minor version number supported by server.
    # $3 = server keyboard layout list.
    kMsgHello                    = "Synergy%2i%2i";
    # respond to hello from server;  secondary -> primary
    # $1 = protocol major version number supported by client.
    # $2 = protocol minor version number supported by client.
    # $3 = client name.
    kMsgHelloBack                = "Synergy%2i%2i%s";
    # no operation;  secondary -> primary
    kMsgCNoop                    = "CNOP";
    # close connection;  primary -> secondary
    kMsgCClose                   = "CBYE";
    # enter screen:  primary -> secondary
    # entering screen at screen position
    # $1 = x,
    # $2 = y.  x,y are absolute screen coordinates.
    # $3 = sequence number, which is
    # used to order messages between screens. the secondary screen
    # must return this number with some messages.
    # $4 = modifier key mask.  this will have bits set for each
    # toggle modifier key that is activated on entry to the screen.
    # the secondary screen should adjust its toggle modifiers to reflect that state.
    kMsgCEnter                   = "CINN%2i%2i%4i%2i";
    # leave screen:  primary -> secondary
    # leaving screen.  the secondary screen should send clipboard
    # data in response to this message for those clipboards that
    # it has grabbed (i.e. has sent a kMsgCClipboard for and has
    # not received a kMsgCClipboard for with a greater sequence
    # number) and that were grabbed or have changed since the
    # last leave.
    kMsgCLeave                   = "COUT";
    # grab clipboard:  primary <-> secondary
    # sent by screen when some other app on that screen grabs a
    # clipboard.  $1 = the clipboard identifier, $2 = sequence number.
    # secondary screens must use the sequence number passed in the
    # most recent kMsgCEnter.  the primary always sends 0.
    kMsgCClipboard               = "CCLP%1i%4i";
    # screensaver change:  primary -> secondary
    # screensaver on primary has started ($1 == 1) or closed ($1 == 0)
    kMsgCScreenSaver             = "CSEC%1i";
    # reset options:  primary -> secondary
    # client should reset all of its options to their defaults.
    kMsgCResetOptions            = "CROP";
    # resolution change acknowledgment:  primary -> secondary
    # sent by primary in response to a secondary screen's kMsgDInfo.
    # this is sent for every kMsgDInfo, whether or not the primary
    # had sent a kMsgQInfo.
    kMsgCInfoAck                 = "CIAK";
    # keep connection alive:  primary <-> secondary
    # sent by the server periodically to verify that connections are still
    # up and running.  clients must reply in kind on receipt.  if the server
    # gets an error sending the message or does not receive a reply within
    # a reasonable time then the server disconnects the client.  if the
    # client doesn't receive these (or any message) periodically then it
    # should disconnect from the server.  the appropriate interval is
    # defined by an option.
    kMsgCKeepAlive               = "CALV";
    #
    # data codes
    #
    # The same as kMsgDKeyDown but with languageCode
    # $4 = languageCode
    kMsgDKeyDownLang             = "DKDL%2i%2i%2i%s";
    # key pressed:  primary -> secondary
    # $1 = KeyID, $2 = KeyModifierMask, $3 = KeyButton
    # the KeyButton identifies the physical key on the primary used to
    # generate this key.  the secondary should note the KeyButton along
    # with the physical key it uses to generate the key press.  on
    # release, the secondary can then use the primary's KeyButton to
    # find its corresponding physical key and release it.  this is
    # necessary because the KeyID on release may not be the KeyID of
    # the press.  this can happen with combining (dead) keys or if
    # the keyboard layouts are not identical and the user releases
    # a modifier key before releasing the modified key.
    # languageCode is parameter which helps client to react on unknwon
    # language letters
    kMsgDKeyDown                 = "DKDN%2i%2i%2i";
    # key pressed 1.0:  same as above but without KeyButton
    kMsgDKeyDown1_0              = "DKDN%2i%2i";
    # key auto-repeat:  primary -> secondary
    # $1 = KeyID, $2 = KeyModifierMask, $3 = number of repeats, $4 = KeyButton
    # $5 =language code
    kMsgDKeyRepeat               = "DKRP%2i%2i%2i%2i%s";
    # key auto-repeat 1.0:  same as above but without KeyButton
    kMsgDKeyRepeat1_0            = "DKRP%2i%2i%2i";
    # key released:  primary -> secondary
    # $1 = KeyID, $2 = KeyModifierMask, $3 = KeyButton
    kMsgDKeyUp                   = "DKUP%2i%2i%2i";
    # key released 1.0:  same as above but without KeyButton
    kMsgDKeyUp1_0                = "DKUP%2i%2i";
    # mouse button pressed:  primary -> secondary
    # $1 = ButtonID
    kMsgDMouseDown               = "DMDN%1i";
    # mouse button released:  primary -> secondary
    # $1 = ButtonID
    kMsgDMouseUp                 = "DMUP%1i";
    # mouse moved:  primary -> secondary
    # $1 = x, $2 = y.  x,y are absolute screen coordinates.
    kMsgDMouseMove               = "DMMV%2i%2i";
    # relative mouse move:  primary -> secondary
    # $1 = dx, $2 = dy.  dx,dy are motion deltas.
    kMsgDMouseRelMove            = "DMRM%2i%2i";
    # mouse scroll:  primary -> secondary
    # $1 = xDelta, $2 = yDelta.  the delta should be +120 for one tick forward
    # (away from the user) or right and -120 for one tick backward (toward
    # the user) or left.
    kMsgDMouseWheel              = "DMWM%2i%2i";
    # mouse vertical scroll:  primary -> secondary
    # like as kMsgDMouseWheel except only sends $1 = yDelta.
    kMsgDMouseWheel1_0           = "DMWM%2i";
    # clipboard data:  primary <-> secondary
    # $2 = sequence number, $3 = mark $4 = clipboard data.  the sequence number
    # is 0 when sent by the primary.  secondary screens should use the
    # sequence number from the most recent kMsgCEnter.  $1 = clipboard
    # identifier.
    kMsgDClipboard               = "DCLP%1i%4i%1i%s";
    # client data:  secondary -> primary
    # $1 = coordinate of leftmost pixel on secondary screen,
    # $2 = coordinate of topmost pixel on secondary screen,
    # $3 = width of secondary screen in pixels,
    # $4 = height of secondary screen in pixels,
    # $5 = size of warp zone, (obsolete)
    # $6, $7 = the x,y position of the mouse on the secondary screen.
    #
    # the secondary screen must send this message in response to the
    # kMsgQInfo message.  it must also send this message when the
    # screen's resolution changes.  in this case, the secondary screen
    # should ignore any kMsgDMouseMove messages until it receives a
    # kMsgCInfoAck in order to prevent attempts to move the mouse off
    # the new screen area.
    kMsgDInfo                    = "DINF%2i%2i%2i%2i%2i%2i%2i";
    # set options:  primary -> secondary
    # client should set the given option/value pairs.  $1 = option/value
    # pairs.
    kMsgDSetOptions              = "DSOP%4I";
    # file data:  primary <-> secondary
    # transfer file data. A mark is used in the first byte.
    # 0 means the content followed is the file size.
    # 1 means the content followed is the chunk data.
    # 2 means the file transfer is finished.
    kMsgDFileTransfer            = "DFTR%1i%s";
    # drag infomation:  primary <-> secondary
    # transfer drag infomation. The first 2 bytes are used for storing
    # the number of dragging objects. Then the following string consists
    # of each object's directory.
    kMsgDDragInfo                = "DDRG%2i%s";
    # secure input notification:  primary -> secondary
    # $1 = app. app only obtainable on MacOS since that's the only
    # platform facing secure input problems
    kMsgDSecureInputNotification = "SECN%s";
    # language synchronization:  primary -> secondary
    # $1 = List of server languages
    kMsgDLanguageSynchronisation = "LSYN%s";
    # query screen info:  primary -> secondary
    # client should reply with a kMsgDInfo.
    kMsgQInfo                    = "QINF";
    # incompatible versions:  primary -> secondary
    # $1 = major version of primary, $2 = minor version of primary.
    kMsgEIncompatible            = "EICV%2i%2i";
    # name provided when connecting is already in use:  primary -> secondary
    kMsgEBusy                    = "EBSY";
    # unknown client:  primary -> secondary
    # name provided when connecting is not in primary's screen
    # configuration map.
    kMsgEUnknown                 = "EUNK";
    # protocol violation:  primary -> secondary
    # primary should disconnect after sending this message.
    kMsgEBad                     = "EBAD";

################################################

if __name__ == '__main__':
    main()

