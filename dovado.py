#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Communicate with Dovado router
u
Usage:
  dovado.py (-h | --help)
  dovado.py --version
  dovado.py [-v|-vv] [options] (state | info | services | traffic | help)
  dovado.py [-v|-vv] [options] sms <number> <message>

Options:
  -u <username>, --username=<username> Dovado router username
  -p <password>, --password=<password> Dovado router password
  --host=<host>                        Dovado router ip [default: autodetect]
  --port=<port>                        Dovado router port [default: 6435]
  -h --help                            Show this message
  -v                                   Increase verbosity
  -vv                                  Increase verbosity even more
  --version                            Show version
"""

import logging
from datetime import timedelta
from contextlib import contextmanager, closing
from curses.ascii import ETB
import telnetlib
import json
from sys import argv
from os import path

__version__ = '0.4.1'

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
        self._port = int(port or DEFAULT_PORT)
        self._connection = None

    def _until(self, what):
        """Wait for response."""
        what = what.encode('utf-8')
        ret = self._connection.read_until(what, timeout=TIMEOUT.seconds)
        return ret.decode('ascii')

    def _write(self, what):
        """Write data to connection."""
        _log('send', what)
        self._connection.write(what.encode('utf-8'))

    def _send(self, *cmd):
        """Send command to router."""
        cmd = ' '.join(cmd)
        cursor = '>> '
        ret = self._until('\n')
        _log('skip', ret)
        ret = self._until(cursor)
        self._write(cmd + '\n')
        ret = self._until(chr(ETB))[:-1]
        _log('recv', ret)
        return ret

    def _parse_query(self, cmd):
        """Make query and convert response into dict."""
        res = self._send(cmd)
        res = [item.split('=')
               for item in res.splitlines()]
        res = [item[0].split(':')
               if len(item) == 1
               else item
               for item in res]
        res = [(k.lower().replace('_', ' '), v)
               for k, v in res]
        res = [(k, int(v))
               if k.startswith('traffic modem') or k.startswith('sms ')
               else (k, v)
               for k, v in res]
        res = dict(res)
        return res

    @contextmanager
    def _connect(self, hostname, port):
        """Open connection to router."""
        self._connection = telnetlib.Telnet(hostname, port,
                                            timeout=TIMEOUT.seconds)
        with closing(self._connection):
            yield

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
                               self._port):
                _LOGGER.debug('Connected, logging in as user %s',
                              self._username)
                ret = self._send('user', self._username)
                _expect('Hello' in ret, 'User unknown')
                ret = self._send('pass', self._password)
                _expect('Access granted' in ret, 'Could not authenticate')
                yield
                self._send('quit')
        except (RuntimeError, OSError) as error:
            _LOGGER.warning('Could not communicate with %s@%s:%d: %s',
                            self._username, self._hostname, self._port, error)
            raise

    def send_sms(self, number, message):
        """Send SMS through the router."""
        with self.session():
            res = self._send('sms sendtxt %s' % number)
            if 'Start sms input' in res:
                self._write('%s\n.\n' % message)
                return True

    def query(self, command, parse_response=True):
        """Send query to server."""
        with self.session():
            if parse_response:
                return self._parse_query(command)
            else:
                return self._send(command)

    @property
    def state(self):
        """Update state from router."""
        try:
            with self.session():
                _LOGGER.debug('Querying state')
                info = self._parse_query('info')
                services = self._parse_query('services')
                info.update(services)
                return info
        except (RuntimeError, OSError, IOError):
            return None


def _read_credentials():
    """Read credentials from file."""
    try:
        with open(path.join(path.dirname(argv[0]),
                            '.credentials.conf')) as config:
            return dict(x.split(': ')
                        for x in config.read().strip().splitlines()
                        if not x.startswith('#'))
    except (IOError, OSError):
        return {}


def main():
    """Main method."""
    import docopt  # pylint:disable=import-error
    args = docopt.docopt(__doc__,
                         version=__version__)
    if args['-v'] == 2:
        level = logging.DEBUG
    elif args['-v']:
        level = logging.INFO
    else:
        level = logging.ERROR

    fmt = '%(asctime)s %(name)s: %(message)s'
    logging.basicConfig(level=level, format=fmt, datefmt='%H:%M:%S')

    credentials = _read_credentials()
    credentials.update({param: args['--'+param]
                        for param in ['username', 'password', 'host', 'port']
                        if args['--'+param]})
    if credentials['host'] == 'autodetect':
        del credentials['host']

    if 'username' and 'password' not in credentials:
        exit('Username and password expected')

    dovado = Dovado(**credentials)

    def emit(obj):
        """Print object."""
        if isinstance(obj, dict):
            print(json.dumps(obj, indent=2))
        else:
            print(obj)

    try:
        if args['state']:
            emit(dovado.state)
        elif args['help']:
            emit(dovado.query('help', parse_response=False))
        elif args['info']:
            emit(dovado.query('info'))
        elif args['services']:
            emit(dovado.query('services'))
        elif args['traffic']:
            emit(dovado.query('traffic', parse_response=False))
        elif args['sms']:
            dovado.send_sms(args['<number>'], args['<message>'])
    except (RuntimeError, OSError, IOError):
        exit('Failed to contact router')


if __name__ == '__main__':
    main()
