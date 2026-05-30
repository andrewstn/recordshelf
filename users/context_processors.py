from .onboarding import get_onboarding_progress


NAV_SECTIONS = {
    'home': 'home',
    'search': 'search',
    'album_detail': 'search',
    'artist_detail': 'search',
    'sync_artist': 'search',
    'user_directory': 'community',
    'feed': 'feed',
    'profile': 'profile',
    'edit_profile': 'profile',
    'followers_list': 'profile',
    'following_list': 'profile',
    'edit_item': 'profile',
    'getting_started': 'getting_started',
    'support': 'support',
    'terms': 'terms',
}


def onboarding_progress(request):
    progress = None
    if request.user.is_authenticated:
        progress = get_onboarding_progress(request.user)
    url_name = request.resolver_match.url_name if request.resolver_match else None
    return {
        'active_nav_section': NAV_SECTIONS.get(url_name),
        'onboarding_nav_progress': progress,
    }
