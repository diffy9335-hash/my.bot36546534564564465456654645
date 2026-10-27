import os, sqlite3, hmac, hashlib, json, time, threading, random, math
from urllib.parse import parse_qsl
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = os.getenv('DB_PATH', './football.sqlite3')
LOCK = threading.RLock()
START_BONUS = 1000


def connect():
    c = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init_db():
    with LOCK, connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, balance INTEGER NOT NULL DEFAULT 1000, last_bonus TEXT);
        CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY, league TEXT NOT NULL, home TEXT NOT NULL, away TEXT NOT NULL,
          kickoff TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'SCHEDULED', home_score INTEGER, away_score INTEGER,
          odd_h REAL NOT NULL, odd_d REAL NOT NULL, odd_a REAL NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS slips(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), stake INTEGER NOT NULL,
          combined_odd REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending', payout INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS legs(id INTEGER PRIMARY KEY AUTOINCREMENT, slip_id INTEGER NOT NULL REFERENCES slips(id), match_id INTEGER NOT NULL REFERENCES matches(id),
          pick TEXT NOT NULL, locked_odd REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending', UNIQUE(slip_id, match_id));
        CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, reason TEXT NOT NULL,
          ref TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, text TEXT NOT NULL,
          sent_at TEXT, claimed_at TEXT, created_at TEXT NOT NULL, UNIQUE(user_id,text));
        ''')
        c.execute('''CREATE TABLE IF NOT EXISTS match_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER NOT NULL REFERENCES matches(id),
          kind TEXT NOT NULL, home_score INTEGER, away_score INTEGER,
          occurred_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'score_snapshot')''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_match_events_match ON match_events(match_id,id DESC)')
        match_cols={r['name'] for r in c.execute('PRAGMA table_info(matches)')}
        for column in ('home_crest','away_crest'):
            if column not in match_cols: c.execute(f'ALTER TABLE matches ADD COLUMN {column} TEXT')
        cols={r['name'] for r in c.execute('PRAGMA table_info(slips)')}
        if 'cashout_at' not in cols: c.execute('ALTER TABLE slips ADD COLUMN cashout_at TEXT')
        if 'request_key' not in cols: c.execute('ALTER TABLE slips ADD COLUMN request_key TEXT')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_slips_idempotency ON slips(user_id,request_key) WHERE request_key IS NOT NULL')
        c.execute('CREATE INDEX IF NOT EXISTS idx_slips_user_status ON slips(user_id,status)')


def utcnow(): return datetime.now(timezone.utc)
def iso(dt): return dt.isoformat(timespec='seconds')


def validate_init_data(raw, token, ttl=86400):
    if not raw or not token: raise ValueError('Нет данных Telegram')
    parsed = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    pairs = dict(parsed)
    if len(pairs) != len(parsed): raise ValueError('Повторяющиеся параметры Telegram')
    signature = pairs.pop('hash', None)
    if not signature: raise ValueError('Нет подписи')
    # Telegram bot-token HMAC includes the `signature` field, if present.
    # Only `hash` is excluded. Ed25519 third-party verification uses
    # a different data-check-string and excludes both fields.
    check = '\n'.join(f'{k}={v}' for k,v in sorted(pairs.items()))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, signature): raise ValueError('Неверная подпись Telegram')
    try: auth_date = int(pairs.get('auth_date', 0))
    except (TypeError, ValueError): raise ValueError('Неверная дата сессии Telegram')
    age = time.time() - auth_date
    if age < -60 or age > ttl: raise ValueError('Сессия устарела')
    try: user = json.loads(pairs['user'])
    except (KeyError, ValueError, TypeError): raise ValueError('Нет данных пользователя Telegram')
    if not isinstance(user, dict) or type(user.get('id')) is not int or user['id'] <= 0: raise ValueError('Нет ID')
    return user


def get_user(uid, name='Игрок'):
    with LOCK, connect() as c:
        c.execute('INSERT OR IGNORE INTO users(id,name) VALUES (?,?)', (uid, name[:100]))
        c.execute('UPDATE users SET name=? WHERE id=?', (name[:100],uid))
        return dict(c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())


def get_matches():
    with connect() as c:
        return [dict(x) for x in c.execute("SELECT * FROM matches WHERE kickoff>=datetime('now','-2 days') OR status='IN_PLAY' ORDER BY kickoff LIMIT 150")]


def get_live_center():
    """Snapshot-based score timeline, not individual goals or disciplinary events."""
    with connect() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM matches WHERE status IN ('IN_PLAY','PAUSED','HALFTIME') ORDER BY kickoff LIMIT 75")]
        for m in rows:
            m['events']=[dict(r) for r in c.execute('SELECT kind,home_score,away_score,occurred_at,source FROM match_events WHERE match_id=? ORDER BY id DESC LIMIT 12',(m['id'],))][::-1]
            age=(utcnow()-datetime.fromisoformat(m['updated_at'])).total_seconds()
            m['fresh']=0 <= age <= 180
            m['age_seconds']=round(max(age,0))
            elapsed=max(0,int((utcnow()-datetime.fromisoformat(m['kickoff'])).total_seconds()/60))
            m['estimated_minute']=min(elapsed,120)
        return {'matches':rows,'timestamp':iso(utcnow()),'refresh_seconds':20,'minute_is_estimate':True}


def get_slips(uid):
    with connect() as c:
        slips = [dict(x) for x in c.execute('SELECT * FROM slips WHERE user_id=? ORDER BY id DESC LIMIT 50',(uid,))]
        for s in slips:
            s['legs']=[dict(r) for r in c.execute('SELECT l.*, m.home,m.away FROM legs l JOIN matches m ON m.id=l.match_id WHERE slip_id=?',(s['id'],))]
        return slips


MARKET_NAMES={
 'H':'П1','D':'Ничья','A':'П2',
 'O25':'ТБ 2.5','U25':'ТМ 2.5','O15':'ТБ 1.5','U15':'ТМ 1.5','O35':'ТБ 3.5','U35':'ТМ 3.5',
 'GG':'Обе забьют: да','NG':'Обе забьют: нет',
 'F1M1':'Ф1 (-1)','F1P1':'Ф1 (+1)','F2M1':'Ф2 (-1)','F2P1':'Ф2 (+1)',
 'IH15O':'ИТБ1 (1.5)','IH15U':'ИТМ1 (1.5)','IA15O':'ИТБ2 (1.5)','IA15U':'ИТМ2 (1.5)'
}
# All extra markets use transparent fixed game odds, NOT bookmaker lines.
GAME_MARKET_ODDS={
 'O15':1.40,'U15':2.75,'O25':1.92,'U25':1.92,'O35':2.45,'U35':1.53,
 'GG':1.88,'NG':1.88,
 'F1M1':2.65,'F1P1':1.54,'F2M1':2.65,'F2P1':1.54,
 'IH15O':2.20,'IH15U':1.64,'IA15O':2.20,'IA15U':1.64
}

def market_odd(m,pick):
 if pick in ('H','D','A'):
  return float(m[{'H':'odd_h','D':'odd_d','A':'odd_a'}[pick]])
 return GAME_MARKET_ODDS[pick]

def won_pick(pick,home,away):
 # Integer-line handicap: equality is a PUSH (stake refunded, odd 1.0).
 value={
  'H':home>away,'D':home==away,'A':home<away,
  'O15':home+away>=2,'U15':home+away<=1,
  'O25':home+away>=3,'U25':home+away<=2,
  'O35':home+away>=4,'U35':home+away<=3,
  'GG':home>0 and away>0,'NG':home==0 or away==0,
  'F1M1':home-away>1,'F1P1':home-away>-1,
  'F2M1':away-home>1,'F2P1':away-home>-1,
  'IH15O':home>=2,'IH15U':home<=1,
  'IA15O':away>=2,'IA15U':away<=1
 }[pick]
 return value

def pushed_pick(pick,home,away):
 return {'F1M1':home-away==1,'F1P1':home-away==-1,
         'F2M1':away-home==1,'F2P1':away-home==-1}.get(pick,False)

def place_slip(uid, stake, picks, request_key=None):
    if request_key is not None and (not isinstance(request_key,str) or not 8 <= len(request_key) <= 100): raise ValueError('Неверный ключ запроса')
    if type(stake) is not int or not 10 <= stake <= 100000: raise ValueError('Ставка: от 10 до 100 000 монет')
    if not isinstance(picks,list) or not 1 <= len(picks) <= 8: raise ValueError('Добавь от 1 до 8 исходов')
    if len(set(p.get('match_id') for p in picks)) != len(picks): raise ValueError('Один исход на матч')
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if request_key:
            existing=c.execute('SELECT * FROM slips WHERE user_id=? AND request_key=?',(uid,request_key)).fetchone()
            if existing:
                old=c.execute('SELECT match_id,pick FROM legs WHERE slip_id=? ORDER BY match_id',(existing['id'],)).fetchall()
                incoming=sorted((p.get('match_id'),p.get('pick')) for p in picks)
                if existing['stake']!=stake or [(r['match_id'],r['pick']) for r in old]!=incoming:
                    raise ValueError('Ключ запроса уже использован для другой ставки')
                return {'id':existing['id'],'combined_odd':existing['combined_odd'],
                        'potential':round(existing['stake']*existing['combined_odd']),'duplicate':True}
        user=c.execute('SELECT balance FROM users WHERE id=?',(uid,)).fetchone()
        if not user or user['balance']<stake: raise ValueError('Недостаточно монет')
        odds=1.; rows=[]
        for p in picks:
            mid=p.get('match_id'); pick=p.get('pick')
            if type(mid) is not int or pick not in MARKET_NAMES: raise ValueError('Неверный исход')
            m=c.execute('SELECT * FROM matches WHERE id=?',(mid,)).fetchone()
            if not m or m['status'] not in ('SCHEDULED','TIMED') or datetime.fromisoformat(m['kickoff'])<=utcnow()+timedelta(minutes=5):
                raise ValueError('На матч уже нельзя поставить')
            odd=market_odd(m,pick)
            if not 1.01 <= odd <= 100: raise ValueError('Неверный коэффициент')
            odds*=odd; rows.append((mid,pick,odd))
        if odds>10000: raise ValueError('Слишком высокий общий коэффициент')
        c.execute('UPDATE users SET balance=balance-? WHERE id=?',(stake,uid))
        cur=c.execute('INSERT INTO slips(user_id,stake,combined_odd,created_at,request_key) VALUES (?,?,?,?,?)',(uid,stake,round(odds,4),iso(utcnow()),request_key))
        sid=cur.lastrowid
        for mid,pick,odd in rows: c.execute('INSERT INTO legs(slip_id,match_id,pick,locked_odd) VALUES (?,?,?,?)',(sid,mid,pick,odd))
        c.execute('INSERT INTO ledger(user_id,amount,reason,ref,created_at) VALUES (?,?,?,?,?)',(uid,-stake,'Ставка',f'stake:{sid}',iso(utcnow())))
        return {'id':sid,'combined_odd':round(odds,4),'potential':round(stake*odds)}


def daily_bonus(uid):
    today=utcnow().date().isoformat()
    with LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE')
        u=c.execute('SELECT last_bonus FROM users WHERE id=?',(uid,)).fetchone()
        if not u or u['last_bonus']==today: raise ValueError('Сегодня бонус уже получен')
        c.execute('UPDATE users SET balance=balance+200,last_bonus=? WHERE id=?',(today,uid))
        c.execute('INSERT INTO ledger(user_id,amount,reason,ref,created_at) VALUES (?,?,?,?,?)',(uid,200,'Бонус',f'bonus:{uid}:{today}',iso(utcnow())))
        return 200


# Cashout is strictly for a single leg in a live game. Real-money value is zero.
# A transparent approximate in-game model, NOT a trading or bookmaker quotation.
def _poisson(lam, k):
    return math.exp(-lam)*lam**k/math.factorial(k)


def _live_prob(pick, home, away, elapsed):
    remaining=max(0., 90.-elapsed)/90.
    # Project future goals independently; approximate average 1.45 home, 1.15 away / match.
    lam_h=1.45*remaining
    lam_a=1.15*remaining
    probability=0.
    for dh in range(11):
        for da in range(11):
            if won_pick(pick, home+dh, away+da):
                probability+=_poisson(lam_h,dh)*_poisson(lam_a,da)
    return min(1.,max(0.,probability))


def _cashout_quote(c, uid, sid):
    slip=c.execute('SELECT * FROM slips WHERE id=? AND user_id=?',(sid,uid)).fetchone()
    if not slip: raise ValueError('Ставка не найдена')
    if slip['status']!='pending': raise ValueError('Ставка уже рассчитана или закрыта')
    legs=c.execute('SELECT l.*, m.status AS match_status,m.kickoff,m.home_score,m.away_score,m.updated_at FROM legs l JOIN matches m ON m.id=l.match_id WHERE l.slip_id=?',(sid,)).fetchall()
    if len(legs)!=1: raise ValueError('Для экспрессов кэшаут недоступен')
    leg=legs[0]
    if leg['match_status']!='IN_PLAY': raise ValueError('Кэшаут доступен только во время игры')
    if leg['home_score'] is None or leg['away_score'] is None: raise ValueError('Нет достоверного текущего счёта')
    now=utcnow()
    age=(now-datetime.fromisoformat(leg['updated_at'])).total_seconds()
    if age<0 or age>180: raise ValueError('Данные матча устарели — кэшаут временно закрыт')
    elapsed=(now-datetime.fromisoformat(leg['kickoff'])).total_seconds()/60
    # Do not quote near kickoff or the end: irregular stoppage time / data delay.
    if elapsed<2 or elapsed>=85: raise ValueError('Кэшаут сейчас приостановлен')
    p=_live_prob(leg['pick'],leg['home_score'],leg['away_score'],elapsed)
    payout=slip['stake']*leg['locked_odd']
    amount=min(round(payout*0.88*p),round(payout*0.95))
    amount=max(0,amount)
    return {'slip_id':sid,'amount':amount,'probability':round(p,4),'score':f"{leg['home_score']}:{leg['away_score']}",'elapsed':int(elapsed),'expires_in_seconds':min(20,max(0,int(180-age))),'single':True}


def cashout_quote(uid,sid):
    with LOCK,connect() as c:
        return _cashout_quote(c,uid,sid)


def execute_cashout(uid,sid,expected_amount):
    if type(expected_amount) is not int or expected_amount<1: raise ValueError('Недопустимая сумма')
    with LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE')
        q=_cashout_quote(c,uid,sid)
        if q['amount']<1: raise ValueError('Кэшаут пока недоступен: выплата слишком мала')
        if q['amount']!=expected_amount: raise ValueError('Сумма кэшаута изменилась — обнови предложение')
        changed=c.execute("UPDATE slips SET status='cashed_out',payout=?,cashout_at=? WHERE id=? AND user_id=? AND status='pending'",(q['amount'],iso(utcnow()),sid,uid)).rowcount
        if changed!=1: raise ValueError('Ставка уже закрыта')
        c.execute('UPDATE legs SET status=? WHERE slip_id=?',('cashed_out',sid))
        c.execute('UPDATE users SET balance=balance+? WHERE id=?',(q['amount'],uid))
        c.execute('INSERT INTO ledger(user_id,amount,reason,ref,created_at) VALUES (?,?,?,?,?)',(uid,q['amount'],'Кэшаут',f'cashout:{sid}',iso(utcnow())))
        c.execute('INSERT OR IGNORE INTO notifications(user_id,text,created_at) VALUES (?,?,?)',(uid,f'⚽ Одиночная ставка №{sid}: кэшаут +{q["amount"]} 🪙',iso(utcnow())))
        return {'slip_id':sid,'amount':q['amount'],'status':'cashed_out'}


def settle():
    """Called after trusted API updates. A leg resolves only when FINISHED has a full-time score."""
    count=0
    with LOCK, connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for slip in c.execute("SELECT * FROM slips WHERE status='pending'").fetchall():
            legs=c.execute('SELECT l.*,m.status AS match_status,m.home_score,m.away_score FROM legs l JOIN matches m ON l.match_id=m.id WHERE slip_id=?',(slip['id'],)).fetchall()
            results=[]
            for leg in legs:
                if leg['match_status'] in ('CANCELLED','POSTPONED','SUSPENDED'):
                    result='void'
                elif leg['match_status']=='FINISHED' and leg['home_score'] is not None and leg['away_score'] is not None:
                    result='void' if pushed_pick(leg['pick'],leg['home_score'],leg['away_score']) else ('won' if won_pick(leg['pick'],leg['home_score'],leg['away_score']) else 'lost')
                else: result='pending'
                results.append(result)
                if leg['status']!=result: c.execute('UPDATE legs SET status=? WHERE id=?',(result,leg['id']))
            if 'lost' in results: status='lost'; payout=0
            elif 'pending' in results: continue
            else:
                status='won' if 'won' in results else 'void'
                effective=1.
                for leg,result in zip(legs,results):
                    if result=='won': effective*=leg['locked_odd']
                payout=round(slip['stake']*effective)
            c.execute('UPDATE slips SET status=?,payout=? WHERE id=? AND status=?',(status,payout,slip['id'],'pending'))
            if payout:
                c.execute('UPDATE users SET balance=balance+? WHERE id=?',(payout,slip['user_id']))
                c.execute('INSERT INTO ledger(user_id,amount,reason,ref,created_at) VALUES (?,?,?,?,?)',(slip['user_id'],payout,'Расчёт',f'settle:{slip["id"]}',iso(utcnow())))
            message=(f'⚽ Купон №{slip["id"]}: ' +
                     (f'выигрыш +{payout} 🪙' if status=='won' else
                      f'возврат {payout} 🪙' if status=='void' else 'ставка проиграла'))
            c.execute('INSERT OR IGNORE INTO notifications(user_id,text,created_at) VALUES (?,?,?)',
                      (slip['user_id'],message,iso(utcnow())))
            count+=1
    return count


def seed_demo():
    teams=[('Арсенал','Челси','Premier League'),('Реал Мадрид','Барселона','La Liga'),('Бавария','Боруссия Д','Bundesliga'),('Интер','Милан','Serie A'),('ПСЖ','Марсель','Ligue 1'),('Ливерпуль','Ман Сити','Premier League')]
    with LOCK,connect() as c:
        for i,(home,away,league) in enumerate(teams):
            match_id=-(i+1)
            existing=c.execute('SELECT kickoff FROM matches WHERE id=?',(match_id,)).fetchone()
            if existing and datetime.fromisoformat(existing['kickoff']) > utcnow(): continue
            kickoff=iso(utcnow()+timedelta(hours=5+i*7))
            c.execute('INSERT INTO matches(id,league,home,away,kickoff,status,home_score,away_score,odd_h,odd_d,odd_a,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kickoff=excluded.kickoff,status=excluded.status,home_score=NULL,away_score=NULL,updated_at=excluded.updated_at',
              (match_id,league,home,away,kickoff,'SCHEDULED',None,None,1.9+i*.1,3.2,3.8-i*.1,iso(utcnow())))


def profile_summary(uid):
    """Account-only aggregates; transactions are immutable ledger entries."""
    with connect() as c:
        user=c.execute('SELECT id,name,balance,last_bonus FROM users WHERE id=?',(uid,)).fetchone()
        if user is None: raise ValueError('Игрок не найден')
        counts=c.execute("""SELECT COUNT(*) total,
          COALESCE(SUM(CASE WHEN status='won' THEN 1 ELSE 0 END),0) won,
          COALESCE(SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END),0) lost,
          COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),0) pending,
          COALESCE(SUM(CASE WHEN status='cashed_out' THEN 1 ELSE 0 END),0) cashed_out,
          COALESCE(SUM(stake),0) total_staked,
          COALESCE(SUM(payout),0) total_paid
          FROM slips WHERE user_id=?""",(uid,)).fetchone()
        recent=[dict(r) for r in c.execute('SELECT amount,reason,created_at FROM ledger WHERE user_id=? ORDER BY id DESC LIMIT 12',(uid,))]
        completed=counts['won']+counts['lost']
        return {'user':dict(user),'stats':{**dict(counts),'win_rate':round(100*counts['won']/completed,1) if completed else 0},'transactions':recent}



def balance_history(uid, days=30):
    # Private wallet history from posted ledger changes, grouped by UTC date.

    # Positive numbers are credited coins and negative numbers are debited coins.
    # Totals include welcome/admin/bonus entries if recorded in the ledger;
    # the initial 1000 coins are separately disclosed as starting balance.

    if days not in (7, 30, 90):
        raise ValueError('Допустимые периоды: 7, 30, 90 дней')
    from datetime import date
    with connect() as c:
        user=c.execute('SELECT balance FROM users WHERE id=?',(uid,)).fetchone()
        if user is None: raise ValueError('Игрок не найден')
        rows=c.execute('''SELECT substr(created_at,1,10) AS day,
            COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) AS received,
            COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) AS spent
            FROM ledger WHERE user_id=? GROUP BY substr(created_at,1,10)
            ORDER BY day DESC''',(uid,)).fetchall()
        today=utcnow().date()
        totals={'received':sum(int(r['received']) for r in rows),'spent':sum(int(r['spent']) for r in rows)}
        totals['net']=totals['received']-totals['spent']
        byday={r['day']:(int(r['received']),int(r['spent'])) for r in rows}
        daily=[]
        for i in range(days):
            d=(today-timedelta(days=i)).isoformat()
            plus,minus=byday.get(d,(0,0))
            daily.append({'date':d,'received':plus,'spent':minus,'net':plus-minus})
        return {'timezone':'UTC','days':days,'today':daily[0],
                'lifetime':{**totals,'current_balance':int(user['balance']),
                  'starting_balance':int(user['balance'])-totals['net']},
                'daily':daily}


def stats():
    with connect() as c:
        players=[dict(r) for r in c.execute('SELECT name,balance FROM users ORDER BY balance DESC LIMIT 20')]
        return players


def admin_overview():
    with connect() as c:
        return {'users':c.execute('SELECT COUNT(*) FROM users').fetchone()[0],
                'matches':c.execute('SELECT COUNT(*) FROM matches').fetchone()[0],
                'slips':c.execute('SELECT COUNT(*) FROM slips').fetchone()[0],
                'pending_slips':c.execute("SELECT COUNT(*) FROM slips WHERE status='pending'").fetchone()[0],
                'total_virtual_balance':c.execute('SELECT COALESCE(SUM(balance),0) FROM users').fetchone()[0]}

def admin_cancel_match(mid):
    with LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE')
        match=c.execute('SELECT status FROM matches WHERE id=?',(mid,)).fetchone()
        if not match: raise ValueError('Матч не найден')
        if match['status']=='FINISHED': raise ValueError('Нельзя отменить завершённый матч')
        c.execute("UPDATE matches SET status='CANCELLED',updated_at=? WHERE id=?",(iso(utcnow()),mid))
    return {'settled':settle()}


def admin_players(limit=50):
    with connect() as c:
        return [dict(row) for row in c.execute(
            "SELECT u.id,u.name,u.balance,u.last_bonus,COUNT(s.id) AS slips FROM users u LEFT JOIN slips s ON s.user_id=u.id GROUP BY u.id ORDER BY u.id DESC LIMIT ?", (limit,))]

def admin_adjust_balance(uid, amount, operator_id, reason):
    import uuid
    if type(amount) is not int or amount == 0 or abs(amount)>100000:
        raise ValueError('Изменение: от -100 000 до +100 000 монет')
    if not reason or not reason.strip() or len(reason)>120:
        raise ValueError('Укажи причину (до 120 символов)')
    with LOCK,connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT balance FROM users WHERE id=?',(uid,)).fetchone()
        if not row: raise ValueError('Игрок не найден')
        if row['balance']+amount<0: raise ValueError('Недостаточно монет')
        c.execute('UPDATE users SET balance=balance+? WHERE id=?',(amount,uid))
        c.execute('INSERT INTO ledger(user_id,amount,reason,ref,created_at) VALUES(?,?,?,?,?)',
                  (uid,amount,f'Администратор {operator_id}: {reason.strip()}',f'admin:{uuid.uuid4().hex}',iso(utcnow())))
        return {'id':uid,'balance':row['balance']+amount}

def admin_recent_activity(limit=30):
    with connect() as c:
        return [dict(row) for row in c.execute(
          'SELECT l.id,l.user_id,u.name,l.amount,l.reason,l.created_at FROM ledger l JOIN users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT ?',(limit,))]
