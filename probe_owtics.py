"""Read-only THIRD-PARTY discovery. No site publication; no AI/API usage.
Fetches public HTML with Windows curl (system TLS), decodes React Router data.
"""
import datetime, json, re
from pathlib import Path

OUT = Path(__file__).parent

def decode_html(text):
    match = re.search(r'window\.__reactRouterContext\.streamController\.enqueue\(("(?:[^"\\]|\\.)*")\)', text)
    if not match:
        raise ValueError('Missing React Router payload; fail closed')
    values = json.loads(json.loads(match.group(1)))
    memo = {}
    def decode(index):
        if index < 0:
            return None
        if index in memo:
            return memo[index]
        value = values[index]
        if isinstance(value, dict):
            result = {}; memo[index] = result
            for key, ref in value.items():
                result[decode(int(key[1:])) if key.startswith('_') else key] = decode(ref)
            return result
        if isinstance(value, list):
            if value and isinstance(value[0], str):
                if value[0] == 'D':
                    return datetime.datetime.fromtimestamp(value[1]/1000, datetime.timezone.utc).isoformat()
                raise ValueError(f'Unsupported payload tag {value[0]}')
            result = []; memo[index] = result
            result.extend(decode(ref) for ref in value)
            return result
        return value
    return decode(0)['loaderData']['app/routes/esports/tournament.$slug']['data']['competitionBySlug']


