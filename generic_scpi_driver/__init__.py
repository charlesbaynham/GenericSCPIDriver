"""generic_scpi_driver - A generic template for creating python object-based drivers for SCPI hardware devices which communicate via VISA. Compatible with ARTIQ."""

from .driver import GenericDriver
from .driver import with_handler
from .driver import with_lock

__author__ = "Charles Baynham <charles.baynham@npl.co.uk>"

__all__ = ["GenericDriver", "with_handler", "with_lock"]
__version__ = "1.6.2"


try:
    from .generic_aqctl import get_controller_func  # noqa

    __all__.append("get_controller_func")
except ImportError:
    # sipyco is not installed
    pass
