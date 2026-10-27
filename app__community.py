"""Season dashboard, voluntary prediction posts, notifications and anti-abuse review.
No real-money rewards, no automated bans based on heuristics.
"""
from datetime import timedelta
from .core import LOCK, connect, utcnow, iso
from .seasons import standings, season_window, champion_badges


def init_community():
    with LOCK, connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS prediction_posts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          author_id INTEGER NOT NULL REFERENCES users(id),
          match_id INTEGER NOT NULL REFERENCES matches(id),
          pick TEXT NOT NULL,
          comment TEXT NOT NULL,
          created_at TEXT NOT NULL,
          removed INTEGER NOT NULL DEFAULT 0,
          UNIQUE(author_id,match_id)
        );
        CREATE INDEX IF NOT EXISTS idx_predictions_recent ON prediction_posts(id);
        CREATE TABLE IF NOT EXISTS prediction_reactions(
          post_id INTEGER NOT NULL REFERENCES prediction_posts(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id),
          created_at TEXT NOT NULL,
          PRIMARY KEY(post_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS prediction_reports(
          post_id INTEGER NOT NULL REFERENCES prediction_posts(id),
          user_id INTEGER NOT NULL REFERENCES users(id),
          created_at TEXT NOT NULL,
          PRIMARY KEY(post_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS community_notifications(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id),
          kind TEXT NOT NULL,
          text TEXT NOT NULL,
          dedupe_key TEXT NOT NULL,
          created_at TEXT NOT NULL,
          read_at TEXT,
          UNIQUE(user_id,dedupe_key)
        );
        CREATE TABLE IF NOT EXISTS season_snapshots(
          season INTEGER NOT NULL,
          day TEXT NOT NULL,
          user_id INTEGER NOT NULL,
          rank INTEGER NOT NULL,
          points INTEGER NOT NULL,
          PRIMARY KEY(season,day,user_id)
        );
        CREATE TABLE IF NOT EXISTS ranking_audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          season INTEGER NOT NULL,
          reason TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(user_id,season,reason)
        );
        ''')


def dashboard(user_id, now=None):
    now = now or utcnow()
    data = standings(user_id,now=now)
    current, start, end = season_window(now)
    day = (now-timedelta(days=1)).date().isoformat()
    with connect() as c:
        old = c.execute('SELECT rank,points FROM season_snapshots WHERE season=? AND day=? AND user_id=?',
                        (current, day, user_id)).fetchone()
    data['remaining_days'] = max(0, (end-now).total_seconds()/86400)
    data['previous_rank'] = old['rank'] if old else None
    data['rank_change'] = (old['rank']-data['me']['rank']) if old and data['me'] else None
    return data


def save_daily_snapshot(now=None):
    now=now or utcnow()
    season=standings(0,limit=100,now=now)
    season_id=season['season']; day=now.date().isoformat()
    # Whole ranking, not just top 100; sorted exactly like season leaderboard.
    start,end=season_window(now)[1:]
    with LOCK,connect() as c:
        rows=c.execute('''SELECT u.id,
             COALESCE(SUM(CASE WHEN s.status='won' THEN 3 WHEN s.status='cashed_out' THEN 1 ELSE 0 END),0) points,
             COALESCE(SUM(s.status='won'),0) wins,
             COALESCE(SUM(s.status IN ('won','lost','cashed_out')),0) resolved
             FROM users u LEFT JOIN slips s ON s.user_id=u.id AND s.created_at>=? AND s.created_at<?
             GROUP BY u.id ORDER BY points DESC,wins DESC,resolved DESC,u.id ASC''', (iso(start),iso(end))).fetchall()
        c.executemany('INSERT OR IGNORE INTO season_snapshots VALUES(?,?,?,?,?)',
                      [(season_id,day,r['id'],i+1,r['points']) for i,r in enumerate(rows)])
    return len(rows)


def create_post(uid,match_id,pick,comment):
    if pick not in ('H','D','A','O25','U25','GG','NG'): raise ValueError('Неизвестный исход')
    if not isinstance(comment,str) or len(comment.strip()) > 280: raise ValueError('Комментарий до 280 символов')
    comment=comment.strip()
    now=utcnow()
    with LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE')
        match=c.execute('SELECT kickoff,status FROM matches WHERE id=?',(match_id,)).fetchone()
        if not match or match['status'] not in ('SCHEDULED','TIMED') or match['kickoff']<=iso(now+timedelta(minutes=5)):
            raise ValueError('Прогноз можно опубликовать только до закрытия приёма')
        last=c.execute('SELECT created_at FROM prediction_posts WHERE author_id=? ORDER BY id DESC LIMIT 1',(uid,)).fetchone()
        if last and (now-__import__('datetime').datetime.fromisoformat(last['created_at'])).total_seconds()<30:
            raise ValueError('Не чаще одного прогноза в 30 секунд')
        try:
            cursor=c.execute('INSERT INTO prediction_posts(author_id,match_id,pick,comment,created_at) VALUES(?,?,?,?,?)',
                           (uid,match_id,pick,comment,iso(now)))
        except __import__('sqlite3').IntegrityError: raise ValueError('На этот матч прогноз уже опубликован')
    return {'id':cursor.lastrowid}


def feed(uid,mode='all',limit=40):
    if mode not in ('all','following'): raise ValueError('Неизвестный фильтр')
    limit=max(1,min(int(limit),80))
    with connect() as c:
        clause='AND EXISTS (SELECT 1 FROM follows f WHERE f.target_id=p.author_id AND f.follower_id=?)' if mode=='following' else ''
        params=[uid,uid]+([uid] if mode=='following' else [])+[limit]
        rows=c.execute(f'''SELECT p.id,p.author_id,u.name,p.match_id,m.home,m.away,m.kickoff,p.pick,p.comment,p.created_at,
           (SELECT COUNT(*) FROM prediction_reactions r WHERE r.post_id=p.id) likes,
           EXISTS(SELECT 1 FROM prediction_reactions r WHERE r.post_id=p.id AND r.user_id=?) liked,
           EXISTS(SELECT 1 FROM follows f WHERE f.target_id=p.author_id AND f.follower_id=?) following
           FROM prediction_posts p JOIN users u ON u.id=p.author_id JOIN matches m ON m.id=p.match_id
           WHERE p.removed=0 {clause} ORDER BY p.id DESC LIMIT ?''', params).fetchall()
    results=[dict(r) for r in rows]
    badges=champion_badges([r['author_id'] for r in results])
    for r in results:r['champion_titles']=badges.get(r['author_id'],0)
    return results


def like(uid,post_id):
    with LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM prediction_posts WHERE id=? AND removed=0',(post_id,)).fetchone():
            raise ValueError('Публикация не найдена')
        c.execute('INSERT OR IGNORE INTO prediction_reactions VALUES(?,?,?)',(post_id,uid,iso(utcnow())))
    return {'ok':True}


def report_post(uid,post_id):
    with LOCK,connect() as c:
        post=c.execute('SELECT author_id FROM prediction_posts WHERE id=? AND removed=0',(post_id,)).fetchone()
        if not post or post['author_id']==uid:raise ValueError('Нельзя отправить жалобу')
        c.execute('INSERT OR IGNORE INTO prediction_reports VALUES(?,?,?)',(post_id,uid,iso(utcnow())))
    return {'ok':True}


def remove_post(post_id):
    with LOCK,connect() as c:
        if not c.execute('UPDATE prediction_posts SET removed=1 WHERE id=? AND removed=0',(post_id,)).rowcount:
            raise ValueError('Публикация не найдена')
    return {'ok':True}


def reports():
    with connect() as c:
        return [dict(r) for r in c.execute('''SELECT p.id,p.comment,u.name,COUNT(pr.user_id) reports
            FROM prediction_reports pr JOIN prediction_posts p ON p.id=pr.post_id
            JOIN users u ON u.id=p.author_id WHERE p.removed=0 GROUP BY p.id ORDER BY reports DESC LIMIT 50''')]


def notify(uid,kind,message,key):
    with LOCK,connect() as c:
        c.execute('INSERT OR IGNORE INTO community_notifications(user_id,kind,text,dedupe_key,created_at) VALUES(?,?,?,?,?)',
                  (uid,kind,message,key,iso(utcnow())))


def get_notifications(uid):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT id,kind,text,created_at,read_at FROM community_notifications WHERE user_id=? ORDER BY id DESC LIMIT 80',(uid,))]


def mark_read(uid,notification_id):
    with LOCK,connect() as c:
        if not c.execute('UPDATE community_notifications SET read_at=? WHERE id=? AND user_id=?',
                         (iso(utcnow()),notification_id,uid)).rowcount:
            raise ValueError('Уведомление не найдено')
    return {'ok':True}


def ranking_audit(now=None):
    """Review-only flags. Never ban or penalize automatically."""
    now=now or utcnow(); season,start,end=season_window(now)
    with LOCK,connect() as c:
        rows=c.execute('''SELECT user_id,COUNT(*) cnt FROM slips WHERE created_at>=? AND created_at<?
                         GROUP BY user_id HAVING cnt>=150''',(iso(start),iso(end))).fetchall()
        for r in rows:
            c.execute('INSERT OR IGNORE INTO ranking_audit(user_id,season,reason,created_at) VALUES(?,?,?,?)',
                      (r['user_id'],season,'Необычно много купонов за сезон: проверка вручную',iso(now)))
    return len(rows)


def audit_queue():
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM ranking_audit ORDER BY id DESC LIMIT 100')]


def community_maintenance(now=None):
    """Periodic, idempotent maintenance; sync independent from Telegram delivery."""
    now=now or utcnow()
    init_community()
    save_daily_snapshot(now)
    ranking_audit(now)
    from .seasons import award_completed_seasons
    award_completed_seasons(now)
    season,_,end=season_window(now)
    with connect() as c:
        # Mirror already-settled coupons to the in-app activity feed.
        settled=c.execute("SELECT id,user_id,status,payout FROM slips WHERE status IN ('won','lost','void','cashed_out') ORDER BY id DESC LIMIT 500").fetchall()
        champions=c.execute('SELECT season,user_id FROM season_champions').fetchall()
        players=c.execute('SELECT id FROM users').fetchall()
    for r in settled:
        notify(r['user_id'],'slip',f'Купон №{r["id"]}: {r["status"]} · начислено {r["payout"] or 0} монет',f'slip:{r["id"]}:{r["status"]}')
    for r in champions:
        notify(r['user_id'],'champion',f'Ты чемпион сезона №{r["season"]}! Значок ✦ теперь у твоего ника.',f'champion:{r["season"]}')
    for r in players:
        notify(r['id'],'season',f'Сезон №{season} начался! Он продлится 90 дней.',f'season:{season}:begin')
        if (end-now).total_seconds()<=86400:
            notify(r['id'],'season',f'Сезон №{season} заканчивается менее чем через сутки.',f'season:{season}:end')
