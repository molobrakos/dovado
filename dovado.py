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
    _LOGGER.info("Using gateway %s", gateway)
    return gateway


def _log(what, msg):
    """Helper method for logging."""
    if msg.strip():
        _LOGGER.debug("%s %s", what, msg.strip().replace("\n", "\\n"))


class Connection():
    """Connection to the router."""

    def __init__(self):
        self._telnet = None

    def _until(self, what):
        """Wait for response."""
        what = what.encode("utf-8")
        ret = self._telnet.read_until(what, timeout=TIMEOUT.seconds)
        return ret.decode("ascii")

    def write(self, what):
        """Write data to connection."""
        _log("send", what)
        self._telnet.write(what.encode("utf-8"))

    def send(self, *cmd):
        """Send command to router."""
        cmd = " ".join(cmd)
        cursor = ">> "
        ret = self._until("\n")
        _log("skip", ret)
        ret = self._until(cursor)
        self.write(cmd + "\n")
        ret = self._until(chr(ETB))[:-1]
        _log("recv", ret)
        return ret

    def query(self, cmd):
        """Make query and convert response into dict."""
        res = self.send(cmd)
        res = [item.split("=") for item in res.splitlines()]
        res = [item[0].split(":") if len(item) == 1 else item for item in res]
        res = {k.lower().replace("_", " "): v for k, v in res}
        return res

    @contextmanager
    def connect(self, hostname, port):
        """Open connection to router."""
        self._telnet = telnetlib.Telnet(hostname, port,
                                        timeout=TIMEOUT.seconds)
        with closing(self._telnet):
            yield self


class Dovado():
    """Representing a Dovado router."""

    def __init__(self, username, password, hostname=None, port=None):
        self._username = username
        self._password = password
        self._hostname = hostname or _get_gw()
        self._port = port or DEFAULT_PORT

    @contextmanager
    def session(self):
        """Open connection to router."""
        _LOGGER.info("Connecting to %s@%s:%d",
                     self._username, self._hostname, self._port)
        try:
            with Connection().connect(self._hostname,
                                      self._port) as conn:
                conn.send("user", self._username)
                conn.send("pass", self._password)
                yield conn
                conn.send("quit")
        except OSError as error:
            _LOGGER.error("Could not communicate with %s@%s:%d: %s",
                          self._username, self._hostname, self._port, error)
            raise

    def send_sms(self, number, message):
        """Send SMS through the router."""
        with self.session() as conn:
            res = conn.send("sms sendtxt %s" % number)
            if "Start sms input" not in res:
                return False
            conn.write("%s\n.\n" % message)
            return True

    def query_state(self):
        """Update state from router."""
        with self.session() as conn:
            info = conn.query("info")
            services = conn.query("services")
            info.update(services)
            return info

if __name__ == "__main__":
    from sys import argv
    logging.basicConfig(level=logging.DEBUG)
    if len(argv) < 3:
        exit(-1)
    USERNAME = argv[1]
    PASSWORD = argv[2]
    if len(argv) == 3:
        print(Dovado(USERNAME, PASSWORD).query_state())
    else:
        TELNO = argv[3]
        MSG = argv[4]
        Dovado(USERNAME, PASSWORD).send_sms(TELNO, MSG)
