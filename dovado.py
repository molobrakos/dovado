#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Communicate with Dovado router
"""

import logging
from datetime import timedelta
from contextlib import contextmanager, closing
from curses.ascii import ETB
import telnetlib

__version__ = '0.2.0'

TIMEOUT = timedelta(seconds=5)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 6435


def _get_gw():
    """Determine ip of gateway."""
    try:
        import netifaces
    except ImportError:
        return None
    # pylint: disable=no-member
    gws = netifaces.gateways()
    gateway = gws['default'][netifaces.AF_INET][0]
    _LOGGER.info('Using gateway %s', gateway)
    return gateway


def _log(what, msg):
    """Helper method for logging."""
    if msg.strip():
        _LOGGER.debug('%s %s', what, msg.strip().replace('\n', '\\n'))


class Dovado():
    """Representing a Dovado router."""

    def __init__(self, username, password, hostname=None, port=None):
        self._username = username
        self._password = password
        self._hostname = hostname or _get_gw()
        self._port = port or DEFAULT_PORT
        self._connection = None

    def _until(self, what):
        """Wait for response."""
        what = what.encode('utf-8')
        ret = self._connection.read_until(what, timeout=TIMEOUT.seconds)
        return ret.decode('ascii')

    def write(self, what):
        """Write data to connection."""
        _log('send', what)
        self._connection.write(what.encode('utf-8'))

    def send(self, *cmd):
        """Send command to router."""
        cmd = ' '.join(cmd)
        cursor = '>> '
        ret = self._until('\n')
        _log('skip', ret)
        ret = self._until(cursor)
        self.write(cmd + '\n')
        ret = self._until(chr(ETB))[:-1]
        _log('recv', ret)
        return ret

    def query(self, cmd):
        """Make query and convert response into dict."""        
        with self.session() as conn:
            res = conn.send(cmd)
            res = [item.split('=') for item in res.splitlines()]
            res = [item[0].split(':') if len(item) == 1 else item for item in res]
            res = {k.lower().replace('_', ' '): v for k, v in res}
            return res

    def query_str(self, cmd):
        """Make query and return response as raw string."""        
        with self.session() as conn:
            res = conn.send(cmd)
            return res

    @contextmanager
    def _connect(self, hostname, port):
        """Open connection to router."""
        self._connection = telnetlib.Telnet(hostname, port,
                                            timeout=TIMEOUT.seconds)
        with closing(self._connection):
            yield self

    @contextmanager
    def session(self):
        """Open connection to router."""
        _LOGGER.info('Connecting to %s@%s:%d',
                     self._username, self._hostname, self._port)

        def _expect(condition, reason):
            if not condition:
                raise RuntimeError(reason)

        try:
            with self._connect(self._hostname,
                               self._port) as conn:
                ret = conn.send('user', self._username)
                _expect('Hello' in ret, 'User unknown')
                ret = conn.send('pass', self._password)
                _expect('Access granted' in ret, 'Could not authenticate')
                yield conn
                conn.send('quit')
        except (RuntimeError, OSError) as error:
            _LOGGER.error('Could not communicate with %s@%s:%d: %s',
                          self._username, self._hostname, self._port, error)
            raise

    def send_sms(self, number, message):
        """Send SMS through the router."""
        with self.session() as conn:
            res = conn.send('sms sendtxt %s' % number)
            if 'Start sms input' not in res:
                return False
            conn.write('%s\n.\n' % message)
            return True

    def update(self):
        """Update state from router."""
        try:
            state = self.query('info')
            state.update(self.query('services'))
            return state
        except (RuntimeError, OSError):
            return None

if __name__ == '__main__':
    from sys import argv
    logging.basicConfig(level=logging.DEBUG)
    if len(argv) < 6:
        exit('You should provide at least command, username, password, host and port')
    CMD = argv[1]
    USERNAME = argv[2]
    PASSWORD = argv[3]
    HOSTNAME = argv[4]
    PORT = argv[5]
    
    if CMD == "help":
        print(Dovado(USERNAME, PASSWORD, HOSTNAME, int(PORT)).query_str("help"))
    elif CMD == "info":
        print(Dovado(USERNAME, PASSWORD, HOSTNAME, int(PORT)).query_str("info"))
    elif CMD == "update":
        for key, value in (Dovado(USERNAME, PASSWORD, HOSTNAME, int(PORT)).update()).iteritems():
            print key + ": " + value
    elif CMD == "sms":
        TELNO = argv[6]
        MSG = argv[7]
        Dovado(USERNAME, PASSWORD, HOSTNAME, int(PORT)).send_sms(TELNO, MSG)
    else:
        print "Not yet implemented"
        
