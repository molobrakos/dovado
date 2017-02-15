#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Communicate with Dovado router

Usage:
  dovado.py (-h | --help)
  dovado.py --version
  dovado.py [-v|-vv] [options] (state | info | services | traffic | help)
  dovado.py [-v|-vv] [options] sms <number> <message>

Options:
  -u <username>, --username=<username> Dovado router username
  -p <password>, --password=<password> Dovado router password
  -n <host>, --host=<host>             Dovado router ip [default: <autodetect>]
  -p <port>, --port=<port>             Dovado router port [default: 6435]
  -h --help                            Show this message
  -v,-vv                               Increase verbosity
  --version                            Show version
"""

import logging
from datetime import datetime, timedelta
from contextlib import contextmanager, closing
from curses.ascii import ETB
import telnetlib
import json
from sys import argv
from os import path

TIMEOUT = timedelta(seconds=5)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 6435

__version__ = '0.1.15'


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


class Connection():
    """Connection to the router."""

    def __init__(self):
        self._telnet = None

    def _until(self, what):
        """Wait for response."""
        what = what.encode('utf-8')
        ret = self._telnet.read_until(what, timeout=TIMEOUT.seconds)
        return ret.decode('ascii')

    def write(self, what):
        """Write data to connection."""
        _log('send', what)
        self._telnet.write(what.encode('utf-8'))

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

    def query(self, cmd, parse=False):
        """Make query and convert response into dict."""
        res = self.send(cmd)
        if not parse:
            return res
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
               for k,v in res]
        res = dict(res)
        return res

    @contextmanager
    def connect(self, host, port):
        """Open connection to router."""
        self._telnet = telnetlib.Telnet(host, port,
                                        timeout=TIMEOUT.seconds)
        with closing(self._telnet):
            yield self


class Dovado():
    """Representing a Dovado router."""

    def __init__(self, username, password, host=None, port=None):
        self._username = username
        self._password = password
        self._host = host or _get_gw()
        self._port = int(port) or DEFAULT_PORT

    @contextmanager
    def session(self):
        """Open connection to router."""
        _LOGGER.info('Connecting to %s@%s:%d',
                     self._username, self._host, self._port)

        def _expect(condition, reason):
            if not condition:
                raise RuntimeError(reason)

        try:
            with Connection().connect(self._host,
                                      self._port) as conn:
                ret = conn.send('user', self._username)
                _expect('Hello' in ret, 'User unknown')
                ret = conn.send('pass', self._password)
                _expect('Access granted' in ret, 'Could not authenticate')
                yield conn
                conn.send('quit')
        except (RuntimeError, IOError, OSError) as error:
            _LOGGER.warning('Could not communicate with %s@%s:%d: %s',
                            self._username, self._host, self._port, error)
            raise

    def send_sms(self, number, message):
        """Send SMS through the router."""
        with self.session() as conn:
            res = conn.send('sms sendtxt %s' % number)
            if 'Start sms input' not in res:
                return False
            conn.write('%s\n.\n' % message)
            return True

    def query(self, command, parse=True):
        with self.session() as conn:
            return conn.query(command, parse)

    @property
    def state(self):
        """Update state from router."""
        with self.session() as conn:
            _LOGGER.info('Querying state')
            info = conn.query('info')
            services = conn.query('services')
            info.update(services)
            return info

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
    import docopt
    args = docopt.docopt(__doc__,
                         version=__version__)
    if args['-v'] == 2:
        level=logging.DEBUG
    elif args['-v']:
        level=logging.INFO
    else:
        level=logging.ERROR

    FORMAT = '%(asctime)s %(name)s: %(message)s'
    logging.basicConfig(level=level, format=FORMAT, datefmt='%H:%M:%S')

    credentials = _read_credentials()
    credentials.update({param: args['--'+param]
                        for param in ['username', 'password', 'host', 'port']
                        if args['--'+param]})
    if credentials['host'] == '<autodetect>':
        del credentials['host']

    dovado = Dovado(**credentials)

    def emit(d):
        if isinstance(d, dict):
            print(json.dumps(d, indent=2))
        else:
            print(d)

    try:
        if args['state']:
            emit(dovado.state)
        elif args['help']:
            emit(dovado.query('help', parse=False))
        elif args['info']:
            emit(dovado.query('info'))
        elif args['services']:
            emit(dovado.query('services'))
        elif args['traffic']:
            emit(dovado.query('traffic', parse=False))
        elif args['sms']:
            dovado.send_sms(args['<number>'], args['<message>'])
    except (RuntimeError, OSError, IOError):
        exit('Failed to contact router')

if __name__ == '__main__':
    main()
