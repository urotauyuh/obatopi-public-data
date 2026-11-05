"""Fetch public OWCS records without an AI/API key. Publish only validated snapshots."""
import argparse
import copy
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCHEDULE = 'https://esports.overwatch.com/en-us/schedule'
RANKINGS = 'https://esports.overwatch.com/en-us/rankings'
JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent


def hydration_objects(html):
    chunks = []
    for match in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)</script>', html, re.S):
        value = json.loads(match[1])
        if len(value) > 1 and isinstance(value[1], str):
            chunks.append(value[1])
    if not chunks:
        raise ValueError('Official page structure changed: no public hydration data')
    for line in ''.join(chunks).splitlines():
        try:
            yield json.loads(line.partition(':')[2])
        except ValueError:
            continue


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def schedule_records(html):
    records = {}
    for root in hydration_objects(html):
        for value in walk(root):
            fields = value.get('fields')
            if isinstance(fields, dict) and 'datetime' in fields and 'matchId' in fields:
                key = fields['matchId']
                # Official payload can repeat a record. Conflicting copies are unsafe.
                public = {k: fields.get(k) for k in (
                    'matchId', 'datetime', 'matchStatus', 'team1Name', 'team2Name',
                    'Team 1 Score', 'Team 2 Score', 'region', 'event', 'Stage Name',
                    'Phase Name', 'YouTube Stream Link', 'Twitch Stream Link')}
                if key in records and records[key] != public:
                    raise ValueError('Conflicting official match records')
                records[key] = public
    if not records:
        raise ValueError('Official schedule contained no match records')
    return list(records.values())


def ranking_blocks(html):
    blocks = {}
    for root in hydration_objects(html):
        for value in walk(root):
            if isinstance(value.get('rankingTables'), list) and value.get('title'):
                blocks[value.get('_uid', value['title'])] = value
    if not blocks:
        raise ValueError('Official rankings contained no tables')
    return list(blocks.values())


def norm(name):
    return re.sub(r'[^a-z0-9]', '', str(name).casefold())


def team_map(data):
    names = {}
    for team in data['teams']:
        key = norm(team['name'])
        if key in names:
            raise ValueError('Ambiguous team mapping')
        names[key] = team['id']
    return names


def score(fields):
    status = fields['matchStatus']
    if status in ('scheduled', 'in-progress'):
        return status, None
    if status != 'completed':
        raise ValueError('Unknown official match status')
    result = [fields['Team 1 Score'], fields['Team 2 Score']]
    if (any(type(n) is not int or n < 0 or n > 4 for n in result)
            or max(result) not in (3, 4) or result[0] == result[1]):
        raise ValueError('Invalid completed-match score')
    return status, result


def update_region(original, region, records, blocks, checked):
    data = copy.deepcopy(original)
    names = team_map(data)
    expected_stage = 'Stage 3'  # Versioned coverage; never mix another season/stage.
    eligible = [r for r in records if r.get('region') == region
                and r.get('Stage Name') == expected_stage
                and str(r.get('datetime', '')).startswith('2026-')]
    if not eligible:
        raise ValueError('Expected regional season absent; previous snapshot retained')
    matches = {m['id']: m for m in data['matches']}
    previous = {m.get('officialMatchId'): m for m in data['matches'] if m.get('officialMatchId')}
    source_id = 'official-schedule-daily'
    unresolved = []
    for row in eligible:
        first = (row.get('team1Name') or [None])[0]
        second = (row.get('team2Name') or [None])[0]
        a, b = names.get(norm(first)), names.get(norm(second))
        if not a or not b:
            unresolved.append(row['matchId'])
            continue
        if a == b:
            raise ValueError('Same-team fixture')
        status, result = score(row)
        when = datetime.fromisoformat(row['datetime'].replace('Z', '+00:00'))
        if when.tzinfo is None:
            raise ValueError('Official datetime has no timezone')
        old = previous.get(row['matchId'])
        if old and old.get('status') == 'completed' and status != 'completed':
            raise ValueError('Official completed result regressed')
        match = copy.deepcopy(old) if old else {'id': f'{region}-2026-s3-{row["matchId"]}'}
        playoff = row.get('event') == 'Playoffs'
        match.update(date=when.astimezone(JST).date().isoformat(), startAt=row['datetime'],
                     phase='playoffs' if playoff else 'regular',
                     round=row.get('Phase Name') or row.get('event') or 'Stage 3',
                     home=a, away=b, score=result, status=status,
                     sourceIds=[source_id], format='Stage 3 / ' + str(row.get('event') or ''),
                     archiveUrl=match.get('archiveUrl'), officialMatchId=row['matchId'],
                     watchUrl=row.get('YouTube Stream Link') or data['officialBroadcast'],
                     timeKind='scheduled',
                     note='開始時刻は公式の予定時刻です。実開始時刻とは区別しています。')
        matches[match['id']] = match
    data['matches'] = sorted(matches.values(), key=lambda m: (m['date'], m.get('startAt') or '', m['id']))
    data['sources'] = [s for s in data['sources'] if s['id'] not in (source_id, 'official-rankings-daily')]
    data['sources'].append(dict(id=source_id, title='Overwatch Esports公式 日程・結果',
                                url=SCHEDULE, checkedAt=checked, publisher='Overwatch Esports'))
    table_candidates = [(block, table) for block in blocks
                        if re.match(r'^Stage 3 Rankings\b', block['title'])
                        for table in block['rankingTables'] if table.get('title', '').lower() == region]
    if len(table_candidates) != 1:
        raise ValueError('Expected official ranking table is not unique')
    block, table = table_candidates[0]
    ranking = []
    for position, row in enumerate(table['rows'], 1):
        team = names.get(norm(row['team'][0]['name']))
        stats = {s['title'][0]['name']: s['value'] for s in row['stats']}
        if not team or not re.fullmatch(r'\d+', str(stats.get('Wins', ''))) or not re.fullmatch(r'\d+', str(stats.get('Losses', ''))):
            raise ValueError('Ranking team or W/L invalid')
        ranking.append(dict(rank=position, team=team, wins=int(stats['Wins']),
                            losses=int(stats['Losses']), mapDifference=stats.get('Map', '')))
    if len(ranking) != len(names) or len({r['team'] for r in ranking}) != len(names):
        raise ValueError('Official ranking coverage mismatch')
    note = f'公式掲載表「{block["title"]}」の順序・勝敗です。以後のプレーオフ結果から順位を再計算していません。'
    data['standings'].update(rows=ranking, kind='regular', note=note,
                             sourceUpdatedLabel=block['title'], sourceIds=['official-rankings-daily'])
    data['sources'].append(dict(id='official-rankings-daily', title=block['title'], url=RANKINGS,
                                checkedAt=checked, publisher='Overwatch Esports', note=note))
    # Roster freshness is intentionally not advanced by a score-only fetch.
    data['updateStatus'] = dict(mode='daily-program', automaticRefreshConfigured=True,
        matchesCheckedAt=checked, standingsCheckedAt=checked, rosterCheckedAt=original.get('checkedAt'),
        unresolvedOfficialMatches=unresolved, liveTrackingConfigured=False)
    return data


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'ObatopiPublicData/1.0'})
    with urllib.request.urlopen(request, timeout=40) as response:
        if response.status != 200:
            raise ValueError('Official source unavailable')
        body = response.read(5_000_001)
    if len(body) > 5_000_000:
        raise ValueError('Official source too large')
    return body.decode('utf-8')


def run(folder, fixture=None):
    checked = datetime.now(timezone.utc).isoformat()
    target = folder / 'data.json'
    baseline = json.loads((target if target.exists() else folder / 'seed.json').read_text('utf-8'))
    result = copy.deepcopy(baseline)
    errors = {}
    try:
        html = lambda key, url: (fixture / (key + '.html')).read_text('utf-8') if fixture else download(url)
        records = schedule_records(html('schedule', SCHEDULE))
        tables = ranking_blocks(html('rankings', RANKINGS))
        for region in ('na', 'emea'):
            try:
                result['regions'][region] = update_region(baseline['regions'][region], region, records, tables, checked)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                errors[region] = str(exc)
    except Exception as exc:
        errors['official'] = type(exc).__name__ + ': ' + str(exc)
    result['refresh'] = dict(attemptedAt=checked, errors=errors, aiCalls=0,
        automatedRegions=['na', 'emea'], manualRegions=['jp', 'kr', 'cn'],
        schedule='00:00 Asia/Tokyo', scope='2026 Stage 3; matches and official standings; roster unchanged')
    # One atomic replacement means interrupted runs never publish truncated JSON.
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(encoded, 'utf-8')
    temporary.replace(target)
    print(json.dumps({'ok': not errors, 'errors': errors, 'aiCalls': 0,
                      'sha256': hashlib.sha256(encoded.encode()).hexdigest()}))
    return not errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path)
    options = parser.parse_args()
    raise SystemExit(0 if run(ROOT, options.fixture) else 1)
