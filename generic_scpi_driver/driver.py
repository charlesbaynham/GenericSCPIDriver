"""
A generator for drivers for generic devices which communicate over a SCPI
interface, using VISA communications

This module can be used to generate a driver for a device which communicates with simple SCPI commands.
"""

import asyncio
import logging
import re
from collections import namedtuple
from functools import partial
from functools import wraps
from threading import RLock
from types import FunctionType

from .session import Session
from .visa_session import VISASession

logger = logging.getLogger("GenericSCPI")

from typing import Callable
from typing import Optional

_locks = {}
_sessions = {}


def with_lock(f):
    """
    Decorator to cause a function to acquire an RLock for this id before it runs.

    RLocks are stored in the namespace of the class whose function is being decorated.
    Note that this decorator must be applied to a class method
    """

    @wraps(f)
    def wrapped(self: "GenericDriver", *args, **kw):
        with _locks[self.dev_id]:
            return f(self, *args, **kw)

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped


def with_handler(f):
    """
    Decorator to wrap function in a try/except block, handling Exceptions by flush()ing the device,
    then passing on the exception.

    This decorator expects the instance method self.instr.flush() to exit
    """

    @wraps(f)
    def wrapped(self: "GenericDriver", *args, **kw):
        try:
            return f(self, *args, **kw)
        except Exception:
            self.instr.flush()

            raise

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped


class GenericDriver:
    """
    A template driver for a generic VISA device

    Template for devices which communicate by sending / receiving text commands.
    This class should be inherited by your driver.

    You can register new commands by calling
    :meth:`GenericDriver._register_query`. This will create a method on the
    class which queries your device returns the response. The class builder
    supports input and output validation as well as custom error handling.

    If you need more advanced logic in your driver, you can still just add
    methods as normal. They'll work side-by-side with methods registered by
    :meth:`GenericDriver._register_query`.
    """

    session_factory: Callable[..., Session] = VISASession
    _simulator_factory: Optional[Callable[..., Session]] = None

    def __init__(
        self,
        *args,
        id=None,
        simulation=False,
        baud_rate=57600,
        command_separator=" ",
        **kwargs,
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
        logger.debug("Creating new driver object for device %s", id)

        self.command_separator = command_separator
        self.simulation = simulation

        if not id:
            raise ValueError("You must pass an id")

        self.dev_id = str(self.__class__) + id
        if simulation:
            self.dev_id += "Sim"

        logger.debug(
            "Accessing controller {} with locks {}".format(self.dev_id, _locks)
        )

        # Create a Lock for this resource if it doesn't already exist. This lives
        # in the namespace of this module and so is common across all Drivers,
        # just in case you make multiple drivers pointing to the same device for
        # some reason
        if self.dev_id not in _locks:
            _locks[self.dev_id] = RLock()

        # Claim this device exclusivly while we manipulate it
        with _locks[self.dev_id]:
            if simulation:
                if not self.__class__._simulator_factory:
                    raise RuntimeError(
                        "Simulation mode is not available: you must first call _register_simulator"
                    )
                if self.dev_id not in _sessions:
                    _sessions[self.dev_id] = self.__class__._simulator_factory()
            else:
                if self.dev_id not in _sessions:
                    # Pass all unrecognised keyword arguments to the session factory
                    session = self.__class__.session_factory(
                        id, baud_rate=baud_rate, **kwargs
                    )
                    session.flush()

                    _sessions[self.dev_id] = session

        self.check_connection()

        logger.info(
            "Controller {} successfully started and connected".format(self.dev_id)
        )

    def close(self):
        """
        Close the connection to this device.

        After this method is called, no other methods will work and this object should be discarded.
        """
        logger.debug("Closing connection to device %s", self.dev_id)
        self.instr.close()
        del _locks[self.dev_id]
        del _sessions[self.dev_id]

    @property
    def instr(self) -> Session:
        """
        Get the session for this device.

        This is stored in a shared namespace for this python session,
        so other GenericDrivers can access the same device in a thread-safe way, taking turns via @with_lock.
        """
        logger.debug(
            "Getting instrument object from _visa_sessions for device %s", self.dev_id
        )
        return _sessions[self.dev_id]

    @classmethod
    def _register_simulator(cls, simulator_factory):
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
    def _register_query(
        cls,
        method_name: str,
        device_command: str,
        response_parser=str,
        response_validator=None,
        args=[],
        coroutine=False,
        docstring=None,
    ):
        """Make a function for this class which will access the device.

        Args:
            method_name (str): Name of the method to create
            device_command (str): Command to send to the device. Arguments can follow
            response_parser (callable, optional): Function to pass the response to. Must return a string. If not provided, the device's response will returned as a string. If set to None, the device's response will not be read.
            response_validator (callable, optional): Function to pass the response to before the parser. Can raise an error. Returns are ignored. Defaults to None.
            args (list, optional): List of arguments for the command, as ``GenericDriver.Arg`` objects. Defaults to [].
            coroutine (bool, optional): If true, create an async coroutine instead of a normal method, wrapping serial calls in a threaded executor. Defaults to False.
            docstring (str, optional): Docstring for the created method.
        """
        registered_args = [GenericDriver.Arg(*a) for a in args]

        # Define a function that will be called with the arguments provided.
        # This is guaranteed to get the right number of arguments with defaults
        # already present because we will call it from a wrapper
        @with_lock
        @with_handler
        def func(self: GenericDriver, *args):
            arg_strings = []
            for arg, registered_arg in zip(args, registered_args):
                arg_strings.append(str(registered_arg.validator(arg)))

            cmd_string = self.command_separator.join([device_command] + arg_strings)

            logger.debug("Sending command '%s'", cmd_string)

            self.instr.flush()

            if response_parser:
                r = self.instr.query(cmd_string)

                # Validate the response if available
                if response_validator:
                    response_validator(r)

                # Return the parsed result
                return response_parser(r)
            else:
                self.instr.write(cmd_string)

        async def func_async(self, *args):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, partial(func, self, *args))

        logger.debug(
            "Registering method %s with coroutine = %s", method_name, coroutine
        )

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
        if coroutine:
            func_code_str = """async def wrapping_func({args}): return await func_async({args})""".format(
                args=all_arg_names
            )
        else:
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
        if not docstring:
            docstring = """
Query "{}"

This function is automatically generated. It will call the command "{}"
and expects you to pass it {} arguments named {}.
        """.format(
                method_name,
                device_command,
                len(args),
                [arg.name for arg in registered_args],
            ).strip()

        wrapping_func.__doc__ = docstring

        setattr(cls, method_name, wrapping_func)

    @with_lock
    @with_handler
    def check_connection(self):
        """Check the connection to the device

        You should override this method if you want checks in the setup

        Raises:
            Whatever errors you want to raise if the connection isn't working

        Returns:
            None
        """

    def ping(self):
        """
        The all-important ping function, without which ARTIQ will brutally kill our controller.
        """
        return True


# _register_query(Driver, "get_identity", "*idn", response_validator=None)
# _register_query(Driver, "get_status", "stat", response_parser=lambda x:
#                int(x, 2), response_validator=None)
# _register_query(Driver,
#                "get_version", "*git", response_parser=int, response_validator=None)

# # register_command(Driver, "calibrate", "CALI", response_validator=None)
# # _register_query(Driver, "set_measurement_mode", "MODE", response_parser=int, args=[('mode', int, ...)])
