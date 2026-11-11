"""Official CN OWCS adapter. Standard library only; no AI or authentication.
Fail closed on new teams/status/schema. Does not alter roster, events or publish.
"""
import copy, json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
BASE = "https://webapi.blizzard.cn/ow-game-center-server-release-app/"
STAGE_URL = BASE + "stage_list"
NAME_IDS = {"All Gamers":"all-gamers", "BLACK FLAG":"black-flag", "HuNeng Gaming":"huneng-gaming", "JD Gaming":"jd-gaming", "Over Ultra Gaming":"over-ultra-gaming", "SHENGSHI Esports":"shengshi-esports", "SV.CRUSH":"sv-crush", "Weibo Gaming":"weibo-gaming"}
JST = timezone(timedelta(hours=9))
def fetch(url):
    with urllib.request.urlopen(url, timeout=35) as r:
        if r.status != 200: raise ValueError("HTTP status")
        body=r.read(4 * 1024 * 1024 + 1)
        if len(body)>4 * 1024 * 1024: raise ValueError("Oversize API response")
        doc=json.loads(body)
    if doc.get("code") != 0 or not isinstance(doc.get("data"),dict): raise ValueError("API failure")
    return doc["data"]
def url(endpoint, **params):
    return BASE+endpoint+"?"+urllib.parse.urlencode(params)
def normalize(payload, year, stage, source_id):
    teams={t["team_uuid"]: NAME_IDS[t["team_name"]] for t in payload["team_detail_list"]}
    result=[]
    for m in payload["match_list"]:
        if m["year"] != str(year): raise ValueError("Wrong season")
        status={0:"scheduled",1:"completed",2:"in-progress"}[m["status"]]
        start=datetime.fromtimestamp(m["match_time"]/1000,timezone.utc).astimezone(JST)
        h,a=m["home_team_info"],m["custom_team_info"]
        score=[h["team_score"],a["team_score"]] if status == "completed" else None
        if score is not None and any(type(x) is not int or x<0 for x in score): raise ValueError("Invalid scores")
        if score is not None and (score[0]==score[1] or max(score) not in (3,4) or min(score)>=max(score)): raise ValueError("Invalid completed winner")
        if h["team_uuid"]==a["team_uuid"]: raise ValueError("Self match")
        result.append(dict(id=f"cn-{year}-{stage.lower()}-{m['match_uuid']}",date=start.date().isoformat(),startAt=None if status=="completed" else start.isoformat(),phase="playoffs" if m["type_name"]=="季后赛" else "regular",round=m["type_name"],home=teams[h["team_uuid"]],away=teams[a["team_uuid"]],score=score,status=status,sourceIds=[source_id],archiveUrl=None,note="中国公式公開データ。日時は公式予定時刻であり、実開始時刻ではありません。",timeBasis="date-only" if status=="completed" else "official-scheduled-time",scheduledStartAt=start.isoformat(),timeKind="scheduled",sourceTimeZone="Asia/Shanghai",displayTimeZone="Asia/Tokyo"))
    if len({m["id"] for m in result}) != len(result): raise ValueError("Duplicate matches")
    return result

def refresh(existing, year=2026, stage="S3", get=fetch):
    checked=datetime.now(timezone.utc).isoformat()
    listing=get(STAGE_URL)
    seasons=[s for s in listing["season_year_list"] if s["year"]==str(year)]
    if len(seasons)!=1: raise ValueError("Season not found")
    stages=[s for s in seasons[0]["stage_list"] if s["comp_type"]==stage]
    if len(stages)!=1: raise ValueError("Stage not found")
    matches=[];sources=[];regular=[]
    for phase in stages[0]["type_list"]:
        query=url("match_list",comp_type=stage,year=year,game_type=phase["game_type"],match_uuid=phase["match_uuid"])
        sid="cn-auto-"+phase["match_uuid"]
        payload=get(query);matches.extend(normalize(payload,year,stage,sid))
        sources.append(dict(id=sid,title="中国公式："+phase["type_name"],url=query,publisher="Blizzard Entertainment / NetEase",checkedAt=checked))
        if phase["game_type"]=="regular": regular.append((phase,payload))
    if len({m["id"] for m in matches}) != len(matches): raise ValueError("Cross-phase duplicate")
    out=copy.deepcopy(existing);out["matches"]=sorted(matches,key=lambda m:(m["scheduledStartAt"],m["id"]))
    # UI shows the latest regular phase separately from Swiss. Never blend tables.
    # stage_list orders phases as rendered by the official frontend. Select by
    # explicit phase label; never rely on shuffled response ordering.
    rr=[item for item in regular if item[0]["type_name"]=="常规赛-单循环"]
    if len(rr)!=1: raise ValueError("Unique round robin phase required")
    phase,payload=rr[0]
    query=url("team_statistics",match_uuid=phase["match_uuid"])
    stats=get(query)["team_statistics"]
    if len(stats)!=6: raise ValueError("Expected six round robin standings teams")
    teammap={t["team_uuid"]:NAME_IDS[t["team_name"]] for t in payload["team_detail_list"]}
    rows=[]
    for t in stats:
        if NAME_IDS[t["team_name"]]!=teammap[t["team_uuid"]]: raise ValueError("Standings team mismatch")
        diff=t["winning_score_cnt"]-t["losing_score_cnt"]
        if diff!=t["total_score"]: raise ValueError("Map differential mismatch")
        rows.append(dict(rank=t["rank"],team=teammap[t["team_uuid"]],wins=t["winning_cnt"],losses=t["losing_cnt"],mapDifference=f"{diff:+d}"))
    if len({r["team"] for r in rows})!=6 or set(r["team"] for r in rows)!=set(teammap.values()): raise ValueError("Incomplete standings team set")
    sid="cn-auto-standings-"+phase["match_uuid"]
    sources.append(dict(id=sid,title="中国公式順位："+phase["type_name"],url=query,publisher="Blizzard Entertainment / NetEase",checkedAt=checked))
    out["standings"]=dict(rows=sorted(rows,key=lambda r:r["rank"]),note="Stage 3総当たりの公式順位。プレーオフ最終順位とは異なります。同順位は公式値を維持。",kind="regular",sourceIds=[sid],sourceUpdatedLabel="公式更新日時の表示なし",checkedAt=checked)
    out["sources"]=[s for s in out.get("sources",[]) if not s["id"].startswith("cn-auto-")]+sources
    # Do not allow a transient partial/upstream regression to erase known results.
    fresh={m["id"]:m for m in matches}
    known_ids={t["id"] for t in existing["teams"]}
    if not set(NAME_IDS.values()).issubset(known_ids): raise ValueError("Existing site lacks known teams")
    for old in existing.get("matches",[]):
        new=fresh.get(old["id"])
        if new is None: raise ValueError("Previously listed match disappeared")
        if old.get("status")=="completed" and any(new.get(k)!=old.get(k) for k in ("status","score","home","away")): raise ValueError("Previously completed match changed; manual review required")
    out.setdefault("updateStatus",{}).update(matchesCheckedAt=checked,standingsCheckedAt=checked,rosterCheckedAt=existing.get("updateStatus",{}).get("rosterCheckedAt",existing.get("checkedAt")),standingsTeamCount=6)

    out["coverage"]=dict(note="中国公式が公開する指定Stage全フェーズの試合を収録。",resultDateRange=[min(m["date"] for m in matches),max(m["date"] for m in matches)],scheduleNote="公式予定時刻。実開始時刻とは区別。",teamsCoverage="既存ロスターを保持。試合チームIDのみ公式名で照合。")
    return out
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("input");p.add_argument("output");a=p.parse_args()
    with open(a.input,encoding="utf-8") as f: original=json.load(f)
    result=refresh(original)
    with open(a.output,"w",encoding="utf-8") as f: json.dump(result,f,ensure_ascii=False,indent=2)

