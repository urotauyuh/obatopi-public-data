import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import update
from official_asia import parse


class CloudSafety(unittest.TestCase):
    def test_regional_failure_preserves_last_good_data(self):
        baseline={'schemaVersion':1,'regions':{r:{'marker':r} for r in ['na','emea','jp','kr','cn','pac','asia']}}
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'data.json').write_text(json.dumps(baseline))
            with patch.object(update,'download',side_effect=OSError('upstream unavailable')), patch('cn_adapter.refresh',side_effect=OSError('cn unavailable')), patch('supplemental_adapter.fetch',side_effect=OSError('supplement unavailable')):
                self.assertFalse(update.run(p))
            result=json.loads((p/'data.json').read_text())
            self.assertEqual(result['regions'],baseline['regions'])
            self.assertEqual(result['refresh']['aiCalls'],0)
            self.assertEqual(set(result['refresh']['automatedRegions']),set(baseline['regions']))
            self.assertIn('cn',result['refresh']['errors'])
            self.assertIn('jp',result['refresh']['errors'])

    def test_official_javascript_is_never_executed(self):
        with self.assertRaises((ValueError,SyntaxError)):
            parse("const COMPETITION = {teams:evil(),online:[]\n}; 11.11—13 11.20")


if __name__=='__main__':
    unittest.main()

