import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import update
from official_asia import parse


class CloudSafety(unittest.TestCase):
    def test_same_day_rematches_are_matched_by_fixture_id(self):
        from supplemental_adapter import CONFIG, seed, adapt
        slug, phases=CONFIG['pac']; ids=list(phases)
        a={'id':'a','name':'Alpha','abbreviation':'A'};b={'id':'b','name':'Beta','abbreviation':'B'}
        matches=[dict(id=str(i),scheduledAt='2026-11-09T00:00:00+00:00',phaseInfo={'id':pid,'name':'phase'},teamA=a,teamB=b,status='COMPLETED',format=fmt,result={'teamAScore':score[0],'teamBScore':score[1],'winner':a}) for i,(pid,fmt,score) in enumerate([(ids[0],'FT3',[3,0]),(ids[1],'FT4',[4,1])])]
        record={'sourceType':'third_party','sourceUrl':'https://owtics.gg/en-US/esports/tournament/'+slug,'retrievedAt':'2026-11-11T00:00:00Z','data':{'detailsUrl':'/esports/tournament/'+slug,'title':'2026 Stage 3','startDate':'2026-11-09','endDate':'2026-11-09','teams':[a,b],'phases':[{'id':x} for x in ids],'matches':matches,'placements':[],'standings':[]}}
        first=adapt(seed(record,'pac'),record,'pac');second=adapt(first,record,'pac')
        self.assertEqual([m['score'] for m in second['matches']],[[3,0],[4,1]])

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

