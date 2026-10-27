"""90-day leaderboard and one-way subscriptions. Points never affect wallet balances."""
import os
from datetime import datetime, timedelta, timezone
from .core import LOCK, connect, utcnow, iso

DAYS = 90


def season_window(now=None):
    now = now or utcnow()
    anchor_text = os.getenv('SEASON_ANCHOR_UTC', '2026-10-26T00:00:00+00:00')
    anchor = datetime.fromisoformat(anchor_text.replace('Z', '+00:00'))
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    anchor = anchor.astimezone(timezone.utc)
    index = (now-anchor).total_seconds() // (DAYS * 86400)
    start = anchor + timedelta(days=index * DAYS)
    return int(index)+1, start, start+timedelta(days=DAYS)


def init_seasons():
    with LOCK, connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS follows (
          follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          target_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at TEXT NOT NULL,
          PRIMARY KEY(follower_id,target_id),
          CHECK (follower_id <> target_id)
        );
        CREATE INDEX IF NOT EXISTS idx_follows_target ON follows(target_id);
        CREATE TABLE IF NOT EXISTS season_champions (
          season INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES users(id),
          points INTEGER NOT NULL,
          awarded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_champions_user ON season_champions(user_id);
        ''')



def award_completed_seasons(now=None):
    """Award precisely one immutable champion per completed season.

    The #1 winner must have positive points. Rankings tie-break by wins,
    resolved tickets and then player id. Never award a running season.
    """
    init_seasons()
    now = now or utcnow()
    current, _, _ = season_window(now)
    if current <= 1:
        return
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for season in range(1, current):
            if c.execute('SELECT 1 FROM season_champions WHERE season=?', (season,)).fetchone():
                continue
            _, start, end = season_window_from_number(season)
            row = c.execute("""SELECT user_id,
                     SUM(CASE WHEN status='won' THEN 3 WHEN status='cashed_out' THEN 1 ELSE 0 END) points,
                     SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) wins,
                     COUNT(*) resolved
                  FROM slips WHERE created_at>=? AND created_at<?
                    AND status IN ('won','lost','cashed_out')
                  GROUP BY user_id HAVING points > 0
                  ORDER BY points DESC,wins DESC,resolved DESC,user_id ASC LIMIT 1""",
                  (iso(start),iso(end))).fetchone()
            if row:
                c.execute('INSERT INTO season_champions(season,user_id,points,awarded_at) VALUES(?,?,?,?)',
                          (season,row['user_id'],row['points'],iso(now)))


def season_window_from_number(number):
    anchor_text = os.getenv('SEASON_ANCHOR_UTC', '2026-10-26T00:00:00+00:00')
    anchor = datetime.fromisoformat(anchor_text.replace('Z', '+00:00'))
    if anchor.tzinfo is None: anchor = anchor.replace(tzinfo=timezone.utc)
    start = anchor.astimezone(timezone.utc) + timedelta(days=(number-1)*DAYS)
    return number, start, start + timedelta(days=DAYS)


def champion_badges(user_ids=None, now=None):
    award_completed_seasons(now)
    with connect() as c:
        if user_ids is None:
            rows=c.execute('SELECT user_id,COUNT(*) total FROM season_champions GROUP BY user_id').fetchall()
        else:
            ids=list(set(user_ids))
            if not ids: return {}
            rows=c.execute('SELECT user_id,COUNT(*) total FROM season_champions WHERE user_id IN ('+
                           ','.join('?' for _ in ids)+') GROUP BY user_id',ids).fetchall()
    return {r['user_id']:r['total'] for r in rows}

def standings(viewer_id, limit=50, now=None):
    if not 1 <= limit <= 100:
        raise ValueError('Лимит должен быть от 1 до 100')
    season, start, end = season_window(now)
    badges=champion_badges(now=now)
    with connect() as c:
        # Only resolved slips from the current season; canceled/void don't count.
        # A slip contributes to the season when placed, and only after resolution.
        rows = c.execute('''
          SELECT u.id, u.name,
                 COALESCE(SUM(CASE WHEN s.status='won' THEN 3 WHEN s.status='cashed_out' THEN 1 ELSE 0 END),0) AS points,
                 COALESCE(SUM(CASE WHEN s.status='won' THEN 1 ELSE 0 END),0) AS wins,
                 COALESCE(SUM(CASE WHEN s.status IN ('won','lost','cashed_out') THEN 1 ELSE 0 END),0) AS resolved
          FROM users u LEFT JOIN slips s ON s.user_id=u.id AND s.created_at>=? AND s.created_at<?
          GROUP BY u.id ORDER BY points DESC, wins DESC, resolved DESC, u.id ASC
        ''', (iso(start), iso(end))).fetchall()
    entries = [{'rank':i+1,'id':r['id'],'name':r['name'],'points':r['points'],
                'wins':r['wins'],'resolved':r['resolved'],'champion_titles':badges.get(r['id'],0)} for i,r in enumerate(rows)]
    me = next((x for x in entries if x['id']==viewer_id), None)
    return {'season':season,'starts_at':iso(start),'ends_at':iso(end),'duration_days':DAYS,
            'total_players':len(entries),'top':entries[:limit], 'me':me,
            'rules':{'win':3,'cashout':1,'loss':0,'pending':0,'void':0}}


def follow(viewer_id, target_id):
    if viewer_id == target_id: raise ValueError('Нельзя подписаться на себя')
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM users WHERE id=?',(target_id,)).fetchone():
            raise ValueError('Игрок не найден')
        c.execute('INSERT OR IGNORE INTO follows(follower_id,target_id,created_at) VALUES(?,?,?)',
                  (viewer_id,target_id,iso(utcnow())))
    return follow_stats(target_id, viewer_id)


def unfollow(viewer_id, target_id):
    with LOCK, connect() as c:
        c.execute('DELETE FROM follows WHERE follower_id=? AND target_id=?',(viewer_id,target_id))
    return follow_stats(target_id, viewer_id)


def follow_stats(target_id, viewer_id):
    with connect() as c:
        if not c.execute('SELECT 1 FROM users WHERE id=?',(target_id,)).fetchone():
            raise ValueError('Игрок не найден')
        followers = c.execute('SELECT COUNT(*) FROM follows WHERE target_id=?',(target_id,)).fetchone()[0]
        following = c.execute('SELECT COUNT(*) FROM follows WHERE follower_id=?',(target_id,)).fetchone()[0]
        subscribed = c.execute('SELECT 1 FROM follows WHERE follower_id=? AND target_id=?',
                               (viewer_id,target_id)).fetchone() is not None
    return {'followers':followers,'following':following,'subscribed':subscribed,'is_self':viewer_id==target_id}


def subscriptions(viewer_id):
    with connect() as c:
        rows = c.execute('''SELECT u.id,u.name FROM follows f
                            JOIN users u ON u.id=f.target_id
                            WHERE f.follower_id=? ORDER BY f.created_at DESC LIMIT 200''',(viewer_id,)).fetchall()
        return [dict(r) for r in rows]
