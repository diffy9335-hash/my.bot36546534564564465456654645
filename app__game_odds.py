"""Deterministic fictional prices for RDG virtual matches.

NOT bookmaker odds, and NOT real-world predictive statistics. Club name tiers
are editorial defaults; unavailable performance data is never fabricated.
"""
import hashlib
import math

TIERS = {
    'real madrid': 89, 'barcelona': 87, 'manchester city': 90,
    'liverpool': 88, 'arsenal': 87, 'chelsea': 79,
    'manchester united': 77, 'tottenham': 78, 'newcastle': 76,
    'bayern': 91, 'borussia dortmund': 83, 'leverkusen': 83,
    'inter': 86, 'internazionale': 86, 'milan': 82, 'juventus': 82,
    'napoli': 83, 'roma': 79, 'atalanta': 79,
    'paris saint-germain': 90, 'monaco': 80, 'marseille': 78,
    'atletico': 84, 'atlético': 84, 'athletic club': 78,
}


def club_strength(name):
    """Approximate game rating, never presented as verified current form."""
    name = name.casefold()
    for club, score in TIERS.items():
        if club in name:
            return score
    digest = hashlib.sha256(name.encode('utf-8')).digest()
    return 67 + digest[0] % 12


def game_odds(home, away):
    """Normalized 1-X-2 game odds, stable per team pairing."""
    diff = (club_strength(home) - club_strength(away)) / 13 + 0.24
    p_draw = min(0.31, max(0.19, 0.29 - 0.045 * abs(diff)))
    p_home = (1 - p_draw) / (1 + math.exp(-diff))
    p_away = 1 - p_draw - p_home
    # 4% fictional overround; no commercial odds feed.
    return tuple(round(min(15., max(1.06, 1 / (p * 1.04))), 2) for p in (p_home, p_draw, p_away))
