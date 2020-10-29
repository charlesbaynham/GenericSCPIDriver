from unittest.mock import Mock

import pytest

from generic_scpi_driver import GenericDriver


def test_driver_class_creation():
    class DumbDriver(GenericDriver):
        pass


def test_driver_method_registration_simple():
    class Driver(GenericDriver):
        pass

    Driver._register_query("get_identity", "*IDN?")


def test_driver_method_registration_output_parser():
    class Driver(GenericDriver):
        pass

    Driver._register_query("get_status", "STAT?", response_parser=int)
    Driver._register_query("get_status", "STAT?", response_parser=lambda x: int(x) * 10)


def test_driver_method_registration_input_parser():
    class Driver(GenericDriver):
        pass

    def validate_mode(mode):
        if not isinstance(mode, int) or mode < 1 or mode > 2:
            raise ValueError
        return mode

    Driver._register_query(
        "set_output_mode",
        "OUTP",
        args=[
            ("channel", None, None),
            ("mod", None, validate_mode),
            ("optional", True, None),
        ],
    )


def test_simulated_error():
    class Driver(GenericDriver):
        pass

    # Driver with one simple command
    Driver._register_query("get_identity", "*IDN?")

    # Error because we haven't set up simulation mode yet
    with pytest.raises(RuntimeError):
        Driver(id="anything", simulation=True)


def test__register_simulator():
    class Driver(GenericDriver):
        pass

    # Driver with one simple command
    Driver._register_query("get_identity", "*IDN?")

    # Register the simulator
    Driver._register_simulator(Mock)

    Driver(id="anything", simulation=True)


def test_calling():
    class Driver(GenericDriver):
        pass

    # Driver with one simple command
    Driver._register_query("get_identity", "*IDN?")
    Driver._register_query("get_version", "*VER?")

    # Register a simulator
    sim = Mock(unsafe=True)
    Driver._register_simulator(lambda: sim)

    d = Driver(id="anything", simulation=True)

    d.get_identity()
    sim.query.assert_called_with("*IDN?")

    d.get_version()
    sim.query.assert_called_with("*VER?")


def test_response():
    class Driver(GenericDriver):
        pass

    # Driver with one command
    Driver._register_query("get_identity", "*IDN?")

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock(return_value="Test device")

    Driver._register_simulator(lambda: sim)

    d = Driver(id="anything", simulation=True)

    assert d.get_identity() == "Test device"


def test_response_parsing():
    class Driver(GenericDriver):
        pass

    # Driver with one command
    Driver._register_query("get_identity", "*IDN?", response_parser=int)

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock(return_value="123")

    Driver._register_simulator(lambda: sim)

    d = Driver(id="anything", simulation=True)

    assert d.get_identity() == 123


def test_response_validation():
    class Driver(GenericDriver):
        pass

    def validator(v):
        v = int(v)
        if v > 100:
            raise ValueError
        return v

    Driver._register_query("get_identity", "*IDN?", response_parser=validator)

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock()

    Driver._register_simulator(lambda: sim)

    d = Driver(id="anything", simulation=True)

    sim.query.return_value = "10"
    assert d.get_identity() == 10

    sim.query.return_value = "potato"
    with pytest.raises(ValueError):
        d.get_identity()

    sim.query.return_value = "200"
    with pytest.raises(ValueError):
        d.get_identity()


def test_command_args():
    class Driver(GenericDriver):
        pass

    Driver._register_query("get_mode", "MODE?", args=[("channel", None)])

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock(return_value="on")

    Driver._register_simulator(lambda: sim)

    d = Driver(id="something", simulation=True)

    with pytest.raises(TypeError):
        d.get_mode()

    assert d.get_mode(1) == "on"
    sim.query.assert_called_with("MODE? 1")


def test_command_args_default():
    class Driver(GenericDriver):
        pass

    Driver._register_query("get_mode", "MODE?", args=[("channel", "1")])

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock(return_value="on")

    Driver._register_simulator(lambda: sim)

    d = Driver(id="something", simulation=True)

    assert d.get_mode() == "on"
    sim.query.assert_called_with("MODE? 1")


def test_command_args_default_multiple():
    class Driver(GenericDriver):
        pass

    Driver._register_query(
        "get_mode",
        "MODE?",
        args=[("a", None), ("b", "second_arg_default")],
    )

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock()

    Driver._register_simulator(lambda: sim)

    d = Driver(id="something", simulation=True)

    with pytest.raises(TypeError):
        d.get_mode()

    d.get_mode("first_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg_default")

    d.get_mode("first_arg", "second_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg")

    with pytest.raises(TypeError):
        d.get_mode(1, 2, 3)


def test_command_args_keywords():
    class Driver(GenericDriver):
        pass

    Driver._register_query(
        "get_mode",
        "MODE?",
        args=[("a", None), ("b", "second_arg_default")],
    )

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock()

    Driver._register_simulator(lambda: sim)

    d = Driver(id="something", simulation=True)

    with pytest.raises(TypeError):
        d.get_mode()

    d.get_mode("first_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg_default")

    d.get_mode(a="first_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg_default")

    d.get_mode("first_arg", "second_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg")

    d.get_mode("first_arg", b="second_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg")

    d.get_mode(a="first_arg", b="second_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg")

    d.get_mode(b="second_arg", a="first_arg")
    sim.query.assert_called_with("MODE? first_arg second_arg")

    with pytest.raises(TypeError):
        d.get_mode(a="first_arg", b="second_arg", c="something else")


def test_command_args_backwards():
    class Driver(GenericDriver):
        pass

    # Attempt to put an arg without a default value after one with a default
    with pytest.raises(ValueError):
        Driver._register_query(
            "get_mode",
            "MODE?",
            args=[
                ("b", "second_arg_default"),
                ("a", None),
            ],
        )


def test_command_args_validators():
    class Driver(GenericDriver):
        pass

    Driver._register_query(
        "get_mode",
        "MODE?",
        args=[("a", None, lambda num: "{:.1f}".format(num))],
    )

    # Register a simulator
    sim = Mock(unsafe=True)
    sim.query = Mock()

    Driver._register_simulator(lambda: sim)

    d = Driver(id="something", simulation=True)

    d.get_mode(a=1.123)
    sim.query.assert_called_with("MODE? 1.1")
