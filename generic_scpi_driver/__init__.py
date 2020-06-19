"""generic_scpi_driver - A generic template for creating python object-based drivers for SCPI hardware devices which communicate via VISA. Compatible with ARTIQ. """

__author__ = "Charles Baynham <charles.baynham@npl.co.uk>"
__all__ = []

from ._version import get_versions

__version__ = get_versions()["version"]
del get_versions
