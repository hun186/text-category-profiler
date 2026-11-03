"""Fail-closed local Windows Stage 4 acceptance port ownership checks."""
import socket
import unittest

from tools.stage4_candidate_desktop_acceptance import _port_is_available


class CandidateManualAcceptancePortTests(unittest.TestCase):
    def test_existing_loopback_listener_cannot_be_accepted(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]
            self.assertFalse(_port_is_available(port))

    def test_ephemeral_port_can_be_reserved_when_unoccupied(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.assertTrue(_port_is_available(port))


if __name__ == "__main__":
    unittest.main()
