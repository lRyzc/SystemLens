import subprocess
import unittest
from unittest.mock import patch

from systemlens.hardware import clean, discover, normalize


class HardwareTests(unittest.TestCase):
    def test_cim_singletons_arrays_missing_fields(self):
        result = normalize({'cpu': {'Name': '  Example CPU  '}, 'memory': [
            {'PartNumber': ' RAM-123 ', 'Capacity': '17179869184', 'ConfiguredClockSpeed': 6000},
            {'PartNumber': 'Unknown', 'Capacity': 0}], 'disks': None, 'graphics': []})
        self.assertEqual(result['cpu'][0]['model'], 'Example CPU')
        self.assertEqual(result['memory'][0]['capacity'], 16 * 1024**3)
        self.assertEqual(result['memory'][0]['speed_mts'], 6000)
        self.assertIsNone(result['memory'][1]['model'])
        self.assertIsNone(result['memory'][1]['capacity'])
        self.assertEqual(result['disks'], [])

    def test_placeholders_do_not_become_model_names(self):
        self.assertIsNone(clean('To Be Filled By O.E.M.'))
        self.assertIsNone(clean(None))
        self.assertEqual(clean('RTX 2070 SUPER'), 'RTX 2070 SUPER')

    @patch('systemlens.hardware.platform.system', return_value='Linux')
    @patch('systemlens.hardware.subprocess.run')
    def test_other_platforms_do_not_launch_powershell(self, run, _):
        self.assertEqual(discover()['status'], 'unsupported')
        run.assert_not_called()

    @patch('systemlens.hardware.platform.system', return_value='Windows')
    @patch('systemlens.hardware.subprocess.run', side_effect=subprocess.TimeoutExpired('powershell', 25))
    @patch.dict('sys.modules', {'winreg': None})
    def test_query_timeout_preserves_a_valid_payload(self, *_):
        result = discover()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['memory'], [])
        self.assertEqual(result['graphics'], [])


if __name__ == '__main__':
    unittest.main()
