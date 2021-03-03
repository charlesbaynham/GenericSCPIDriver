import logging
import argparse
import asyncio

from sipyco import common_args
from sipyco.pc_rpc import Server


def get_controller_func(name, default_port, driver_class, driver_kwargs={}):
    """Generate a function which will launch an ARTIQ controller for the provided class

    The generated controller will only accept "--id" and "--simulation" command-line parameters.

    Args:
        name (str): Name of the controller to launch
        default_port (int): Default port if not provided
        driver_class (object): Driver class. Probably a GenericDriver, but not required to be
        driver_kwargs (dict): Additional arguments to pass to the driver object constuctor

    Returns:
        function: A function to launch the controller
    """

    def main(extra_args=None):
        logging.getLogger(name).info("Launching controller %s", name)

        def get_argparser():
            parser = argparse.ArgumentParser(
                description="Generic controller for {}".format(name)
            )
            group = parser.add_argument_group(name)
            group.add_argument(
                "--id",
                required=True,
                type=str,
                help="VISA id to connect to. This Controller will obtain an exclusive lock.",
            )
            group.add_argument(
                "--simulation",
                action="store_true",
                help="Run this controller in simulation mode. ID will be ignored but is still required.",
            )
            common_args.simple_network_args(parser, default_port)
            common_args.verbosity_args(parser)

            return parser

        args = get_argparser().parse_args(extra_args)
        common_args.init_logger_from_args(args)

        driver_obj = driver_class(
            None, id=args.id, simulation=args.simulation, **driver_kwargs
        )

        loop = asyncio.get_event_loop()

        # Start an ARTIQ server for this device.
        #
        # Allow parallel connections so that functions which don't touch the
        # serial device can be done simultaneously: functions which do are
        # protected by @with_lock.
        server = Server(
            {name: driver_obj},
            description="An automatically generated server for {}".format(
                driver_class.__name__
            ),
            builtin_terminate=True,
            allow_parallel=True,
        )

        loop.run_until_complete(
            server.start(
                host=common_args.bind_address_from_args(args),
                port=args.port,
            )
        )

        try:
            loop.run_until_complete(server.wait_terminate())
        finally:
            try:
                loop.run_until_complete(server.stop())
            finally:
                # Close the VISA connection after the server has shutdown
                driver_obj.close()

            loop.close()

    return main
