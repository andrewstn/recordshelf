import posthog
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone


def capture_onboarding_event(user, event, **properties):
    with posthog.new_context():
        posthog.identify_context(str(user.id))
        if properties:
            posthog.capture(event, properties=properties)
        else:
            posthog.capture(event)


def onboarding_step_destination(user, step_key):
    profile_url = reverse('profile', args=[user.username])
    destinations = {
        'profile-picture': reverse('edit_profile'),
        'tagline': reverse('edit_profile'),
        'collection': reverse('search'),
        'shelf': f'{profile_url}#collection',
        'current-spin': f'{profile_url}#collection',
        'rating': f'{profile_url}#collection' if user.collection.exists() else reverse('search'),
    }
    return destinations.get(step_key)


def get_onboarding_progress(user):
    if (
        not user.is_authenticated
        or not user.onboarding_started_at
        or user.onboarding_dismissed_at
        or user.onboarding_completed_at
    ):
        return None

    collection_stats = user.collection.aggregate(
        collection_count=Count('id'),
        rating_count=Count('id', filter=Q(rating__isnull=False)),
    )
    status = {
        'profile-picture': bool(user.profile_picture),
        'tagline': bool(user.tagline and user.tagline.strip()),
        'collection': collection_stats['collection_count'] > 0,
        'shelf': user.shelf.exists(),
        'current-spin': bool(user.favorite_record_id),
        'rating': collection_stats['rating_count'] > 0,
    }

    if all(status.values()):
        user.onboarding_completed_at = timezone.now()
        user.save(update_fields=['onboarding_completed_at'])
        capture_onboarding_event(user, 'onboarding_completed')
        return None

    completed_count = sum(status.values())
    return {
        'status': status,
        'completed_count': completed_count,
        'total_count': len(status),
        'percent_complete': round(completed_count / len(status) * 100),
    }


def get_onboarding_checklist(user):
    progress = get_onboarding_progress(user)
    if not progress:
        return None

    if not user.onboarding_viewed_at:
        user.onboarding_viewed_at = timezone.now()
        user.save(update_fields=['onboarding_viewed_at'])
        capture_onboarding_event(user, 'getting_started_viewed')

    step_content = [
        ('profile-picture', 'Customize your profile', 'Add a photo so your shelf feels like yours.'),
        ('tagline', 'Add a tagline', 'Share a quick note about your taste.'),
        ('collection', 'Add your first record', 'Search the catalog and start your crate.'),
        ('shelf', 'Place a record on your shelf', 'Choose up to six records to feature publicly.'),
        ('current-spin', "Set what's currently spinning", "Show collectors what's on your turntable right now."),
        ('rating', 'Rate a record', 'Add your first 1-5 star rating.'),
    ]
    steps = [
        {
            'key': key,
            'title': title,
            'description': description,
            'completed': progress['status'][key],
            'cta_url': reverse('onboarding_step', args=[key]),
        }
        for key, title, description in step_content
    ]
    return {
        'steps': steps,
        'completed_count': progress['completed_count'],
        'total_count': progress['total_count'],
        'percent_complete': progress['percent_complete'],
    }
