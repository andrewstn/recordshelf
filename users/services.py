from django.contrib.auth import get_user_model

User = get_user_model()

def toggle_follow(user, user_to_follow):
    """
    Toggles the follow status between two users. 
    Returns True if a follow was added, False if it was removed.
    """
    # Prevent a user from following themselves
    if user == user_to_follow:
        return None 

    # Check if the relationship already exists
    if user.following.filter(id=user_to_follow.id).exists():
        # If they are already following, unfollow
        user.following.remove(user_to_follow)
        return False
    else:
        # If they aren't following, add the follow
        user.following.add(user_to_follow)
        return True