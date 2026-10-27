"""Virtual-only progression. XP is not money and has no redemption value."""
from datetime import datetime, timezone
from .core import connect, LOCK
from .referrals import referral_xp, init_referrals

QUESTS = (
    ('visit', 'Зайти в игру', 15),
    ('bonus', 'Получить ежедневный бонус', 20),
    ('prediction', 'Сделать один прогноз', 25),
)

def init_progression():
    init_referrals()
    with LOCK, connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS quest_claims (
          user_id INTEGER NOT NULL REFERENCES users(id), day TEXT NOT NULL,
          quest TEXT NOT NULL, xp INTEGER NOT NULL, claimed_at TEXT NOT NULL,
          PRIMARY KEY(user_id, day, quest))''')

def _day():
    return datetime.now(timezone.utc).date().isoformat()

def _facts(c, uid, day):
    slips=c.execute('SELECT COUNT(*) FROM slips WHERE user_id=?',(uid,)).fetchone()[0]
    settled=c.execute("SELECT COUNT(*) FROM slips WHERE user_id=? AND status IN ('won','lost','void','cashed_out')",(uid,)).fetchone()[0]
    wins=c.execute("SELECT COUNT(*) FROM slips WHERE user_id=? AND status='won'",(uid,)).fetchone()[0]
    combos=c.execute('SELECT COUNT(*) FROM slips s WHERE s.user_id=? AND (SELECT COUNT(*) FROM legs l WHERE l.slip_id=s.id)>1',(uid,)).fetchone()[0]
    today_bets=c.execute('SELECT COUNT(*) FROM slips WHERE user_id=? AND substr(created_at,1,10)=?',(uid,day)).fetchone()[0]
    bonus=c.execute('SELECT last_bonus FROM users WHERE id=?',(uid,)).fetchone()
    return {'slips':slips,'settled':settled,'wins':wins,'combos':combos,'today_bets':today_bets,'bonus_today':bool(bonus and bonus[0]==day)}

def _level(xp):
    # Every level needs 100 more XP than the previous level.
    level=1; minimum=0; needed=100
    while xp >= minimum+needed:
        minimum+=needed;level+=1;needed=100*level
    return {'level':level,'xp':xp,'level_start_xp':minimum,'next_level_xp':minimum+needed,'progress_xp':xp-minimum,'needed_xp':needed}

def summary(uid):
    day=_day()
    with LOCK, connect() as c:
        facts=_facts(c,uid,day)
        claimed={r['quest'] for r in c.execute('SELECT quest FROM quest_claims WHERE user_id=? AND day=?',(uid,day))}
        claimed_xp=c.execute('SELECT COALESCE(SUM(xp),0) FROM quest_claims WHERE user_id=?',(uid,)).fetchone()[0]
        # Historical, deterministic XP from real app actions. No stake-size multiplier.
        xp=20*min(facts['slips'],100)+15*min(facts['settled'],100)+25*min(facts['wins'],100)+claimed_xp+referral_xp(uid)
        quests=[{'id':key,'title':title,'xp':reward,'completed':key=='visit' or (key=='bonus' and facts['bonus_today']) or (key=='prediction' and facts['today_bets']>0),'claimed':key in claimed} for key,title,reward in QUESTS]
        milestones=[('first','Первый прогноз',facts['slips'],1),('five','Пять прогнозов',facts['slips'],5),('settled','Три рассчитанных прогноза',facts['settled'],3),('winner','Первая победа',facts['wins'],1),('combo','Первый экспресс',facts['combos'],1)]
        achievements=[{'id':key,'title':title,'current':min(current,target),'target':target,'unlocked':current>=target} for key,title,current,target in milestones]
        return {**_level(xp),'quests':quests,'achievements':achievements,'day_utc':day,'xp_virtual_only':True}

def claim(uid, quest):
    allowed={x[0]:x[2] for x in QUESTS}
    if quest not in allowed: raise ValueError('Неизвестное задание')
    day=_day()
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        facts=_facts(c,uid,day)
        complete=quest=='visit' or quest=='bonus' and facts['bonus_today'] or quest=='prediction' and facts['today_bets']>0
        if not complete: raise ValueError('Задание ещё не выполнено')
        exists=c.execute('SELECT 1 FROM quest_claims WHERE user_id=? AND day=? AND quest=?',(uid,day,quest)).fetchone()
        if exists: raise ValueError('Награда за задание уже получена')
        c.execute('INSERT INTO quest_claims(user_id,day,quest,xp,claimed_at) VALUES(?,?,?,?,?)',(uid,day,quest,allowed[quest],datetime.now(timezone.utc).isoformat()))
    return summary(uid)
