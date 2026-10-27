# Launch the Telegram polling bot from the embedded RDG distribution.
import asyncio
from dotenv import load_dotenv
from run import prepare

load_dotenv()
prepare()
from app.bot import main

if __name__ == '__main__':
    asyncio.run(main())
