from collections import namedtuple

import pint

ureg = pint.UnitRegistry()
Q_ = ureg.Quantity

Pressure = namedtuple('Pressure', ['qfe', 'qnh', 'qff'])
