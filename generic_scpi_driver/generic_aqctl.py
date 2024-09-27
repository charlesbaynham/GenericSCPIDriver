import argparse
import asyncio
import logging

from sipyco import common_args
from sipyco.pc_rpc import Server


def get_controller_func(
    name, default_port, driver_class, driver_kwargs={}, extra_arg_processor=lambda _: []
):
    """
    Generate a function which will launch an ARTIQ controller for the provided class

    The generated controller will only accept "--id" and "--simulation" command-line parameters.

    Args:
        name (str): The name of the controller.
        default_port (int): The default port number for the controller.
        driver_class (type): The class of the driver to be used.
        driver_kwargs (dict, optional): Additional keyword arguments to pass to the driver class. Defaults to {}.
        extra_arg_processor (function, optional): Function that will be called and passed the ArgumentParser so that extra arguments can be added to the command line. Must return a list of strings of the names of the parameters added. . Defaults to a lambda that returns an empty list.
    Returns:
        function: The main function for the controller.
    """

    def main():
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

        args_parser = get_argparser()

        # Call the extra arg processor to add any extra arguments to the command
        # line. This will return a list of the arguments which were added
        extra_args = extra_arg_processor(args_parser)

        args = args_parser.parse_args()
        common_args.init_logger_from_args(args)

        extra_arg_values = {k: getattr(args, k) for k in extra_args}

        # Merge driver_kwargs and extra_arg_values
        merged_kwargs = {**driver_kwargs, **extra_arg_values}

        driver_obj = driver_class(
            None, id=args.id, simulation=args.simulation, **merged_kwargs
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
