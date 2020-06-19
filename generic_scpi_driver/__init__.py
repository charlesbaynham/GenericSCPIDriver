"""generic_scpi_driver - A generic template for creating python object-based drivers for SCPI hardware devices which communicate via VISA. Compatible with ARTIQ. """

from ._version import get_versions
from .driver import GenericDriver

__version__ = get_versions()["version"]
del get_versions

__author__ = "Charles Baynham <charles.baynham@npl.co.uk>"
__all__ = ["GenericDriver"]
