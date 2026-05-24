from django.contrib.auth import get_user_model
from collection.models import CollectionItem

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

def set_favorite_record(user, record):
    """Sets the user's favorite record, verifying they own it first."""
    if not CollectionItem.objects.filter(user=user, record=record).exists():
        raise ValueError("You cannot favorite a record you do not own.")
    
    user.favorite_record = record
    user.save()
    return True

def toggle_shelf_record(user, record):
    """
    Adds or removes a record from the top 6 shelf. 
    Enforces ownership and the 6-record limit.
    """
    if not CollectionItem.objects.filter(user=user, record=record).exists():
        raise ValueError("You cannot add a record you do not own to your shelf.")
    
    # If it's already on the shelf, remove it
    if user.shelf.filter(id=record.id).exists():
        user.shelf.remove(record)
        return False # Indicates removed
    
    # If adding a new one, check the limit first
    if user.shelf.count() >= 6:
        raise ValueError("Your shelf is full! Remove a record before adding a new one.")
        
    user.shelf.add(record)
    return True # Indicates added