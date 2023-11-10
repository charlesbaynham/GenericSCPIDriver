"""generic_scpi_driver - A generic template for creating python object-based drivers for SCPI hardware devices which communicate via VISA. Compatible with ARTIQ. """
from .driver import GenericDriver
from .driver import with_handler
from .driver import with_lock
from .generic_aqctl import get_controller_func


__author__ = "Charles Baynham <charles.baynham@npl.co.uk>"
__all__ = ["GenericDriver", "with_handler", "with_lock", "get_controller_func"]
__version__ = "1.5"
