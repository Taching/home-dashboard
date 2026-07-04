import unittest
from unittest.mock import patch

from app.domain.bluetooth_audio import BluetoothAudioService


SAMPLE_PACTL_SINKS = """
Sink #66
	Name: alsa_output.usb-0c76_USB_Microphone-00.analog-stereo
	Description: USB Microphone Analog Stereo

Sink #78
	Name: bluez_output.78_2B_64_77_F3_DB.1
	Description: Bose Revolve taching
"""


class BluetoothAudioServiceTests(unittest.TestCase):
    def test_connected_bluetooth_default_output(self):
        service = BluetoothAudioService()
        with patch.object(service, "_run", side_effect=[
            "bluez_output.78_2B_64_77_F3_DB.1\n",
            SAMPLE_PACTL_SINKS,
        ]):
            snapshot = service.snapshot()

        self.assertEqual(snapshot.status, "connected")
        self.assertEqual(snapshot.device_name, "Bose Revolve taching")
        self.assertTrue(snapshot.is_default_output)

    def test_connected_bluetooth_not_default(self):
        service = BluetoothAudioService()
        with patch.object(service, "_run", side_effect=[
            "alsa_output.usb-0c76_USB_Microphone-00.analog-stereo\n",
            SAMPLE_PACTL_SINKS,
        ]):
            snapshot = service.snapshot()

        self.assertEqual(snapshot.status, "connected")
        self.assertEqual(snapshot.device_name, "Bose Revolve taching")
        self.assertFalse(snapshot.is_default_output)

    def test_disconnected_when_no_bluetooth_sink(self):
        service = BluetoothAudioService()
        with patch.object(service, "_run", side_effect=[
            "alsa_output.usb-0c76_USB_Microphone-00.analog-stereo\n",
            "Sink #66\n\tName: alsa_output.usb-0c76_USB_Microphone-00.analog-stereo\n",
        ]):
            snapshot = service.snapshot()

        self.assertEqual(snapshot.status, "disconnected")
        self.assertIsNone(snapshot.device_name)
        self.assertFalse(snapshot.is_default_output)


if __name__ == "__main__":
    unittest.main()
