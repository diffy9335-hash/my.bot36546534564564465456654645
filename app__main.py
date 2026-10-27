import os, asyncio, logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import init_db, get_user, get_matches, place_slip, get_slips, validate_init_data, daily_bonus, stats, settle, admin_overview, admin_cancel_match, admin_players, admin_adjust_balance, admin_recent_activity, cashout_quote, execute_cashout, get_live_center, profile_summary, balance_history
from .avatars import save_avatar, avatar_path, MAX_BYTES
from .sync import polling_loop, synchronize
from .operations import init_operations, operations_overview
from .progression import init_progression, summary as progression_summary, claim as claim_quest
from .referrals import init_referrals, enroll, record_visit, summary as referral_summary
from .seasons import init_seasons, standings, follow, unfollow, follow_stats, subscriptions
from .social import init_social, messages as chat_messages, send as chat_send, report as chat_report, public_profile, moderation_queue, remove_message, mute_player
from .community import init_community, dashboard, save_daily_snapshot, create_post, feed, like, report_post, remove_post, reports, notify, get_notifications, mark_read, ranking_audit, audit_queue
BASE=Path(__file__).resolve().parent.parent
logger=logging.getLogger('rdg.auth')

@asynccontextmanager
async def lifespan(app):
    init_db()
    init_operations()
    init_progression()
    init_referrals()
    init_social()
    init_seasons()
    init_community()
    task=asyncio.create_task(polling_loop())
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass

app=FastAPI(title='Football Virtual League',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=str(BASE/'static')),name='static')

@app.get('/')
def index(): return FileResponse(BASE/'static'/'index.html')


def auth(x_telegram_init_data: str=Header(default=''), x_dev_user: str=Header(default='')):
    if os.getenv('DEV_AUTH','false').lower()=='true' and x_dev_user:
        if not x_dev_user.isdigit(): raise HTTPException(401,'Неверный тестовый ID')
        uid=int(x_dev_user)
        if uid < 1: raise HTTPException(401,'Неверный ID')
        user=get_user(uid,'Тестовый игрок')
        record_visit(uid)
        return user
    try:
        u=validate_init_data(x_telegram_init_data,os.getenv('BOT_TOKEN',''))
        uid=int(u['id'])
        name=u.get('first_name') or u.get('username') or 'Игрок'
        from urllib.parse import parse_qsl
        signed=dict(parse_qsl(x_telegram_init_data)).get('start_param','')
        if signed: enroll(uid,signed,name)
        user=get_user(uid,name)
        record_visit(uid)
        return user
    except (ValueError,KeyError,TypeError) as exc:
        # Never log raw initData, user JSON, full token or Telegram hashes.
        from urllib.parse import parse_qsl
        try: fields=sorted({k for k,_ in parse_qsl(x_telegram_init_data,keep_blank_values=True)})
        except ValueError: fields=[]
        logger.warning('Telegram login rejected: %s; init_data_present=%s; fields=%s; token_present=%s',
                       str(exc),bool(x_telegram_init_data),','.join(fields),bool(os.getenv('BOT_TOKEN','')))
        raise HTTPException(401,str(exc))

class Pick(BaseModel):
    match_id:int
    pick:str
class SlipRequest(BaseModel):
    stake:int
    request_key:str|None=None
    picks:list[Pick]=Field(min_length=1,max_length=8)

@app.get('/api/me')
def me(user=Depends(auth)):
    admins={int(x) for x in os.getenv('ADMIN_TELEGRAM_IDS','').split(',') if x.strip().isdigit()}
    return {**user, 'is_admin':user['id'] in admins}
@app.get('/api/profile')
def profile(user=Depends(auth)):
    return profile_summary(user['id'])

@app.put('/api/avatar')
async def upload_avatar(request:Request, user=Depends(auth)):
    length = request.headers.get('content-length')
    if length and (not length.isdigit() or int(length)>MAX_BYTES):
        raise HTTPException(413,'Максимальный размер фото 2 МБ')
    parts=[]
    size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>MAX_BYTES: raise HTTPException(413,'Максимальный размер фото 2 МБ')
        parts.append(chunk)
    data=b''.join(parts)
    try: save_avatar(user['id'], data, request.headers.get('content-type','').split(';')[0].lower())
    except ValueError as exc: raise HTTPException(400,str(exc))
    return {'ok':True}

@app.get('/api/avatars/{player_id}')
def get_avatar(player_id:int):
    if player_id<=0: raise HTTPException(404,'Фото не найдено')
    path=avatar_path(player_id)
    if not path.is_file(): raise HTTPException(404,'Фото не найдено')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=300','X-Content-Type-Options':'nosniff'})

@app.get('/api/profile/balance-history')
def profile_balance_history(days:int=30,user=Depends(auth)):
    try: return balance_history(user['id'],days)
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get('/api/referrals')
def referrals(user=Depends(auth)):
    return referral_summary(user['id'])

@app.get('/api/progression')
def progression(user=Depends(auth)):
    return progression_summary(user['id'])

@app.post('/api/quests/{quest_id}/claim')
def claim_daily_quest(quest_id:str,user=Depends(auth)):
    try: return claim_quest(user['id'],quest_id)
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get('/api/matches')
def matches(): return {'matches':get_matches(),'odds_source':'synthetic_game_odds'}
@app.get('/api/live')
def live_center(): return get_live_center()

@app.get('/api/slips')
def slips(user=Depends(auth)): return get_slips(user['id'])
@app.post('/api/slips')
def bet(payload:SlipRequest,user=Depends(auth)):
    try: return place_slip(user['id'],payload.stake,[p.model_dump() for p in payload.picks],payload.request_key)
    except ValueError as exc: raise HTTPException(400,str(exc))
@app.get('/api/slips/{slip_id}/cashout')
def quote_cashout(slip_id:int,user=Depends(auth)):
    try: return cashout_quote(user['id'],slip_id)
    except ValueError as exc: raise HTTPException(400,str(exc))

class CashoutRequest(BaseModel):
    expected_amount:int

@app.post('/api/slips/{slip_id}/cashout')
def close_single(slip_id:int,payload:CashoutRequest,user=Depends(auth)):
    try: return execute_cashout(user['id'],slip_id,payload.expected_amount)
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.post('/api/bonus')
def bonus(user=Depends(auth)):
    try: return {'amount':daily_bonus(user['id'])}
    except ValueError as exc: raise HTTPException(400,str(exc))
@app.get('/api/ranking')
def ranking(): return stats()
@app.get('/api/seasons/current')
def season_ranking(user=Depends(auth)):
    return dashboard(user['id'])

@app.get('/api/subscriptions')
def my_subscriptions(user=Depends(auth)):
    return {'players':subscriptions(user['id'])}

@app.get('/api/players/{player_id}/subscription')
def subscription_detail(player_id:int,user=Depends(auth)):
    try: return follow_stats(player_id,user['id'])
    except ValueError as exc: raise HTTPException(404,str(exc))

@app.post('/api/players/{player_id}/follow')
def follow_player(player_id:int,user=Depends(auth)):
    try:
        result=follow(user['id'],player_id)
        notify(player_id,'follower','На твой профиль подписался новый игрок',f'follow:{user["id"]}:{player_id}')
        return result
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.delete('/api/players/{player_id}/follow')
def unfollow_player(player_id:int,user=Depends(auth)):
    try: return unfollow(user['id'],player_id)
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get('/api/health')
def health(): return {'ok':True}

@app.post('/api/admin/sync')
async def sync_now(user=Depends(auth)):
    admins={int(x) for x in os.getenv('ADMIN_TELEGRAM_IDS','').split(',') if x.strip().isdigit()}
    if user['id'] not in admins: raise HTTPException(403,'Только администратор')
    return await synchronize()


def require_admin(user):
    admins={int(x) for x in os.getenv('ADMIN_TELEGRAM_IDS','').split(',') if x.strip().isdigit()}
    if user['id'] not in admins: raise HTTPException(403,'Только администратор')
    return user

@app.get('/api/admin/overview')
def overview(user=Depends(auth)):
    require_admin(user)
    return admin_overview()

@app.post('/api/admin/matches/{match_id}/cancel')
def cancel_match(match_id:int,user=Depends(auth)):
    require_admin(user)
    try: return admin_cancel_match(match_id)
    except ValueError as exc: raise HTTPException(400,str(exc))

class BalanceChange(BaseModel):
    amount:int
    reason:str=Field(min_length=1,max_length=120)

@app.get('/api/admin/players')
def players(user=Depends(auth)):
    require_admin(user)
    return admin_players()

@app.get('/api/admin/activity')
def activity(user=Depends(auth)):
    require_admin(user)
    return admin_recent_activity()

@app.post('/api/admin/players/{user_id}/balance')
def adjust_balance(user_id:int,payload:BalanceChange,user=Depends(auth)):
    require_admin(user)
    try: return admin_adjust_balance(user_id,payload.amount,user['id'],payload.reason)
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get("/api/admin/operations")
def operations(user=Depends(auth)):
    require_admin(user)
    return operations_overview()


# Social hub — all writes require a verified Telegram Mini App session.
class ChatPost(BaseModel):
    body: str = Field(min_length=1,max_length=350)

@app.get('/api/chat/messages')
def get_chat(after:int=0,limit:int=60,user=Depends(auth)):
    try: return {'messages':chat_messages(after,limit)}
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.post('/api/chat/messages',status_code=201)
def send_chat(payload:ChatPost,user=Depends(auth)):
    try: return chat_send(user['id'],payload.body)
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.post('/api/chat/messages/{message_id}/report')
def report_chat(message_id:int,user=Depends(auth)):
    try: return chat_report(user['id'],message_id)
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get('/api/players/{player_id}/public')
def player_card(player_id:int,user=Depends(auth)):
    try: return public_profile(player_id)
    except ValueError as exc: raise HTTPException(404,str(exc))

@app.get('/api/admin/chat/reports')
def chat_reports(user=Depends(auth)):
    require_admin(user)
    return moderation_queue()

@app.delete('/api/admin/chat/messages/{message_id}')
def delete_chat(message_id:int,user=Depends(auth)):
    require_admin(user)
    try: return remove_message(message_id)
    except ValueError as exc: raise HTTPException(404,str(exc))

class MuteRequest(BaseModel):
    minutes:int=Field(ge=1,le=10080)

@app.post('/api/admin/chat/players/{player_id}/mute')
def mute_chat(player_id:int,payload:MuteRequest,user=Depends(auth)):
    require_admin(user)
    try: return mute_player(player_id,payload.minutes)
    except ValueError as exc: raise HTTPException(400,str(exc))


class PredictionPost(BaseModel):
    match_id:int
    pick:str
    comment:str=Field(default='',max_length=280)

@app.get('/api/community/feed')
def community_feed(mode:str='all',user=Depends(auth)):
    try:return {'posts':feed(user['id'],mode)}
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/community/posts',status_code=201)
def community_post(payload:PredictionPost,user=Depends(auth)):
    try:return create_post(user['id'],payload.match_id,payload.pick,payload.comment)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/community/posts/{post_id}/like')
def community_like(post_id:int,user=Depends(auth)):
    try:return like(user['id'],post_id)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/community/posts/{post_id}/report')
def community_report(post_id:int,user=Depends(auth)):
    try:return report_post(user['id'],post_id)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/notifications')
def notifications(user=Depends(auth)):
    return {'items':get_notifications(user['id'])}

@app.post('/api/notifications/{notification_id}/read')
def notification_read(notification_id:int,user=Depends(auth)):
    try:return mark_read(user['id'],notification_id)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/admin/community/reports')
def admin_post_reports(user=Depends(auth)):
    require_admin(user)
    return reports()

@app.delete('/api/admin/community/posts/{post_id}')
def admin_remove_post(post_id:int,user=Depends(auth)):
    require_admin(user)
    try:return remove_post(post_id)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/admin/seasons/audit')
def admin_season_audit(user=Depends(auth)):
    require_admin(user)
    ranking_audit()
    return {'flags':audit_queue()}

@app.post('/api/admin/seasons/snapshot')
def admin_snapshot(user=Depends(auth)):
    require_admin(user)
    return {'players':save_daily_snapshot()}
