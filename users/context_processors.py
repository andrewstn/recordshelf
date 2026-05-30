from .onboarding import get_onboarding_progress


def onboarding_progress(request):
    progress = None
    if request.user.is_authenticated:
        progress = get_onboarding_progress(request.user)
    return {'onboarding_nav_progress': progress}
