"""Safe, per-user JPEG avatars, stored outside the publicly served static directory."""
from io import BytesIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent / 'avatars'
MAX_BYTES = 2 * 1024 * 1024


def save_avatar(user_id: int, data: bytes, content_type: str) -> None:
    if content_type not in ('image/jpeg', 'image/png', 'image/webp'):
        raise ValueError('Поддерживаются только JPG, PNG и WEBP')
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Фото должно быть размером до 2 МБ')
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in ('JPEG', 'PNG', 'WEBP'):
                raise ValueError('Неверный формат файла')
            if source.width * source.height > 16_000_000:
                raise ValueError('Слишком большое разрешение')
            source.thumbnail((512, 512))
            rgb = Image.new('RGB', source.size, '#111a29')
            if source.mode in ('RGBA', 'LA') or 'transparency' in source.info:
                rgba = source.convert('RGBA')
                rgb.paste(rgba, mask=rgba.getchannel('A'))
            else:
                rgb.paste(source.convert('RGB'))
            ROOT.mkdir(parents=True, exist_ok=True)
            temp = ROOT / f'.{int(user_id)}.tmp'
            rgb.save(temp, format='JPEG', quality=85, optimize=True)
            temp.replace(ROOT / f'{int(user_id)}.jpg')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Не удалось прочитать фотографию') from exc


def avatar_path(user_id: int) -> Path:
    return ROOT / f'{int(user_id)}.jpg'
