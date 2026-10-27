"""Public in-app chat. Only authenticated Telegram Mini App users can post.

SQLite-backed polling works with a single or multiple uvicorn workers. Public
profiles deliberately exclude wallet/ledger details and Telegram identifiers.
"""
from datetime import timedelta
from .core import connect, LOCK, utcnow, iso
from .seasons import champion_badges


def init_social():
    with LOCK, connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS chat_messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL REFERENCES users(id),
          body TEXT NOT NULL,
          created_at TEXT NOT NULL,
          removed INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_time ON chat_messages(id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_author ON chat_messages(user_id,id);
        CREATE TABLE IF NOT EXISTS chat_reports(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          message_id INTEGER NOT NULL REFERENCES chat_messages(id),
          reporter_id INTEGER NOT NULL REFERENCES users(id),
          created_at TEXT NOT NULL,
          UNIQUE(message_id,reporter_id)
        );
        CREATE TABLE IF NOT EXISTS chat_mutes(
          user_id INTEGER PRIMARY KEY REFERENCES users(id),
          until_at TEXT NOT NULL,
          reason TEXT NOT NULL
        );
        ''')


def messages(after=0, limit=60):
    if after < 0 or limit < 1 or limit > 100: raise ValueError('Некорректная страница')
    with connect() as c:
        if after:
            rows=c.execute('''SELECT m.id,m.user_id,u.name,m.body,m.created_at
                              FROM chat_messages m JOIN users u ON m.user_id=u.id
                              WHERE m.id>? AND m.removed=0 ORDER BY m.id ASC LIMIT ?''',(after,limit)).fetchall()
        else:
            rows=c.execute('''SELECT m.id,m.user_id,u.name,m.body,m.created_at
                              FROM chat_messages m JOIN users u ON m.user_id=u.id
                              WHERE m.removed=0 ORDER BY m.id DESC LIMIT ?''',(limit,)).fetchall()
        result=list(reversed([dict(r) for r in rows])) if not after else [dict(r) for r in rows]
    badges=champion_badges([r['user_id'] for r in result])
    for r in result: r['champion_titles']=badges.get(r['user_id'],0)
    return result


def send(uid, body):
    if not isinstance(body,str): raise ValueError('Текст обязателен')
    body=body.strip()
    if not 1 <= len(body) <= 350: raise ValueError('Сообщение: от 1 до 350 символов')
    if any(ord(ch)<32 and ch not in '\n\t' for ch in body): raise ValueError('Недопустимые символы')
    now=utcnow()
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        mute=c.execute('SELECT until_at FROM chat_mutes WHERE user_id=?',(uid,)).fetchone()
        if mute and mute['until_at']>iso(now): raise ValueError('Чат временно недоступен для вашего аккаунта')
        last=c.execute('SELECT created_at FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT 1',(uid,)).fetchone()
        if last and (now-__import__('datetime').datetime.fromisoformat(last['created_at'])).total_seconds()<5:
            raise ValueError('Подожди 5 секунд перед следующим сообщением')
        count=c.execute('SELECT COUNT(*) FROM chat_messages WHERE user_id=? AND created_at>=?',(uid,iso(now-timedelta(hours=1)))).fetchone()[0]
        if count>=50: raise ValueError('Лимит: 50 сообщений в час')
        cur=c.execute('INSERT INTO chat_messages(user_id,body,created_at) VALUES (?,?,?)',(uid,body,iso(now)))
        # Bounded history, no unbounded growth on small SQLite VPS setups.
        c.execute('DELETE FROM chat_reports WHERE message_id IN (SELECT id FROM chat_messages WHERE id < (SELECT COALESCE(MAX(id),0)-10000 FROM chat_messages))')
        c.execute('DELETE FROM chat_messages WHERE id < (SELECT COALESCE(MAX(id),0)-10000 FROM chat_messages)')
        return {'id':cur.lastrowid,'created_at':iso(now)}


def report(uid, message_id):
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT user_id FROM chat_messages WHERE id=? AND removed=0',(message_id,)).fetchone()
        if not row: raise ValueError('Сообщение не найдено')
        if row['user_id']==uid: raise ValueError('Нельзя жаловаться на своё сообщение')
        c.execute('INSERT OR IGNORE INTO chat_reports(message_id,reporter_id,created_at) VALUES(?,?,?)',(message_id,uid,iso(utcnow())))
        return {'ok':True}


def public_profile(uid):
    with connect() as c:
        row=c.execute('SELECT id,name FROM users WHERE id=?',(uid,)).fetchone()
        if not row: raise ValueError('Игрок не найден')
        count=c.execute('''SELECT COUNT(*) total,
            COALESCE(SUM(status='won'),0) won,
            COALESCE(SUM(status='lost'),0) lost
            FROM slips WHERE user_id=?''',(uid,)).fetchone()
        result={'id':row['id'],'name':row['name'],'bets':count['total'],'wins':count['won'],
                'losses':count['lost'],
                'resolved':count['won']+count['lost'],
                'win_rate':round(100*count['won']/(count['won']+count['lost']),1) if count['won']+count['lost'] else 0}
    result['champion_titles']=champion_badges([uid]).get(uid,0)
    return result


def moderation_queue():
    with connect() as c:
        return [dict(x) for x in c.execute('''SELECT m.id,m.body,u.name,m.user_id,COUNT(r.id) reports
            FROM chat_reports r JOIN chat_messages m ON m.id=r.message_id
            JOIN users u ON u.id=m.user_id WHERE m.removed=0
            GROUP BY m.id ORDER BY reports DESC,m.id DESC LIMIT 50''')]


def remove_message(message_id):
    with LOCK, connect() as c:
        updated=c.execute('UPDATE chat_messages SET removed=1 WHERE id=? AND removed=0',(message_id,)).rowcount
    if not updated: raise ValueError('Сообщение не найдено')
    return {'ok':True}


def mute_player(uid, minutes):
    if not 1<=minutes<=10080: raise ValueError('Можно замутить на 1–10080 минут')
    with LOCK,connect() as c:
        if not c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone(): raise ValueError('Игрок не найден')
        until=iso(utcnow()+timedelta(minutes=minutes))
        c.execute('INSERT OR REPLACE INTO chat_mutes(user_id,until_at,reason) VALUES(?,?,?)',(uid,until,'Модерация'))
    return {'ok':True,'until_at':until}
