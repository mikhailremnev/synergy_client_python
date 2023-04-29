#!/usr/bin/env python3

"""
Simple synergy client in Python

Currently all of the event handling work is done by MessageHandler class

              1  ┌──────┐
       ┌─────────┤Stream│
       │         └──────┘
┌──────◇───────┐
│MessageHandler│
└──────◇───────┘
       │         ┌────────┐
       └─────────┤Protocol│
              1  └────────┘

Stream -- reading/writing messages
Protocol -- parsing messages from bytes to list and then formatting them back from list to bytes

There is also a ProtocolMsg static class that contains all message formats
"""

import socket
import time
import struct
import re

# First message from server (Synergy 1.6):
# b'\x00\x00\x00\x0bSynergy\x00\x01\x00\x06'

def test_parser():
    protocol = Protocol()
    msg = b'Synergy\x00\x01\x00\x06'
    print(protocol.parse(msg))
    msg = b'DSOP\x00\x00\x00\x02CLPS\x00\x00\x00\x01'
    print(protocol.parse(msg))
    msg = b'DCLP\x00\x00\x00\x00\x00\x01\x00\x00\x00\x0213'
    print(protocol.parse(msg))
    msg = b'DKRP\x00d\x00\x02\x00\x01\x00('
    print(protocol.parse(msg))
    msg = b'DCLP\x01\x00\x00\x00\x00\x02\x00\x00\x00\x1e\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x12$ \xd0\xbf\xd1\x80\xd0\xbe\xd0\xb2\xd0\xb5\xd1\x80\xd0\xba\xd0\xb0'
    print(protocol.parse(msg))
    # TODO: Make sense out of clipboard parsing:
    # assert protocol.parse(msg)[4] == '\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x12$ проверка'

def main():
    # test_parser()
    # return

    run()

def run(stream=None, protocol=None, handler=None):
    if stream is None:
        host = socket.gethostname()
        # host = '192.168.162.201'
        port = 24800
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        stream = Stream(sock)

    if protocol is None:
        protocol = Protocol()

    if handler is None:
        handler = MessageHandler(stream, protocol)

    try:
        while True:
            msg = stream.read()
            if msg is None: continue

            if not msg.startswith(b'DMMV'):
                print('From server:', msg)

            try:
                msg_info = protocol.parse(msg)
            except:
                raise RuntimeError('error parsing', msg)

            # [msg_name, *msg_args] 
            if msg_info[0] != 'kMsgDMouseMove':
                print('From server:', msg)
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
    So that 'kMsgHello' message is handled by 'on_hello' method,
    'kMsgCEnter' is handled by 'on_c_enter' method
    """
    def __init__(self, stream, protocol):
        self.stream   = stream
        self.protocol = protocol

    def get_handler(self, msg_name):
        """See class documentation for details on method_name
        """
        # Convert method names of type kMsgDInfo to 'on_d_info'
        msg_name_short = msg_name[4:]
        method_name    = re.sub('[A-Z]', lambda m: '_' + m.group(0).lower(),
                                msg_name_short)
        method_name    = 'on' + method_name
        try:
            return self.__getattribute__(method_name)
        except AttributeError:
            raise KeyError('Could not find handler for', msg_name)

    def handle(self, msg_info):
        msg_name = msg_info[0]
        method = self.get_handler(msg_name)
        try:
            return method(msg_info)
        except:
            raise RuntimeError('Error handling message', msg_info)


    def on_hello(self, msg_info):
        """ say hello to client;  primary -> secondary
        $1 = protocol major version number supported by server.
        $2 = protocol minor version number supported by server.
        $3 = server keyboard layout list.
        """
        # Expected message: b'Synergy\x00\x01\x00\x06'
        ver_maj, ver_min = msg_info[1:]
        print(f'Connected to server v{ver_maj}.{ver_min}')
        return self.protocol.format(ProtocolMsg.kMsgHelloBack, 1, 6, 'tablet')

    def on_hello_back(self, msg_info):
        """ respond to hello from server;  secondary -> primary
        $1 = protocol major version number supported by client.
        $2 = protocol minor version number supported by client.
        $3 = client name.
        """

    def on_c_noop(self, msg_info):
        """ no operation;  secondary -> primary
        """

    def on_c_close(self, msg_info):
        """ close connection;  primary -> secondary
        """
        self.stream.close()
        print('Got CBYE from the server')
        exit(0)

    def on_c_enter(self, msg_info):
        """ enter screen:  primary -> secondary
        entering screen at screen position
        $1 = x,
        $2 = y.  x,y are absolute screen coordinates.
        $3 = sequence number, which is
        used to order messages between screens. the secondary screen
        must return this number with some messages.
        $4 = modifier key mask.  this will have bits set for each
        toggle modifier key that is activated on entry to the screen.
        the secondary screen should adjust its toggle modifiers to reflect that state.
        """
        x, y, seq_num, mod_keymask = msg_info[1:]
        print(msg_info)

    def on_c_leave(self, msg_info):
        """ leave screen:  primary -> secondary
        leaving screen.  the secondary screen should send clipboard
        data in response to this message for those clipboards that
        it has grabbed (i.e. has sent a kMsgCClipboard for and has
        not received a kMsgCClipboard for with a greater sequence
        number) and that were grabbed or have changed since the
        last leave.
        """
        print(msg_info)

    def on_c_clipboard(self, msg_info):
        """ grab clipboard:  primary <-> secondary
        sent by screen when some other app on that screen grabs a
        clipboard.  $1 = the clipboard identifier, $2 = sequence number.
        secondary screens must use the sequence number passed in the
        most recent kMsgCEnter.  the primary always sends 0.
        """

    def on_c_screen_saver(self, msg_info):
        """ screensaver change:  primary -> secondary
        screensaver on primary has started ($1 == 1) or closed ($1 == 0)
        """

    def on_c_reset_options(self, msg_info):
        """ reset options:  primary -> secondary
        client should reset all of its options to their defaults.
        """
        print('TODO: reset options to defaults')

    def on_c_info_ack(self, msg_info):
        """ resolution change acknowledgment:  primary -> secondary
        sent by primary in response to a secondary screen's kMsgDInfo.
        this is sent for every kMsgDInfo, whether or not the primary
        had sent a kMsgQInfo.
        """

    def on_c_keep_alive(self, msg_info):
        """ keep connection alive:  primary <-> secondary
        sent by the server periodically to verify that connections are still
        up and running.  clients must reply in kind on receipt.  if the server
        gets an error sending the message or does not receive a reply within
        a reasonable time then the server disconnects the client.  if the
        client doesn't receive these (or any message) periodically then it
        should disconnect from the server.  the appropriate interval is
        defined by an option.
        """
        # Keepalive packet
        return self.protocol.format(ProtocolMsg.kMsgCKeepAlive)


    def on_d_key_down_lang(self, msg_info):
        """ The same as kMsgDKeyDown but with languageCode
        $4 = languageCode
        """

    def on_d_key_down(self, msg_info):
        """ key pressed:  primary -> secondary
        $1 = KeyID, $2 = KeyModifierMask, $3 = KeyButton
        the KeyButton identifies the physical key on the primary used to
        generate this key.  the secondary should note the KeyButton along
        with the physical key it uses to generate the key press.  on
        release, the secondary can then use the primary's KeyButton to
        find its corresponding physical key and release it.  this is
        necessary because the KeyID on release may not be the KeyID of
        the press.  this can happen with combining (dead) keys or if
        the keyboard layouts are not identical and the user releases
        a modifier key before releasing the modified key.
        languageCode is parameter which helps client to react on unknwon
        language letters
        """
        import pynput
        keyboard = pynput.keyboard.Controller()
        key_id, key_mask, key_button = msg_info[1:]

        if key_id < 0:
            # Not sure why additional 0x1000 is necessary
            key_id +=  0xffff + 0x1000 + 1
            key     = pynput.keyboard.KeyCode(key_id)
        else:
            key_id  = button_to_keysym(key_button)
            key     = pynput.keyboard.KeyCode(key_id)
            # key     = chr(key_id)
        print(key)
        keyboard.press(key)

    def on_d_key_down1_0(self, msg_info):
        """ key pressed 1.0:  same as above but without KeyButton
        """

    def on_d_key_repeat(self, msg_info):
        """ key auto-repeat:  primary -> secondary
        $1 = KeyID, $2 = KeyModifierMask, $3 = number of repeats, $4 = KeyButton
        $5 =language code
        """

    def on_d_key_repeat1_0(self, msg_info):
        """ key auto-repeat 1.0:  same as above but without KeyButton
        """

    def on_d_key_up(self, msg_info):
        """ key released:  primary -> secondary
        $1 = KeyID, $2 = KeyModifierMask, $3 = KeyButton
        """
        import pynput
        keyboard = pynput.keyboard.Controller()
        key_id, key_mask, key_button = msg_info[1:]
        if key_id < 0:
            # Not sure why additional 0x1000 is necessary
            key_id +=  0xffff + 0x1000 + 1
            key     = pynput.keyboard.KeyCode(key_id)
        else:
            # key     = chr(key_id)
            key_id  = button_to_keysym(key_button)
            key     = pynput.keyboard.KeyCode(key_id)
        keyboard.release(key)

    def on_d_key_up1_0(self, msg_info):
        """ key released 1.0:  same as above but without KeyButton
        """

    def on_d_mouse_down(self, msg_info):
        """ mouse button pressed:  primary -> secondary
        $1 = ButtonID
        """
        button_id = msg_info[1]
        import pynput
        mouse = pynput.mouse.Controller()
        if button_id == 1: mouse.press(pynput.mouse.Button.left)
        if button_id == 2: mouse.press(pynput.mouse.Button.middle)
        if button_id == 3: mouse.press(pynput.mouse.Button.right)

    def on_d_mouse_up(self, msg_info):
        """ mouse button released:  primary -> secondary
        $1 = ButtonID
        """
        button_id = msg_info[1]
        import pynput
        mouse = pynput.mouse.Controller()
        if button_id == 1: mouse.release(pynput.mouse.Button.left)
        if button_id == 2: mouse.release(pynput.mouse.Button.middle)
        if button_id == 3: mouse.release(pynput.mouse.Button.right)

    def on_d_mouse_move(self, msg_info):
        """ mouse moved:  primary -> secondary
        $1 = x, $2 = y.  x,y are absolute screen coordinates.
        """
        import mouse
        abs_x, abs_y = msg_info[1:]
        mouse.move(abs_x, abs_y)
        # print(msg_info)

    def on_d_mouse_rel_move(self, msg_info):
        """ relative mouse move:  primary -> secondary
        $1 = dx, $2 = dy.  dx,dy are motion deltas.
        """

    def on_d_mouse_wheel(self, msg_info):
        """ mouse scroll:  primary -> secondary
        $1 = xDelta, $2 = yDelta.  the delta should be +120 for one tick forward
        (away from the user) or right and -120 for one tick backward (toward
        the user) or left.
        """

    def on_d_mouse_wheel1_0(self, msg_info):
        """ mouse vertical scroll:  primary -> secondary
        like as kMsgDMouseWheel except only sends $1 = yDelta.
        """

    def on_d_clipboard(self, msg_info):
        """ clipboard data:  primary <-> secondary
        $2 = sequence number, $3 = mark $4 = clipboard data.  the sequence number
        is 0 when sent by the primary.  secondary screens should use the
        sequence number from the most recent kMsgCEnter.  $1 = clipboard
        identifier.
        """
        clipb_id, seq_num, mark, data = msg_info[1:]
        print(msg_info)

    def on_d_info(self, msg_info):
        """ client data:  secondary -> primary
        $1 = coordinate of leftmost pixel on secondary screen,
        $2 = coordinate of topmost pixel on secondary screen,
        $3 = width of secondary screen in pixels,
        $4 = height of secondary screen in pixels,
        $5 = size of warp zone, (obsolete)
        $6, $7 = the x,y position of the mouse on the secondary screen.
        
        the secondary screen must send this message in response to the
        kMsgQInfo message.  it must also send this message when the
        screen's resolution changes.  in this case, the secondary screen
        should ignore any kMsgDMouseMove messages until it receives a
        kMsgCInfoAck in order to prevent attempts to move the mouse off
        the new screen area.
        """

    def on_d_set_options(self, msg_info):
        """ set options:  primary -> secondary
        client should set the given option/value pairs.  $1 = option/value
        pairs.
        """
        print('TODO: set options')
        print('DSOP', msg_info)

    def on_d_file_transfer(self, msg_info):
        """ file data:  primary <-> secondary
        transfer file data. A mark is used in the first byte.
        0 means the content followed is the file size.
        1 means the content followed is the chunk data.
        2 means the file transfer is finished.
        """

    def on_d_drag_info(self, msg_info):
        """ drag infomation:  primary <-> secondary
        transfer drag infomation. The first 2 bytes are used for storing
        the number of dragging objects. Then the following string consists
        of each object's directory.
        """

    def on_d_secure_input_notification(self, msg_info):
        """ secure input notification:  primary -> secondary
        $1 = app. app only obtainable on MacOS since that's the only
        platform facing secure input problems
        """

    def on_d_language_synchronisation(self, msg_info):
        """ language synchronization:  primary -> secondary
        $1 = List of server languages
        """

    def on_q_info(self, msg_info):
        """ query screen info:  primary -> secondary
        client should reply with a kMsgDInfo.
        """
        print(f'Informing about display info')
        from screeninfo import get_monitors
        # TODO: Use better way to work with multiple monitors
        m = get_monitors()[0]
        values = [
          0,             # leftmost pixel x
          0,             # topmost pixel y
          m.width,       # width
          m.height,      # height
          0,             # obsolete
          m.width  // 2, # mouse_x
          m.height // 2, # mouse_y
        ]
        return self.protocol.format(ProtocolMsg.kMsgDInfo, *values)

    def on_e_incompatible(self, msg_info):
        """ incompatible versions:  primary -> secondary
        $1 = major version of primary, $2 = minor version of primary.
        """
        raise RuntimeError('Incompatible protocol version')

    def on_e_busy(self, msg_info):
        """ name provided when connecting is already in use:  primary -> secondary
        """
        raise RuntimeError('Connection already in use')

    def on_e_unknown(self, msg_info):
        """ unknown client:  primary -> secondary
        name provided when connecting is not in primary's screen
        configuration map.
        """
        raise RuntimeError('Not in primary screen configuration map')

    def on_e_bad(self, msg_info):
        """ protocol violation:  primary -> secondary
        primary should disconnect after sending this message.
        """
        raise RuntimeError('Protocol violation')

################################################

class Stream:
    def __init__(self, sock):
        """
        @param sock  Socket for the connection to synergy server
        """
        self.sock = sock
    def read(self):
        # Packet size is sent as big-endian int
        size       = self.sock.recv(4)
        if len(size) == 0: return None
        size       = struct.unpack('>i', size)[0]
        to_receive = size
        #
        data = b''
        while to_receive > 0:
            data += self.sock.recv(to_receive)
            to_receive -= len(data)
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
                    ret.append(val)
                elif fmt_id == 'I':
                    # name, value pairs
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
                    # It seems that sometimes string argument can be skipeed
                    if len(msg) == 0 and len(fmt) == 0: continue
                    strlen, msg = self.__unpack_int(msg, 4)
                    # TODO: Some clipboard contents crashed during parsing when using UTF8
                    content = msg[:strlen] # .decode('utf8')
                    ret.append(content)
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
# AUXILLARY FUNCTIONS

def button_to_keysym(btn_id):
    import pynput
    keyboard = pynput.keyboard.Controller()
    key_map = keyboard.keyboard_mapping
    return [k for (k, v) in key_map.items() if v[0] == btn_id][0]

################################################

if __name__ == '__main__':
    main()

