import os, asyncio
from dotenv import load_dotenv
from .core import connect, LOCK, utcnow, iso, get_user
from .referrals import init_referrals, enroll, record_visit
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, BotCommand
load_dotenv()

async def send_notifications(bot):
    # Single bot worker. Messages are marked sent only after Telegram confirms sending.
    while True:
        try:
            with LOCK,connect() as c:
                pending=c.execute('SELECT id,user_id,text FROM notifications WHERE sent_at IS NULL ORDER BY id LIMIT 25').fetchall()
            for n in pending:
                try:
                    await bot.send_message(n['user_id'], n['text'])
                except Exception:
                    # Users may block bot; retry on next polling cycle.
                    continue
                with LOCK,connect() as c:
                    c.execute('UPDATE notifications SET sent_at=? WHERE id=? AND sent_at IS NULL',(iso(utcnow()),n['id']))
        except Exception:
            pass
        await asyncio.sleep(30)

async def main():
    token=os.getenv('BOT_TOKEN')
    url=os.getenv('PUBLIC_URL','').rstrip('/')
    if not token or token=='PASTE_BOTFATHER_TOKEN': raise RuntimeError('Set BOT_TOKEN in .env')
    if not url.startswith('https://'): raise RuntimeError('PUBLIC_URL must be HTTPS')
    init_referrals()
    bot=Bot(token=token); dp=Dispatcher()
    @dp.message(CommandStart())
    async def start(message:Message):
        if message.from_user:
            payload=(message.text or '').split(maxsplit=1)
            code=payload[1].strip() if len(payload)>1 else ''
            if code: enroll(message.from_user.id,code,message.from_user.first_name or 'Игрок')
            get_user(message.from_user.id,message.from_user.first_name or 'Игрок')
            record_visit(message.from_user.id)
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⚽ Открыть RDG',web_app=WebAppInfo(url=url))]])
        await message.answer('⚽ RDG — Rates Diffy Game\n\n🎁 1000 монет на старте, каждый день +200.\nПрогнозы только на игровые монеты — без денег, покупок и вывода.',reply_markup=kb)
    @dp.message(Command('help'))
    async def help_(message:Message):
        await message.answer('Открой /start и нажми кнопку. Матчи обновляются сервером автоматически. Это игра на виртуальные монеты.')
    await bot.set_my_commands([BotCommand(command='start',description='Открыть Mini App'),BotCommand(command='help',description='Помощь')])
    notifier=asyncio.create_task(send_notifications(bot))
    try: await dp.start_polling(bot)
    finally:
        notifier.cancel()
        try: await notifier
        except asyncio.CancelledError: pass
        await bot.session.close()

if __name__=='__main__': asyncio.run(main())
