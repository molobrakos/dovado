#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Communicate with Dovado router
"""

import logging
from datetime import timedelta
from contextlib import contextmanager
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
    gws = netifaces.gateways()
    gateway = gws['default'][netifaces.AF_INET][0]
    _LOGGER.info("Using gateway %s", gateway)
    return gateway


class Connection():
    """Connection to the router."""

    def __init__(self, username, password, hostname=None, port=DEFAULT_PORT):
        self._username = username
        self._password = password
        self._hostname = hostname or _get_gw()
        self._port = port
        self._telnet = None

    def _until(self, what):
        """Wait for response."""
        return self._telnet.read_until(what.encode("utf-8"),
                                       timeout=TIMEOUT.seconds)

    def send(self, *cmd):
        """Send command to router."""
        cmd = " ".join(cmd)
        _LOGGER.debug("sending %s", cmd)
        cmd = cmd + "\n"
        cursor = ">> "
        self._until(cursor)
        self._telnet.write(cmd.encode("utf-8"))
        ret = self._until(chr(ETB))[:-1]\
                  .decode("ascii")\
                  .splitlines()
        _LOGGER.debug("got %s", ret)
        return ret

    def query(self, cmd):
        """Make query and convert response into dict."""
        res = self.send(cmd)
        res = [item.split("=") for item in res]
        res = [item[0].split(":") if len(item) == 1 else item for item in res]
        res = {k.lower().replace("_", " "): v for k, v in res}
        return res

    @contextmanager
    def _open(self):
        """Open connection to router."""
        try:
            _LOGGER.info("Connecting to %s@%s:%d",
                         self._username, self._hostname, self._port)
            self._telnet = telnetlib.Telnet(self._hostname, self._port,
                                            timeout=TIMEOUT.seconds)
            self.send("user", self._username)
            self.send("pass", self._password)

            yield self

            self.send("quit")
            self._telnet.close()
        except OSError as error:
            _LOGGER.error("Could not communicate with %s@%s:%d: %s",
                          self._username, self._hostname, self._port, error)

    def send_sms(self, number, message):
        """Send SMS through the router."""
        with self._open() as conn:
            conn.send(conn,
                      "sendtxt %s UCS\n%s\n.\n" %
                      number, message)

    def state(self):
        """Update state from router."""
        _LOGGER.info("Updating")
        with self._open() as conn:
            info = conn.query("info")
            services = conn.query("services")
            info.update(services)
            return info

if __name__ == "__main__":
    from sys import argv
    logging.basicConfig(level=logging.INFO)
    if len(argv) < 3:
        exit(-1)
    USERNAME = argv[1]
    PASSWORD = argv[2]
    print(Connection(USERNAME, PASSWORD).state())
