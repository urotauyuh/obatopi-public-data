"""WDG public schedule overlay. Literal data only; never execute downloaded JS."""
import ast
import copy
import re
from datetime import datetime, timezone

URL = 'https://www.owcsasia.com/competition.js'


def parse(js):
    match = re.search(r'^const COMPETITION = (\{.*?\n\});', js, re.S)
    if not match or '11.11—13' not in js or '11.20' not in js:
        raise ValueError('Unverified Asia Stage 3 schedule schema/date window')
    literal = re.sub(r'([{,]\s*)([A-Za-z][A-Za-z0-9_]*)\s*:', r"\1'\2':", match[1])
    value = ast.literal_eval(literal)
    if set(value['teams']) != {'KR1','KR2','KR3','KR4','JP1','JP2','JP3','PAC1'} or len(value['online']) != 3:
        raise ValueError('Asia participants or online days changed')
    return value


def apply(data, js, checked):
    config = parse(js)
    names = {t['name'].casefold():t['id'] for t in data['teams']}
    ids = {seed:names[name.casefold()] for seed,name in config['teams'].items()}
    out = copy.deepcopy(data)
    count = 0
    sid = 'wdg-asia-official-schedule'
    for day, fixtures in enumerate(config['online'], 11):
        if len(fixtures) != 4: raise ValueError('Unexpected daily fixture count')
        date = f'2026-11-{day:02d}'
        for time, group, first, second in fixtures:
            when = f'{date}T{time}:00+09:00'
            datetime.fromisoformat(when)
            found = [m for m in out['matches'] if m['date'] == date and {m['home'],m['away']} == {ids[first],ids[second]}]
            if len(found) != 1: raise ValueError('Official/supplemental Asia fixture mismatch')
            row = found[0]
            row.update(scheduledStartAt=when, timeKind='scheduled', group=group,
                       startAt=when if row['status']=='scheduled' else None)
            row['sourceIds'] = list(dict.fromkeys(row['sourceIds'] + [sid]))
            row['note'] = '日程・開始予定時刻はWDG公式。結果はOWTICS.GG補助資料。実開始時刻ではありません。'
            count += 1
    out['sources'] = [s for s in out['sources'] if s['id'] != sid] + [dict(
        id=sid, title='WDG公式：OWCS Asia Stage 3日程', url=URL,
        publisher='WDG / Overwatch Esports Asia', checkedAt=checked)]
    out['updateStatus']['officialScheduleCheckedAt'] = checked
    out['updateStatus']['officialScheduleMatchCount'] = count
    return out

