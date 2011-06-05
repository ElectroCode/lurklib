#    This file is part of Lurklib.
#    Copyright (C) 2011  LK-
#
#    Lurklib is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Lurklib is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Lurklib.  If not, see <http://www.gnu.org/licenses/>.

""" Lurklib's Core file. """

from __future__ import with_statement
from . import variables, exceptions, channel
from . import connection, optional, sending, squeries, uqueries


class _Core(variables._Variables, exceptions._Exceptions,
           connection._Connection, channel._Channel,
           sending._Sending, uqueries._UserQueries,
           squeries._ServerQueries, optional._Optional):
    """ Core IRC-interaction class. """
    def __init__(self, server, port=None, nick='Lurklib',
                  user='Lurklib',
                  real_name='The Lurk Internet Relay Chat Library',
                  password=None, tls=False, tls_verify=False, encoding='UTF-8',
                  hide_called_events=True, UTC=False):
        """
        Initializes Lurklib and connects to the IRC server.
        Required arguments:
        * server - IRC server to connect to.
        Optional arguments:
        * port=None - IRC port to use.
            if tls is selected it defaults to 6697 -
            if not, it defaults to 6667.
        * nick='Lurklib' - IRC nick to use.
            If a tuple/list is specified it will try to use the first,
            and if the first is already -
            used it will try to use the second and so on.
        * user='Lurklib' - IRC username to use.
        * real_name='The Lurk Internet Relay Chat Library'
             - IRC real name to use.
        * password=None - IRC server password.
        * tls=False - Should the connection use TLS/SSL?
        * tls_verify=False - Verify the TLS certificate?
        * encoding='UTF-8' - The encoding that should be used.
            if the IRC server specifies a CHARSET it will be used instead,
            however in the event of a LookupError it will fallback to this.
        * hide_called_events=True
             - Whether or not to hide events that are -
             generated by calling a Lurklib channel method.
        * UTC=False - Should Lurklib's time objects use UTC?
        """
        self.hide_called_events = hide_called_events
        self.UTC = UTC
        self.fallback_encoding = encoding
        self.encoding = encoding
        self._clrf = '\r\n'

        self._init(server, nick, user, real_name, password, port, tls, \
                   tls_verify)

    def find(self, haystack, needle):
        """
        Finds needle in haystack.
        If needle is found return True, if not return False.
        Required arguments:
        * haystack - Text to search in.
        * needle - Text to search for.
        """
        try:
            qstatus = haystack.find(needle)
        except AttributeError:
            if needle in haystack:
                return True
            else:
                return False
        if qstatus == -1:
            return False
        elif qstatus != -1:
            return True

    def send(self, msg, error_check=False):
        """
        Send a raw string with the clrf appended to it.
        Required arguments:
        * msg - Message to send.
        Optional arguments:
        * error_check=False - Check for errors. \
        If an error is found the relevant exception will be raised.
        """
        with self.lock:
            msg = msg.replace('\r', '\\r').replace('\n', '\\n') + self._clrf
            try:
                data = msg.encode(self.encoding)
            except UnicodeEncodeError:
                data = msg.encode(self.fallback_encoding)
            self._socket.send(data)
            if error_check and self.readable():
                self._recv()
                self.stepback()

    def _mcon(self):
        """ Buffer IRC data and handle PING/PONG. """
        with self.lock:
            sdata = ' '
            while sdata[-1] != self._clrf[-1]:
                if sdata == ' ':
                    sdata = ''
                try:
                    sdata = sdata + \
                    self._socket.recv(4096).decode(self.encoding)
                except UnicodeDecodeError:
                    sdata = sdata + \
                    self._socket.recv(4096).decode(self.fallback_encoding)

            lines = sdata.split(self._clrf)
            for line in lines:
                if line.find('PING :') == 0:
                    self.send(line.replace('PING', 'PONG'))
                if line != '':
                    self._buffer.append(line)

    def _raw_recv(self):
        """ Return the next available IRC message in the buffer. """
        with self.lock:
            if self._index >= len(self._buffer):
                self._mcon()
            if self._index >= 199:
                self._resetbuffer()
                self._mcon()
            msg = self._buffer[self._index]
            while self.find(msg, 'PING :'):
                self._index += 1
                try:
                    msg = self._buffer[self._index]
                except IndexError:
                    self._mcon()
                    self._index -= 1

            self._index += 1
            return msg

    def readable(self, timeout=1):
        """
        Checks whether self.recv() will block or not.
        Optional arguments:
        * timeout=1 - Wait for the socket to be readable,
            for timeout amount of time.
        """
        with self.lock:
            if len(self._buffer) > self._index:
                return True
            else:
                if self._select([self._socket], [], [], timeout)[0] == []:
                    return False
                else:
                    return True

    def _resetbuffer(self):
        """ Resets the IRC buffer. """
        with self.lock:
            self._index, self._buffer = 0, []

    def stepback(self, append=False):
        """
        Stepbacks/reverses the buffer.
        Optional arguments:
        * append=False - If True, appends the data onto the buffer;
                        else, it just steps the index back.
        """
        if append:
            data = self._buffer[self._index - 1]
            self._buffer.append(data)
        else:
            self._index -= 1

    def _from_(self, who):
        """
        Processes nick!user@host data.
        Returns a tuple containing, the nick, user and host.
        If a valid hostmask isn't found, return the data as is.
        Required arguments:
        * who - nick!user@host data.
        """
        try:
            host = who.split('@', 1)
            nickident = host[0].split('!', 1)
            nick = nickident[0]
            ident = nickident[1]
            host = host[1]
            return nick, ident, host
        except IndexError:
            return who

    def _recv(self, rm_colon=False, blocking=True, \
              expected_replies=None, default_rvalue=None, \
              ignore_unexpected_replies=True, rm_first=True):
        """
        Receives and processes an IRC protocol message.
        Optional arguments:
        * rm_colon=False - If True:
                        If the message is > 3 items long:
                            Remove the colon(if found) from the [3] item.
                        Else:
                        Remove the colon(if found) from the [2] item.
        * blocking=True - Should this call block?
        * expected_replies=None - If specified:
                     If no matching reply is found:
                        Return the default_rvalue.
                    Else:
                        Return the message.
        * default_rvalue=None - If no message or a matching message;
                            is found, return default_rvalue.
        * ignore_unexpected_replies=True - If an,
                                    unexpected reply is encountered,
                                    should we keep going,
                                    until we get a valid reply?
                                    If False, it will just return \
                        default_rvalue(If a valid reply isn't found).
        * rm_first=True - If True, remove [0] from the message before returning it.
        """
        append = False
        if expected_replies:
            if len(expected_replies) > 1:
                append = True

        if self.readable():
            msg = self._raw_recv()
        else:
            if not blocking:
                return default_rvalue
            else:
                msg = self._raw_recv()
#<FIXME>
        try:
            msg = msg.split(None, 3)
        except AttributeError:
            pass
#</FIXME>
        if msg[1] in self.error_dictionary:
            self.exception(msg[1])
        if rm_colon:
            if len(msg) > 3:
                if msg[3][0] == ':':
                    msg[3] = msg[3][1:]
            elif len(msg) > 2:
                if msg[2][0] == ':':
                    msg[2] = msg[2][1:]
        if expected_replies:
            if msg[1] in expected_replies:
                if rm_first:
                    return msg[1:]
                else:
                    return msg
            else:
                self.stepback(append)
                if ignore_unexpected_replies:
                    return self._recv(rm_colon=rm_colon, blocking=blocking, \
                               expected_replies=expected_replies, \
                               default_rvalue=default_rvalue, \
            ignore_unexpected_replies=ignore_unexpected_replies)

                return default_rvalue
        return msg

    def recv(self, timeout=None):
        """
        High-level IRC buffering system and processor.
        Optional arguments:
        * timeout=None - Time to wait before returning None.
            Defaults to waiting forever.
        """
        with self.lock:
            if timeout != None:
                if self.readable(timeout) == False:
                    return None
            data = self._raw_recv()
            segments = data.split()

            if segments[1] == 'JOIN':
                who = self._from_(segments[0][1:])
                channel = segments[2][1:]
                if channel not in self.channels:
                    self._index -= 1
                    return 'JOIN', self.join_(channel, process_only=True)
                else:
                    self.channels[channel]['USERS'][who[0]] = \
                    ['', '', '', '', '']
                return 'JOIN', (who, channel)

            elif segments[1] == 'PART':
                who = self._from_(segments[0].replace(':', '', 1))
                channel = segments[2]
                del self.channels[channel]['USERS'][who[0]]
                try:
                    reason = ' '.join(segments[3:]).replace(':', '', 1)
                    return 'PART', (who, channel, reason)
                except IndexError:
                    who = self._from_(segments[0].replace(':', '', 1))
                    return 'PART', (who, channel, '')

            elif segments[1] == 'PRIVMSG':
                who = self._from_(segments[0].replace(':', '', 1))
                msg = ' '.join(segments[3:]).replace(':', '', 1)
                rvalue = 'PRIVMSG', (who, segments[2], msg)

                if msg.find('\001') == 0:
                    rctcp = self.ctcp_decode(msg).upper()
                    return 'CTCP', (rvalue[1][0], rvalue[1][1], rctcp)
                else:
                    return rvalue

            elif segments[1] == 'NOTICE':
                who = self._from_(segments[0].replace(':', '', 1))
                msg = ' '.join(segments[3:]).replace(':', '', 1)
                if msg.find('\001') == 0:
                    msg = self.ctcp_decode(msg)
                    return 'CTCP_REPLY', (who, segments[2], msg)
                return 'NOTICE', (who, segments[2], msg)

            elif segments[1] == 'MODE':
                mode = ' '.join(segments[3:]).replace(':', '', 1)
                who = self._from_(segments[0][1:])
                target = segments[2]
                if target != self.current_nick:
                    self.parse_cmode_string(mode, target)
                    return 'MODE', (who, segments[2], mode)
                else:
                    return 'MODE', (who, mode.replace(':', '', 1))

            elif segments[1] == 'KICK':
                who = self._from_(segments[0].replace(':', '', 1))
                if self.current_nick == segments[3]:
                    del self.channels['USERS'][segments[2]]
                del self.channels[segments[2]]['USERS'][segments[3]]
                reason = ' '.join(segments[4:]).replace(':', '', 1)
                return 'KICK', (who, segments[2], segments[3], reason)

            elif segments[1] == 'INVITE':
                who = self._from_(segments[0].replace(':', '', 1))
                channel = segments[3].replace(':', '', 1)
                return 'INVITE', (who, segments[2], channel)

            elif segments[1] == 'NICK':
                who = self._from_(segments[0].replace(':', '', 1))
                new_nick = ' '.join(segments[2:]).replace(':', '', 1)
                if self.current_nick == who[0]:
                    self.current_nick = new_nick
                for channel in self.channels:
                    if who[0] in self.channels[channel]['USERS']:
                        priv_level = self.channels[channel]['USERS'][who[0]]
                        del self.channels[channel]['USERS'][who[0]]
                        self.channels[channel]['USERS'][new_nick] = priv_level
                return 'NICK', (who, new_nick)

            elif segments[1] == 'TOPIC':
                who = self._from_(segments[0].replace(':', '', 1))
                channel = segments[2]
                topic = ' '.join(segments[3:]).replace(':', '', 1)
                self.channels[channel]['TOPIC'] = topic
                return 'TOPIC', (who, channel, topic)

            elif segments[1] == 'QUIT':
                who = self._from_(segments[0].replace(':', '', 1))
                msg = ' '.join(segments[2:]).replace(':', '', 1)
                return 'QUIT', (who, msg)

            elif segments[1] == '250':
                self.lusers['HIGHESTCONNECTIONS'] = segments[6]
                self.lusers['TOTALCONNECTIONS'] = segments[9][1:]
                return 'LUSERS', self.lusers

            elif segments[1] == '251':
                self.lusers['USERS'] = segments[5]
                self.lusers['INVISIBLE'] = segments[8]
                self.lusers['SERVERS'] = segments[11]
                return 'LUSERS', self.lusers

            elif segments[1] == '252':
                self.lusers['OPERATORS'] = segments[3]
                return 'LUSERS', self.lusers

            elif segments[1] == '253':
                self.lusers['UNKNOWN'] = segments[3]
                return 'LUSERS', self.lusers

            elif segments[1] == '254':
                self.lusers['CHANNELS'] = segments[3]
                return 'LUSERS', self.lusers

            elif segments[1] == '255':
                self.lusers['CLIENTS'] = segments[5]
                self.lusers['LSERVERS'] = segments[8]
                return 'LUSERS', self.lusers

            elif segments[1] == '265':
                self.lusers['LOCALUSERS'] = segments[6]
                self.lusers['LOCALMAX'] = segments[8]
                return 'LUSERS', self.lusers

            elif segments[1] == '266':
                self.lusers['GLOBALUSERS'] = segments[6]
                self.lusers['GLOBALMAX'] = segments[8]
                return 'LUSERS', self.lusers

            elif segments[0] == 'ERROR':
                self.quit()
                return 'ERROR', ' '.join(segments[1:]).replace(':', '', 1)
            else:
                self._index -= 1
                return 'UNKNOWN', self._recv()

    def compare(self, first, second):
        """
        Case in-sensitive comparison of two strings.
        Required arguments:
        * first - The first string to compare.
        * second - The second string to compare.
        """
        if first.lower() == second.lower():
            return True
        else:
            return False

    def ctcp_encode(self, msg):
        """
        CTCP encodes a message.
        Required arguments:
        msg - The message to be CTCP encoded.
        Returns the encoded version of the message.
        """
        return '\001%s\001' % msg

    def ctcp_decode(self, msg):
        """
        Decodes a CTCP message.
        Required arguments:
        msg - The message to be decoded.
        Returns the decoded version of the message.
        """
        return msg.replace('\001', '')
