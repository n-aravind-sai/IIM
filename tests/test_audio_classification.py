import unittest
from unittest.mock import patch

from worker.detectors import AudioCaptureDetector
from worker.models import score


class AudioClassificationTests(unittest.TestCase):
    def scan(self, *names):
        with patch('worker.detectors.native.audio_devices', return_value=[{'name': n, 'inputs': 2} for n in names]):
            return AudioCaptureDetector().scan({})

    def test_stereo_mix_is_informational_and_never_deducts_from_index(self):
        result = self.scan('Stereo Mix (Realtek High Definition Audio)')
        self.assertEqual(len(result.signals), 1)
        self.assertEqual(result.signals[0].weight, 0)
        self.assertEqual(result.signals[0].evidence['classification'], 'hardware_loopback')
        self.assertEqual(score([result])['value'], 100)

    def test_routing_device_presence_remains_explicitly_unattributed(self):
        result = self.scan('BlackHole 2ch')
        self.assertEqual(result.signals[0].evidence['classification'], 'virtual_routing')
        self.assertIn('Installed does not mean active', result.signals[0].limitation)
        self.assertIsNone(result.metrics['capture_conflicts'])

    def test_bluetooth_and_ordinary_microphones_are_not_adverse_signals(self):
        result = self.scan('Bluetooth Headset Microphone', 'USB Microphone')
        self.assertEqual(result.signals, [])

    def test_benign_loopback_does_not_hide_a_separate_routing_observation(self):
        result = self.scan('Stereo Mix', 'CABLE Output')
        self.assertEqual({s.evidence['classification'] for s in result.signals},
                         {'hardware_loopback', 'virtual_routing'})
