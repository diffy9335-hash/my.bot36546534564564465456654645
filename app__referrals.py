"""Invite system: XP only, no balance/monetary rewards, no wagering conditions."""
import os
from datetime import datetime, timezone
from .core import connect, LOCK

REFERRER_XP = 50
INVITEE_XP = 25


def init_referrals():
    with LOCK, connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS referrals (
          invitee_id INTEGER PRIMARY KEY REFERENCES users(id),
          inviter_id INTEGER NOT NULL REFERENCES users(id),
          joined_day TEXT NOT NULL,
          qualified_day TEXT,
          inviter_xp INTEGER NOT NULL DEFAULT 0,
          invitee_xp INTEGER NOT NULL DEFAULT 0,
          CHECK(invitee_id != inviter_id))''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_referrals_inviter ON referrals(inviter_id)')


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def parse_code(code):
    if not isinstance(code, str) or not code.startswith('ref_'): return None
    number=code[4:]
    if not number.isascii() or not number.isdigit() or len(number)>18: return None
    uid=int(number)
    return uid if uid > 0 else None


def enroll(invitee_id, code, name='Игрок'):
    """Register referral only on genuinely new account. Atomic against repeats."""
    inviter_id=parse_code(code)
    if not inviter_id or inviter_id==invitee_id: return False
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM users WHERE id=?',(invitee_id,)).fetchone(): return False
        if not c.execute('SELECT 1 FROM users WHERE id=?',(inviter_id,)).fetchone(): return False
        c.execute('INSERT INTO users(id,name) VALUES(?,?)',(invitee_id,name[:100]))
        c.execute('INSERT INTO referrals(invitee_id,inviter_id,joined_day) VALUES(?,?,?)',(invitee_id,inviter_id,_today()))
        return True


def record_visit(uid):
    """Qualify no earlier than a distinct UTC day after initial join."""
    with LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT joined_day FROM referrals WHERE invitee_id=? AND qualified_day IS NULL',(uid,)).fetchone()
        if not row or _today()<=row['joined_day']: return False
        c.execute('UPDATE referrals SET qualified_day=?, inviter_xp=?, invitee_xp=? WHERE invitee_id=? AND qualified_day IS NULL',(_today(),REFERRER_XP,INVITEE_XP,uid))
        return True


def summary(uid):
    username=os.getenv('BOT_USERNAME','').lstrip('@')
    link=f'https://t.me/{username}?start=ref_{uid}' if username and all(x.isalnum() or x=='_' for x in username) else None
    with connect() as c:
        rows=c.execute('''SELECT r.qualified_day, u.name FROM referrals r
             JOIN users u ON u.id=r.invitee_id WHERE r.inviter_id=? ORDER BY r.rowid DESC LIMIT 50''',(uid,)).fetchall()
        counts=c.execute('SELECT COUNT(*),COUNT(qualified_day) FROM referrals WHERE inviter_id=?',(uid,)).fetchone()
        return {'invite_link':link,'invited':counts[0],'qualified':counts[1],
                'earned_xp':counts[1]*REFERRER_XP,'xp_per_qualified':REFERRER_XP,
                'invited_users':[{'name':r['name'],'status':'qualified' if r['qualified_day'] else 'pending'} for r in rows],
                'qualification':'Друг должен впервые открыть бота по ссылке и вернуться на следующий день; начисляется только XP.'}


def referral_xp(uid):
    with connect() as c:
        return c.execute('SELECT COALESCE(SUM(inviter_xp),0) FROM referrals WHERE inviter_id=?',(uid,)).fetchone()[0] + c.execute('SELECT COALESCE(SUM(invitee_xp),0) FROM referrals WHERE invitee_id=?',(uid,)).fetchone()[0]
