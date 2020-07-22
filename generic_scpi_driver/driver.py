"""
A generator for drivers for generic devices which communicate over a SCPI
interface, using VISA communications

This module can be used to generate a driver for a device which communicates with simple SCPI commands.
"""
import logging
import re
from collections import namedtuple
from functools import wraps
from threading import RLock
from types import FunctionType

import pyvisa
from serial.tools.list_ports import grep as grep_serial_ports

# from typing import Callable, List, Tuple

_locks = {}
_visa_sessions = {}


def get_hwid_from_com_port(com_port):
    """Get a uniquely identifying HWID from a device attached to a COM port

    The HWID of a device is (/ should be) a unique string that identifies it. Unlike the COM port,
    this string is intrinsic to the device and will never change. Referring to devices by these
    strings is therefore a robust way of doing things. 

    Args:
        com_port (str): COM port e.g. "COM11"

    Raises:
        RuntimeError: Raised if the device is not found or multiple matches are found

    Returns:
        str: HWID of the device on the given COM port
    """
    matches = list(grep_serial_ports(com_port))
    if not matches:
        raise RuntimeError("Device {} not found".format(com_port))
    if len(matches) > 1:
        raise RuntimeError("Multiple matched for device {}".format(com_port))
    return matches[0].hwid


def get_com_port_by_hwid(hwid):
    """Get the current COM port based on a uniquely identifying hardware ID of a device

    The HWID of a device is (/ should be) a unique string that identifies it. Unlike the COM port,
    this string is intrinsic to the device and will never change. Referring to devices by these
    strings is therefore a robust way of doing things. 

    Args:
        hwid (str): Hardware ID string to match, e.g. 'USB VID:PID=0403:6001 SER=A6003SX4A'.
                    This is matched using serial.tools.list_ports.grep so can be less specific
                    if desired. The search should result in a single match otherwise an exception will
                    be raised. 

    Raises:
        RuntimeError: Raised if the device is not found or multiple matches are found

    Returns:
        str: current port of the device (e.g. "COM11")
    """
    matches = list(grep_serial_ports(hwid))
    if not matches:
        raise RuntimeError("Device {} not found".format(hwid))
    if len(matches) > 1:
        raise RuntimeError("Multiple matched for device {}".format(hwid))
    return matches[0].device


def with_lock(f):
    """
    Decorator to cause a function to acquire an RLock for this id before it runs.

    RLocks are stored in the namespace of the class whose function is being decorated.
    Note that this decorator must be applied to a class method
    """

    @wraps(f)
    def wrapped(self, *args, **kw):
        with _locks[self.id]:
            return f(self, *args, **kw)

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped


def with_handler(f):
    """
    Decorator to wrap function in a try/except block, handling VISAIOErrors by clear()ing the device,
    then passing on the exception.

    This decorator expects the instance method self.instr.clear() to exit
    """

    @wraps(f)
    def wrapped(self, *args, **kw):
        try:
            return f(self, *args, **kw)
        except pyvisa.VisaIOError:
            self.instr.clear()
            raise

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped


class GenericDriver:
    """
    A template driver for a generic VISA device

    Template for devices which communicate by sending / receiving text commands.
    This class should be inherited by your driver.

    You can register new commands by calling :meth:`GenericDriver.register_query`. This will create a
    method on the class which queries your device returns the response. The
    class builder supports input and output validation as well as custom error
    handling.

    If you need more advanced logic in your driver, you can still just add
    methods as normal. They'll work side-by-side with methods registered by
    :meth:`GenericDriver.register_query`.
    """

    _simulator_factory = None

    def __init__(
        self,
        *args,
        id=None,
        simulation=False,
        baud_rate=57600,
        command_separator=" ",
        **kwargs
    ):
        """Make a new device driver

        If your child class also has an init function, don't forget to call
        `super().__init__()`!

        If you pass a simulation_object (a callable which returns an object
        which implements a method called "query" which takes a string as input
        and produces a string as output) then this driver can be run in
        simulation mode by passing ``simulation_mode=True`` to the constuctor.

        Note that this constuctor ignores positional arguments: this means that
        it can be used with ARTIQ which passes the device manager into new
        driver constructors.
        """
        logging.debug("Creating new driver object for device %s", id)

        self.command_separator = command_separator

        # ID of the device that this driver controls
        if not id:
            raise ValueError("You must pass an id")
        try:
            self.id = get_com_port_by_hwid(id)
            if self.id.lower() == id.lower():
                logging.warning(
                    (
                        "Initiated device from COM port: it would be more "
                        'robust to use the HWID instead. For "%s", that\'s "%s"'
                    ),
                    self.id,
                    get_hwid_from_com_port(self.id),
                )
        except RuntimeError as e:
            if simulation:
                # Simulation mode, so don't worry about a missing device
                self.id = id
            else:
                raise e

        logging.debug("Found device %s on COM port %s", id, self.id)

        # Create a Lock for this resource if it doesn't already exist. This lives
        # in the namespace of this module and so is common across all Drivers,
        # just in case you make multiple drivers pointing to the same device for
        # some reason
        if self.id not in _locks:
            _locks[self.id] = RLock()

        # Claim this device exclusivly while we manipulate it
        with _locks[self.id]:
            self.dev_id = str(self.__class__) + self.id
            if simulation:
                self.dev_id += "Sim"

            logging.debug(
                "Accessing controller {} with locks {}".format(self.dev_id, _locks)
            )

            if simulation:
                if not self.__class__._simulator_factory:
                    raise RuntimeError(
                        "Simulation mode is not available: you must first call register_simulator"
                    )
                if self.dev_id not in _visa_sessions:
                    _visa_sessions[self.dev_id] = self.__class__._simulator_factory()
            else:
                if self.dev_id not in _visa_sessions:
                    # Pass all unrecognised keyword arguments to _setup_device
                    _visa_sessions[self.dev_id] = self._setup_device(
                        self.id, baud_rate=baud_rate, **kwargs
                    )

        self.check_connection()

    @property
    def instr(self):
        """
        Get the VISA session for this device.

        This is stored in a shared namespace for this python session,
        so other GenericDrivers can access the same device in a thread-safe way, taking turns via @with_lock.
        """
        return _visa_sessions[self.dev_id]

    @classmethod
    def register_simulator(cls, simulator_factory):
        """Register a simulator for this class

        If you call this method with a function that creates a simulator (i.e. a
        factory function) then running this driver in simulation mode will be
        possible. Your simulator object must respond to obj.query(str) calls
        with a string.

        Args:
            simulator_factory (Callable): Function to generate a simulator object
        """
        if not callable(simulator_factory):
            raise ValueError("Expected a callable for simulator_factory")
        cls._simulator_factory = simulator_factory

    Arg = namedtuple("Arg", ["name", "default", "validator"])
    Arg.__new__.__defaults__ = (None, str)  # type: ignore

    @classmethod
    def register_query(
        cls,
        method_name: str,
        device_command: str,
        response_parser=str,
        response_validator=None,
        args=[],
    ):
        registered_args = [GenericDriver.Arg(*a) for a in args]

        # Define a function that will be called with the arguments provided.
        # This is guaranteed to get the right number of arguments with defaults
        # already present because we will call it from a wrapper
        @with_lock
        @with_handler
        def func(self, *args):
            arg_strings = []
            for arg, registered_arg in zip(args, registered_args):
                arg_strings.append(registered_arg.validator(arg))

            cmd_string = self.command_separator.join([device_command] + arg_strings)

            if response_parser:
                r = self.instr.query(cmd_string)

                # Validate the response if available
                if response_validator:
                    response_validator(r)

                # Return the parsed result
                return response_parser(r)
            else:
                self.instr.write(cmd_string)

        # Build a python function which takes the arguments as named. This is useful because now our bound methods
        # are real python methods, and so can respond to e.g.
        #     obj.set_mode(1)
        # or
        #     obj.set_mode(mode=1)
        # Also, python does the validation of number of args and setting of defaults for us
        list_of_arg_names = ["self"]
        for arg in registered_args:
            if not re.match(r"^[\w_]+$", arg.name):
                raise ValueError("'{}' is an invalid argument name".format(arg.name))
            list_of_arg_names.append(arg.name)
        all_arg_names = ", ".join(list_of_arg_names)

        defaults = []
        for arg in registered_args:
            if arg.default:
                defaults.append(arg.default)
            else:
                if defaults:
                    raise ValueError(
                        "You can't have arguments without defaults after arguments with defaults"
                    )

        # Compile the wrapping function to call the one we already defined
        func_code_str = """def wrapping_func({args}): return func({args})""".format(
            args=all_arg_names
        )

        wrapping_func_code = compile(func_code_str, "<string>", "exec")

        # Bind this wrapping code to create a function. Pass it the current
        # context so that it can refer to func(). Also pass it the default
        # values required.
        wrapping_func = FunctionType(
            wrapping_func_code.co_consts[0],
            {**globals(), **locals()},
            method_name,
            tuple(defaults),
        )

        # Add a doc string
        wrapping_func.__doc__ = """
Query "{}"

This function is automatically generated. It will call the command "{}"
and expects you to pass it {} arguments named {}.
        """.format(
            method_name,
            device_command,
            len(args),
            [arg.name for arg in registered_args],
        ).strip()

        setattr(cls, method_name, wrapping_func)

    @with_lock
    @with_handler
    def check_connection(self):
        """ Check the connection to the device

        You should override this method if you want checks in the setup

        Raises:
            Whatever errors you want to raise if the connection isn't working

        Returns:
            None
        """
        pass

    @staticmethod
    def _setup_device(
        id, baud_rate, read_termination="\n", write_termination="\n", timeout=None
    ):
        """Open a visa connection to the device

        Raises:
            RuntimeError: Raised if VISA comms fail

        :rtype: :class:pyvisa.resources.Resource
        """
        # Get a handle to the instrument
        rm = pyvisa.ResourceManager()
        instr = rm.open_resource(id)

        logging.debug(rm.list_resources())
        logging.debug(instr)

        # Configure the connection as required
        instr.baud_rate = baud_rate
        if read_termination:
            instr.read_termination = read_termination
        if write_termination:
            instr.write_termination = write_termination
        if timeout:
            instr.timeout = timeout
        # instr.data_bits = 8
        # instr.stop_bits = visa.constants.StopBits.one
        # instr.parity = visa.constants.Parity.none
        # instr.flow_control = visa.constants.VI_ASRL_FLOW_NONE

        logging.debug('Device "{}" init complete'.format(id))

        return instr


# register_query(Driver, "get_identity", "*idn", response_validator=None)
# register_query(Driver, "get_status", "stat", response_parser=lambda x:
#                int(x, 2), response_validator=None)
# register_query(Driver,
#                "get_version", "*git", response_parser=int, response_validator=None)

# # register_command(Driver, "calibrate", "CALI", response_validator=None)
# # register_query(Driver, "set_measurement_mode", "MODE", response_parser=int, args=[('mode', int, ...)])
