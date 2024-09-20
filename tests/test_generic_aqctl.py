import argparse
import asyncio
import logging
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from generic_scpi_driver.generic_aqctl import get_controller_func


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


def test_main(mock_server, mock_event_loop):
    name = "test_controller"
    default_port = 1234
    driver_kwargs = {}

    driver_class = MagicMock()
    driver_class.__name__ = "TestDriver"

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
        "--port",
        "5678",
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

            mock_server.assert_called()
            driver_class.assert_called_with(
                None, id="test_id", simulation=True, extra="extra_value"
            )
            mock_event_loop.return_value.run_until_complete.assert_called()
            mock_event_loop.return_value.close.assert_called()
