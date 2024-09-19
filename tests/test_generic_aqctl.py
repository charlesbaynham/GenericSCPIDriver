import pytest
import argparse
import asyncio
import logging
from unittest.mock import patch, MagicMock
from generic_scpi_driver.generic_aqctl import get_controller_func


# Mock classes and functions
class MockDriver:
    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        pass


@pytest.fixture
def mock_server():
    with patch("generic_scpi_driver.generic_aqctl.Server") as MockServer:
        yield MockServer


@pytest.fixture
def mock_event_loop():
    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_until_complete = MagicMock()
        mock_loop.return_value.close = MagicMock()
        yield mock_loop


@pytest.fixture
def mock_common_args():
    with patch("generic_scpi_driver.generic_aqctl.common_args") as mock_common:
        mock_common.simple_network_args = MagicMock()
        mock_common.verbosity_args = MagicMock()
        mock_common.init_logger_from_args = MagicMock()
        mock_common.bind_address_from_args = MagicMock(return_value="localhost")
        yield mock_common


def test_main(mock_server, mock_event_loop, mock_common_args):
    name = "test_controller"
    default_port = 1234
    driver_class = MockDriver
    driver_kwargs = {}

    def mock_extra_arg_processor(parser):
        parser.add_argument("--extra", type=str, help="Extra argument")
        return ["extra"]

    main_func = get_controller_func(
        name, default_port, driver_class, driver_kwargs, mock_extra_arg_processor
    )

    test_args = [
        "prog",
        "--id",
        "test_id",
        "--simulation",
        # "--port",
        # "5678",
        "--extra",
        "extra_value",
    ]

    with patch("sys.argv", test_args):
        with patch("logging.getLogger") as mock_logger:
            mock_logger.return_value.info = MagicMock()

            main_func()

            mock_logger.return_value.info.assert_called_with(
                "Launching controller %s", name
            )
            mock_common_args.init_logger_from_args.assert_called()
            mock_server.assert_called_with(
                {name: mock_event_loop.return_value},
                description="An automatically generated server for MockDriver",
                builtin_terminate=True,
                allow_parallel=True,
            )
            mock_event_loop.return_value.run_until_complete.assert_called()
            mock_event_loop.return_value.close.assert_called()
