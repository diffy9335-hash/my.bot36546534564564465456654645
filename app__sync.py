import os, asyncio, logging
from datetime import timedelta
import httpx
from .core import connect, LOCK, utcnow, iso, settle, seed_demo
from .community import community_maintenance
from .game_odds import game_odds
from .operations import record_sync
log=logging.getLogger(__name__)
API='https://api.football-data.org/v4/matches'
CODES={'PL':'Premier League','PD':'La Liga','BL1':'Bundesliga','SA':'Serie A','FL1':'Ligue 1','CL':'Champions League'}

async def synchronize():
    key=os.getenv('FOOTBALL_API_KEY','').strip()
    if not key:
        if os.getenv('DEMO_MODE','false').lower()=='true': seed_demo()
        return {'mode':'demo' if os.getenv('DEMO_MODE','false').lower()=='true' else 'empty','updated':0}
    today=utcnow().date()
    params={'dateFrom':(today-timedelta(days=2)).isoformat(),'dateTo':(today+timedelta(days=7)).isoformat()}
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.get(API,headers={'X-Auth-Token':key},params=params)
        r.raise_for_status(); data=r.json()
    updated=0
    with LOCK,connect() as c:
        for m in data.get('matches',[]):
            code=m.get('competition',{}).get('code')
            if code not in CODES: continue
            status=m.get('status','SCHEDULED')
            score=m.get('score',{}).get('fullTime') or {}
            # Only fresh API match score, never estimate the actual result.
            h=score.get('home') if status in ('FINISHED','IN_PLAY') else None
            a=score.get('away') if status in ('FINISHED','IN_PLAY') else None
            kickoff=m.get('utcDate')
            if not kickoff: continue
            kickoff=kickoff.replace('Z','+00:00')
            home=m.get('homeTeam',{}).get('name','Unknown'); away=m.get('awayTeam',{}).get('name','Unknown')
            home_crest=m.get('homeTeam',{}).get('crest') or None
            away_crest=m.get('awayTeam',{}).get('crest') or None
            mid=int(m['id'])
            previous=c.execute('SELECT status,home_score,away_score FROM matches WHERE id=?',(mid,)).fetchone()
            # A stale or out-of-order provider snapshot must not undo a verified final result.
            if previous and previous['status']=='FINISHED' and status!='FINISHED':
                log.warning('Ignoring status regression for finished match %s: %s',mid,status)
                continue
            # Never replace a known final score with an incomplete snapshot.
            if previous and previous['status']=='FINISHED' and status=='FINISHED' and (h is None or a is None):
                continue
            # Snapshots only: changes are logged as score updates, NOT as goals
            # attributed to a player or minute. APIs may skip intermediate scores.
            if status=='IN_PLAY' and h is not None and a is not None:
                if previous and (previous['home_score'],previous['away_score'])!=(h,a):
                    event_kind='score_changed'
                elif not previous or previous['status']!='IN_PLAY':
                    event_kind='live_started'
                else: event_kind=None
            elif previous and previous['status']!='FINISHED' and status=='FINISHED':
                event_kind='finished'
            else: event_kind=None
            # football-data.org returns match scores, not bookmakers' odds.
            # Synthetic stable game prices; NOT verified prediction or bookmaker quotes.
            odds=game_odds(home,away)
            # Avoid stale/incomplete live snapshots erasing the last known score.
            if previous and status=='IN_PLAY' and (h is None or a is None):
                continue
            c.execute('''INSERT INTO matches(id,league,home,away,kickoff,status,home_score,away_score,odd_h,odd_d,odd_a,updated_at,home_crest,away_crest)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            league=excluded.league,home=excluded.home,away=excluded.away,kickoff=excluded.kickoff,status=excluded.status,
            home_score=excluded.home_score,away_score=excluded.away_score,updated_at=excluded.updated_at,
            odd_h=excluded.odd_h,odd_d=excluded.odd_d,odd_a=excluded.odd_a,
            home_crest=COALESCE(excluded.home_crest,matches.home_crest),away_crest=COALESCE(excluded.away_crest,matches.away_crest)''',
            (mid,CODES[code],home,away,kickoff,status,h,a,*odds,iso(utcnow()),home_crest,away_crest))
            if event_kind:
                c.execute('INSERT INTO match_events(match_id,kind,home_score,away_score,occurred_at,source) VALUES (?,?,?,?,?,?)',
                          (mid,event_kind,h,a,iso(utcnow()),'football-data.org snapshot'))
            updated+=1
    calculated=settle()
    return {'mode':'real','updated':updated,'settled':calculated}

async def polling_loop():
    minutes=max(1,int(os.getenv('SYNC_MINUTES','2')))
    while True:
        started=iso(utcnow())
        try:
            result=await synchronize()
            record_sync(started,result=result)
            community_maintenance()
            log.info('Sync: %s',result)
        except Exception as exc:
            log.exception('Football sync failed; previous data kept')
            try: record_sync(started,error=exc)
            except Exception: log.exception('Failed to persist sync error')
        await asyncio.sleep(minutes*60)
