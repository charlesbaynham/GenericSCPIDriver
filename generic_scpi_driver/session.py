class Session:
    """
    A Session that encapsulates communication with a device

    Subclasses of Session are passed to :class:`~GenericDriver` and implements
    the hardware connection to your device. You don't need to define a new type
    of Session unless your device uses a communication protocol that isn't
    already implemented by this package.
    """

    def write(self, s: str) -> None:
        """
        Send a string to the device but do not expect a response
        """
        raise NotImplementedError

    def query(self, s: str) -> str:
        """
        Send a string to the device and expect a string response
        """
        raise NotImplementedError

    def flush(self) -> None:
        """
        Flush any communication buffers

        This method will be called after initial setup and before all commands.
        If your Session does not require this functionality, don't implement
        this function.
        """

    def close(self) -> None:
        """
        Terminate communication with the device

        This Session will not be used again after calling close: this method
        should clean up any resources used, e.g. closing connections.
        """
        raise NotImplementedError
