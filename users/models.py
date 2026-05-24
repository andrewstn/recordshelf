from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    # We can add profile pictures, bios, and follower logic here later
    pass
