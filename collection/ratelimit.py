import logging
import time

from django.core.cache import cache
from django.shortcuts import render

logger = logging.getLogger(__name__)


def get_rate_limit_identity(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        client_ip = forwarded_for.split(",", 1)[0].strip()
    else:
        client_ip = request.META.get("REMOTE_ADDR", "unknown")
    return f"ip:{client_ip}"


def _parse_rate(rate):
    count, period = rate.split("/", 1)
    count = int(count)
    period_seconds = {
        "s": 1,
        "sec": 1,
        "second": 1,
        "m": 60,
        "min": 60,
        "minute": 60,
        "h": 60 * 60,
        "hour": 60 * 60,
    }[period]
    return count, period_seconds


def is_rate_limited(request, scope, anonymous_rate, authenticated_rate=None):
    rate = authenticated_rate if request.user.is_authenticated and authenticated_rate else anonymous_rate
    limit, period_seconds = _parse_rate(rate)
    identity = get_rate_limit_identity(request)
    window = int(time.time() // period_seconds)
    cache_key = f"ratelimit:{scope}:{identity}:{window}"

    added = cache.add(cache_key, 1, period_seconds + 1)
    if added:
        count = 1
    else:
        try:
            count = cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, period_seconds + 1)
            count = 1

    if count > limit:
        logger.warning("Rate limit hit", extra={"scope": scope, "identity": identity, "limit": rate})
        return True
    return False


def rate_limited_response(request):
    return render(request, "429.html", status=429)
