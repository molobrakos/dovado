#!/usr/bin/python

from setuptools import setup
from dovado import __version__


setup(name="dovado",
      version=__version__,
      description="Communicate with Dovado router",
      url="https://github.com/molobrakos/dovado",
      license="",
      author="Erik",
      author_email="Erik",
      scripts=["dovado.py"],
      py_modules=["dovado"],
      provides=["dovado"],
      install_requires=[
          'netifaces'
      ],
      extras_require={
          'console':  ['docopt'],
      })
