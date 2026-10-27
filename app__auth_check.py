"""Local, secret-safe diagnostics for Telegram Mini App auth.
Run from project folder: python -m app.auth_check
"""
import os
from pathlib import Path
from dotenv import dotenv_values


def main():
    env_file = Path(__file__).resolve().parent.parent / '.env'
    values = dotenv_values(env_file) if env_file.exists() else {}
    file_token = (values.get('BOT_TOKEN') or '').strip()
    process_token = os.environ.get('BOT_TOKEN')
    effective_token = process_token if process_token is not None else file_token
    print('RDG AUTH CHECK (no secrets printed)')
    print('Project .env present:', env_file.exists())
    print('BOT_TOKEN in .env:', bool(file_token))
    print('BOT_TOKEN in Windows environment:', process_token is not None)
    print('Environment overrides .env:', process_token is not None and process_token != values.get('BOT_TOKEN'))
    print('Effective token present:', bool(effective_token))
    print('Effective bot ID:', effective_token.split(':', 1)[0] if ':' in effective_token else 'INVALID')
    print('Token whitespace:', effective_token != effective_token.strip())
    url = (os.environ.get('PUBLIC_URL') or values.get('PUBLIC_URL') or '')
    print('Public URL is HTTPS:', url.startswith('https://'))
    print('DEV_AUTH effective:', os.environ.get('DEV_AUTH', values.get('DEV_AUTH', 'false')))
    if process_token is not None and process_token != values.get('BOT_TOKEN'):
        print('ACTION: Windows BOT_TOKEN overrides .env. Remove the stale environment value or update it.')
    else:
        print('NEXT: If signatures fail, confirm the token belongs to the exact bot that opens the Mini App; rotate compromised token via BotFather.')
    print('Do NOT share any tokens or Telegram initData.')

if __name__ == '__main__':
    main()
