Generic SCPI driver
===================

.. image:: https://img.shields.io/pypi/pyversions/generic-scpi-driver
   :alt: PyPI - Python Version

A generic driver generator for devices controlled via (virtual) COM ports using SCPI commands.
Creates a python class for controlling your device. 

This class is compatible with the ARTIQ experimental control system and,
if desired, a network ARTIQ controller is also generated. 

Installation
------------

Install the package and its dependancies with::

    pip install generic-scpi-driver


If you'd like to use the ARTIQ network controller generation, instead install with::

    pip install generic-scpi-driver[artiq]

Usage
-----

Basics
######

To make a driver, simply inherit from the GenericDriver class. To define commands, call
`_register_query` on the class (not on objects of the class). For example:

.. code-block:: python

    from generic_scpi_driver import GenericDriver

    class SimpleDriver(GenericDriver):
        '''A driver for my simple SCPI device'''

    SimpleDriver._register_query("get_identity", "*IDN")

This creates a class called ``SimpleDriver`` which has a constuctor ``__init__``, a ``close()`` method
and a new method called ``get_identity()`` which takes no parameters and returns a string. You could open a connection to your device like this:

.. code-block:: python

    dev = SimpleDriver(
        id="COM10",
        baud_rate=57600
    )

    # This sends the command "*IDN\n" to the device and returns the response
    identity = dev.get_identity()

Parameters
##########

For more complex commands, you can specify parameters for the command:

.. code-block:: python

    SimpleDriver._register_query(
        "set_voltage",
        "VOLT",
        args=[
            GenericDriver.Arg(name="channel"),
            GenericDriver.Arg(name="voltage"),
        ]
    )

This would allow you to call:

.. code-block:: python

    # Using positional arguments
    dev.set_voltage(0, 5.4)

    # ...or keyword arguments
    dev.set_voltage(channel=0, voltage=5.4)

Parameters can be validated by passing a custom function (which may accept any
single parameter and must return a string to be sent to the device, or throw an error):

.. code-block:: python

    def check_voltage_in_limits(v):
        voltage = float(v)
        if voltage > 10:
            raise ValueError("Voltage too high")
        return str(voltage)

    SimpleDriver._register_query(
        "set_voltage",
        "VOLT",
        args=[
            GenericDriver.Arg(name="channel", validator=lambda: str(int(x))),
            GenericDriver.Arg(name="voltage", validator=check_voltage_in_limits, default=0.0,
        ]
    )

Return values
#############

Return values are, by default, the string returned by the SCPI device in response to your command. 
If you'd prefer to process these, you can pass a ``response_parser`` function:

.. code-block:: python

    SimpleDriver._register_query(
        "count_foobars",
        "COUN",
        response_parser=int,
    )

    SimpleDriver._register_query(
        "list_foobars",
        "LIST",
        response_parser=lambda x: x.split(","),
    )

If your device doesn't give any response at all, you can set
``response_parser=None`` and the driver won't attempt to listen for a respose. 

Error checking
##############

You can also add error checking to your commands. Pass a function as
``response_validator`` and it will be called with the output from the device
(not the parsed output of ``response_parser``) as its input. The
``response_validator``'s return value will be ignored: it's only job is to raise
an exception if needed. E.g.

.. code-block:: python

    def check_for_error(s):
        if "error" in s.lower():
            raise RuntimeError("Error returned by device: {}".format(s))
    
    SimpleDriver._register_query(
        "do_something",
        "DOOO",
        response_validator=check_for_error,
    )

Asyncronous operation
#####################

By default, all methods are syncronous. If you'd prefer async operation, pass ``coroutine=True`` 
to ``_register_query``. This creates a new thread for the serial call and returns an ``asyncio``
coroutine. Note that you have to call these using an async loop which is a whole topic of python
programming. This is particularly useful for ARTIQ drivers, since ARTIQ handles coroutines
automatically. 

Custom methods
##############

The method generation is intended to be quite flexible, but if you really need custom logic there's
nothing to stop you writing your own methods. You can use ``self.instr`` to access the
``pyvisa.Resource`` for your device. Use the wrappers ``with_handler`` to cause the driver to issue a
VISA ``.flush()`` if an error occurs and ``with_lock`` to ensure that only one method access the device
at a time (only relevant in multi-threaded applications). 

.. code-block:: python

    from generic_scpi_driver import GenericDriver, with_lock, with_handler

    class SimpleDriver(GenericDriver):
        '''A driver for my simple SCPI device'''

        @with_handler
        @with_lock
        def do_complex_thing(self):
            '''Do something complex'''
            response = self.instr.query("COMP 1 2 3")
            return int(response) + 5

Startup checking
################

It can be useful to check on startup if communicatio with a device has been
established successfully. To do this, define a method in the class called
``check_connection``. Return value is ignored, but this method will be called
when the object is constucted and has the chance to raise an exception. Example:

.. code-block:: python

    from generic_scpi_driver import GenericDriver, with_lock, with_handler

    class SimpleDriver(GenericDriver):
        '''A driver for my simple SCPI device'''

        def check_connection(self):
            idn = self.get_identity()
            if idn != "My device":
                raise RuntimeError(f"Bad device identity: got '{idn}'")

    # Note that it's fine to define functions later which get used in methods
    # defined previously
    SimpleDriver._register_query("get_identity", "*IDN")

Simulation mode
###############

The constuctor accepts a keyword parameter ``simulation=True`` to return a simulation device, for running
offline unit tests. This won't work unless you also register a simulator device with a method ``query`` which
takes a string and returns a string. For example:

.. code-block:: python

    class Simulator:
        def query(s):
            if s == "*IDN":
                return "Simulator device"
            else:
                return "ERROR"

    class SimpleDriver(GenericDriver):
        pass

    SimpleDriver._register_simulator(Simulator)
    SimpleDriver._register_query("get_identity", "*IDN")

    dev = SimpleDriver(id="fake", simulation=True)

    dev.get_identity()  # returns "Simulator device"

ARTIQ Controllers
#################

To get a network controller for use by the ARTIQ controller manager, just make a python module like:

.. code-block:: python

    from generic_scpi_driver import get_controller_func

    from .my_driver import SimpleDriver

    # Makes a controller called "SimpleDriver" which listens to port 3300 by default
    main = get_controller_func("SimpleDriver", 3300, SimpleDriver)


    if __name__ == "__main__":
        main()

Register this ``main`` function in your ``setup.py`` like so:

.. code-block:: python

    setup(
        ...
        entry_points={
            "console_scripts": [
                "artiq_simple_device=my_driver_package.my_driver_controller:main",
            ]
        },
    )

After installing your package using `pip install -e .` as normal, you should be able to call
``artiq_simple_device`` on the command line to launch a controller for your device. 

Development
-----------

For developing the package, you'll need a few more packages. Install with::

    pip install -e .[dev,artiq]

Authors
-------

`generic_scpi_driver` was written by `Charles Baynham <charles.baynham@npl.co.uk>`_.
