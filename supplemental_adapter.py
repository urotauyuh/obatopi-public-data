"""Isolated OWTICS supplemental adapter. Does not publish or alter roster facts.

Requires explicit caller authorization before using its output in production.
Network acquisition uses Python's default TLS verification; failures propagate.
"""
import copy
import datetime as dt
import urllib.request
import re
from probe_owtics import decode_html

CONFIG = {
 'pac': ('2026-owcs-asia-pacific-stage-3', {'Q29tcGV0aXRpb25QaGFzZToxNTU=':'regular','Q29tcGV0aXRpb25QaGFzZToxNTY=':'playoffs'}),
 'asia': ('2026-owcs-asia-stage-3-grand-finals', {'Q29tcGV0aXRpb25QaGFzZToxNjg=':'regular','Q29tcGV0aXRpb25QaGFzZToxNzE=':'seeding','Q29tcGV0aXRpb25QaGFzZToxNjk=':'playoffs'}),
 'jp': ('2026-owcs-asia-japan-stage-3', {'Q29tcGV0aXRpb25QaGFzZToxNTM=':'regular','Q29tcGV0aXRpb25QaGFzZToxNTQ=':'playoffs'}),
 'kr': ('2026-owcs-asia-korea-stage-3', {'Q29tcGV0aXRpb25QaGFzZToxNTc=':'regular','Q29tcGV0aXRpb25QaGFzZToxNTg=':'lcq','Q29tcGV0aXRpb25QaGFzZToxNTk=':'seeding','Q29tcGV0aXRpb25QaGFzZToxNjA=':'playoffs'}),
}

def seed(record, region):
    """Build only sourced team identities; no player/coach/roster facts."""
    if region not in ['pac','asia']:raise ValueError('Seeds restricted to new regions')
    teams=[]
    for t in record['data']['teams']:
        ident=re.sub('[^a-z0-9]+','-',t['name'].lower()).strip('-')
        teams.append({'id':ident,'name':t['name'],'short':t['abbreviation'],'players':[],'coaches':[],'logoUrl':t.get('logoUrl'),'sources':[record['sourceUrl']]})
    if len({x['id'] for x in teams})!=len(teams):raise ValueError('Ambiguous seed identifiers')
    return {'checkedAt':None,'region':region,'officialBroadcast':'https://www.youtube.com/@ow_esports_jp','season':{'name':record['data']['title'],'short':'2026 STAGE 3'},'coverage':{},'teams':teams,'matches':[],'standings':{'rows':[],'note':'順位は未確定。選手名簿は未確認。','sourceIds':[]},'events':[],'sources':[],'platforms':[],'updateStatus':{}}

def fetch(region):
    slug, _ = CONFIG[region]
    url = 'https://owtics.gg/en-US/esports/tournament/'+slug
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ObatopiSchedule/1.0'}),timeout=30) as response:
        body=response.read(3_000_001)
        if len(body)>3_000_000: raise ValueError('Response too large')
        data=decode_html(body.decode('utf-8'))
    return {'sourceType':'third_party','sourceUrl':url,'retrievedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'data':data}

def adapt(baseline, record, region):
    slug, phases = CONFIG[region]
    source_url='https://owtics.gg/en-US/esports/tournament/'+slug
    c=record['data']; now=record['retrievedAt']
    dt.datetime.fromisoformat(now)
    if record['sourceType']!='third_party' or record['sourceUrl']!=source_url or c['detailsUrl']!='/esports/tournament/'+slug:
        raise ValueError('Unverified competition or source')
    if not c['startDate'].startswith('2026-') or set(x['id'] for x in c['phases'])!=set(phases):
        raise ValueError('Unexpected season or phase schema')
    out=copy.deepcopy(baseline)
    names={x['name'].casefold():x['id'] for x in baseline['teams']}
    if len(names)!=len(baseline['teams']):raise ValueError('Ambiguous baseline teams')
    teammap={}
    for t in c['teams']:
        name=t['name'].casefold()
        if name not in names: raise ValueError('Unknown roster team: '+t['name'])
        teammap[t['id']]=names[name]
    if set(teammap.values()) != set(names.values()):raise ValueError('Incomplete team field')
    def team(t):
        if not t or t['id'] not in teammap:raise ValueError('Unresolved team')
        if t.get('name') and names.get(t['name'].casefold())!=teammap[t['id']]:raise ValueError('Team ID/name mismatch')
        return teammap[t['id']]
    source_id='owtics-'+region+'-2026-s3-supplement'
    existing={}
    by_id={m['id']:m for m in baseline['matches']}
    for m in baseline['matches']:
        existing.setdefault((m['date'],frozenset([m['home'],m['away']])),[]).append(m)
    matches=[]; seen=set(); identities=set(); unresolved=[]
    for m in c['matches']:
        if m['id'] in seen:raise ValueError('Duplicate match ID')
        seen.add(m['id'])
        pid=m['phaseInfo']['id']
        if pid not in phases:raise ValueError('Unknown phase')
        if not m['teamA'] or not m['teamB']:
            if m['status']!='UPCOMING':raise ValueError('Unresolved completed/live sides')
            unresolved.append(m['id']);continue
        a,b=team(m['teamA']),team(m['teamB'])
        if a==b:raise ValueError('Identical sides')
        stamp=dt.datetime.fromisoformat(m['scheduledAt']); date=stamp.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
        # Source range has no timezone. Accept its UTC or JST calendar day;
        # the displayed fixture date always derives from explicit UTC timestamp.
        source_days=[date,stamp.astimezone(dt.timezone.utc).date().isoformat()]
        if not any(c['startDate']<=d<=c['endDate'] for d in source_days):raise ValueError('Date outside competition range')
        identity=(date,frozenset([a,b]),pid)
        if identity in identities:raise ValueError('Duplicate match sides/date/phase')
        identities.add(identity)
        if m['status'] not in ['COMPLETED','UPCOMING','LIVE']:raise ValueError('Unknown match status')
        score=None
        if m['status']=='COMPLETED':
            r=m['result'];score=[r['teamAScore'],r['teamBScore']]
            if m['format'] not in ['FT3','FT4']:raise ValueError('Unknown format')
            target=int(m['format'][2:])
            if any(type(n)!=int or n<0 or n>target for n in score) or score[0]==score[1] or max(score)!=target:raise ValueError('Invalid score')
            winner=m['teamA']['id'] if score[0]>score[1] else m['teamB']['id']
            if r['winner']['id']!=winner:raise ValueError('Winner mismatch')
        stable_id=region+'-2026-s3-owtics-'+m['id'].replace('=','')
        old=by_id.get(stable_id)
        if old is None:
            legacy=[x for x in existing.get((date,frozenset([a,b])),[]) if '-owtics-' not in x['id']]
            if len(legacy)>1: raise ValueError('Ambiguous legacy fixture; review required')
            old=legacy[0] if legacy else None
        if old and old['status']=='completed':
            oldscore=old['score'] if old['home']==a else old['score'][::-1]
            if score!=oldscore:raise ValueError('Regression or score conflict with checked baseline')
        row={'id':region+'-2026-s3-owtics-'+m['id'].replace('=',''),'date':date,'startAt':None,'phase':phases[pid],'round':m['phaseInfo'].get('label') or m['phaseInfo']['name'],'home':a,'away':b,'score':score,'status':{'COMPLETED':'completed','UPCOMING':'scheduled','LIVE':'in-progress'}[m['status']],'format':m['format'],'sourceIds':[source_id],'note':'OWTICS.GG補助資料。日時は予定日時に基づく日付で、実開始時刻は未確認。','scheduledAt':m['scheduledAt']}
        if old:
            for field in ['archiveUrl']:
                if old.get(field):row[field]=old[field]
            row['sourceIds']=list(dict.fromkeys(old.get('sourceIds',[])+[source_id]))
        matches.append(row)
    for old in baseline['matches']:
        if old['status']=='completed' and (old['date'],frozenset([old['home'],old['away']])) not in {(x['date'],frozenset([x['home'],x['away']])) for x in matches}:raise ValueError('Checked completed match disappeared')
    known={m['id'] for m in baseline['matches'] if '-owtics-' in m['id']}
    if not known.issubset({m['id'] for m in matches}): raise ValueError('Known fixture disappeared')
    previous=baseline.get('updateStatus',{}).get('supplementalMatchCount',0)
    if len(matches)+len(unresolved)<previous:raise ValueError('Match count regression')
    out['region']=region
    out['matches']=matches
    complete=matches and not unresolved and all(x['status']=='completed' for x in matches)
    placements=[]
    for p in c['placements']:
        for t in p['teams']:
            placements.append({'rank':p['placementStart'],'rankEnd':p['placementEnd'],'team':team(t)})
    if complete and len(placements)==len(teammap) and len({x['team'] for x in placements})==len(teammap):
        out['standings']={'kind':'final','rows':placements,'note':'Stage 3大会最終順位。OWTICS.GG補助資料。勝敗は工程が異なるため合算しません。','sourceIds':[source_id]}
    # Preserve phase and round on supplementary regular-season rows, not a final-table inference.
    out['supplementalStandings']=[{**s,'teamId':team(s['team'])} for s in c['standings']]
    out['sources']=[s for s in out['sources'] if s['id']!=source_id]+[{'id':source_id,'title':'OWTICS.GG補助資料：2026 Stage 3 '+region.upper(),'url':source_url,'publisher':'OWTICS.GG（第三者・補助資料）','checkedAt':now,'note':'公式順位表ではありません。公開構造化データを取得。'}]
    out.setdefault('coverage',{})['note']='2026 Stage 3の対戦確定'+str(len(matches))+'試合をOWTICS.GG補助資料で補完。対戦未確定'+str(len(unresolved))+'枠。選手情報の確認日は既存記録のままです。'
    final_current=bool(complete and len(placements)==len(teammap) and len({x['team'] for x in placements})==len(teammap))
    out.setdefault('updateStatus',{}).update({'mode':'daily-program','automaticRefreshConfigured':True,'liveTrackingConfigured':False,'matchesCheckedAt':now,'standingsCheckedAt':now if final_current else None,'standingsTeamCount':len(placements) if final_current else 0,'sourceType':'third_party','supplementalCheckedAt':now,'supplementalMatchCount':len(matches)+len(unresolved),'resolvedMatchCount':len(matches),'unresolvedMatchIds':unresolved,'supplementalSource':'OWTICS.GG（第三者・補助資料）'})
    return out

