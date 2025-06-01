from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
import uuid


class CustomUser(AbstractUser):
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=26, blank=True, null=True)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.email
    
class FriendList(models.Model):
    friend_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='friend_lists')
    
    # Many-to-Many relationship with CustomUser for mutual friends
    mutual_friends = models.ManyToManyField(
        CustomUser, 
        blank=True, 
        related_name='mutual_friend_of'
    )
    created_at = models.DateTimeField(auto_now_add=True)

class FriendRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('canceled', 'Canceled'),
    ]

    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sent_friend_requests')
    requested_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_friend_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

class Transactions(models.Model):
    transaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    risk_taker_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='risk_taker')
    syndicators = models.JSONField(default=list, blank=True)
    total_prinicipal_amount = models.FloatField(validators=[MinValueValidator(0)])
    total_interest = models.FloatField(validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(blank=False)

class Splitwise(models.Model):
    splitwise_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.ForeignKey(Transactions, on_delete=models.CASCADE, related_name='splitwise_entries')
    principal_amount = models.FloatField(validators=[MinValueValidator(0)])
    interest_amount = models.FloatField(validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)