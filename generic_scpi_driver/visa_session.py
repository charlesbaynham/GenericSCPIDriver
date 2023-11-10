import logging
import re
import time

import pyvisa
from serial.tools.list_ports import grep as grep_serial_ports

from .session import Session

logger = logging.getLogger(__name__)


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


class VISASession(Session):
    def __init__(
        self,
        id,
        baud_rate,
        read_termination="\n",
        write_termination="\n",
        timeout=None,
        wait_after_connect=0.0,
    ) -> None:
        self.visa_instr = self._setup_device(
            id=id,
            baud_rate=baud_rate,
            read_termination=read_termination,
            write_termination=write_termination,
            timeout=timeout,
            wait_after_connect=wait_after_connect,
        )

    @staticmethod
    def _setup_device(
        id,
        baud_rate,
        read_termination="\n",
        write_termination="\n",
        timeout=None,
        wait_after_connect=0.0,
    ):
        """Open a visa connection to the device

        Params:
            wait_after_connect - Time to wait after opening the connection before flushing it [s]

        Raises:
            RuntimeError: Raised if VISA comms fail

        :rtype: :class:pyvisa.resources.Resource
        """
        id_resolved = get_com_port_by_hwid(id)

        if id_resolved.lower() == id.lower():
            logger.warning(
                (
                    "Initiated device from COM port: it would be more "
                    'robust to use the HWID instead. For "%s", that\'s "%s"'
                ),
                id,
                id_resolved,
            )

        logger.debug("Found device %s on COM port %s", id, id_resolved)

        # Get a handle to the instrument
        rm = pyvisa.ResourceManager("@py")

        logger.debug(f"Devices: {rm.list_resources()}")

        # pyvisa-py doesn't have "COM" aliases for ASRL serial ports, so convert
        regex_match = re.match(r"^com(\d{1,3})$", id_resolved.lower())
        if regex_match:
            id_resolved = f"ASRL{regex_match[1]}"

        logger.debug(f"Connecting to : {id_resolved}")

        instr = rm.open_resource(id_resolved)

        logger.debug(f"Connection: {instr}")

        # Configure the connection as required

        logger.debug(
            "Setting up connection with baud %s, write_term %s and read_term %s",
            baud_rate,
            repr(write_termination),
            repr(read_termination),
        )

        instr.baud_rate = baud_rate
        if read_termination:
            instr.read_termination = read_termination
        if write_termination:
            instr.write_termination = write_termination
        if timeout:
            instr.timeout = timeout
        # instr.data_bits = 8
        # instr.stop_bits = pyvisa.constants.StopBits.one
        # instr.parity = pyvisa.constants.Parity.none
        # instr.flow_control = visa.constants.VI_ASRL_FLOW_NONE

        if wait_after_connect:
            time.sleep(wait_after_connect)

        logger.debug('Device "{}" init complete'.format(id))

        return instr

    def flush(self):
        logger.debug("Flushing visa interface with device %s", self.visa_instr)
        self.visa_instr.flush(
            pyvisa.constants.VI_READ_BUF_DISCARD
            | pyvisa.constants.VI_WRITE_BUF_DISCARD
            | pyvisa.constants.VI_IO_IN_BUF_DISCARD
            | pyvisa.constants.VI_IO_OUT_BUF_DISCARD
        )

    def write(self, s: str) -> None:
        self.visa_instr.write(s)

    def query(self, s: str) -> str:
        return self.visa_instr.query(s)

    def close(self) -> None:
        self.visa_instr.close()
