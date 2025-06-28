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
    total_principal_amount = models.FloatField(validators=[MinValueValidator(0)])
    total_interest = models.FloatField(validators=[MinValueValidator(0)])
    # NEW FIELDS FOR COMMISSION
    risk_taker_commission = models.FloatField(validators=[MinValueValidator(0)], default=0)
    risk_taker_flag = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(blank=False)

class Splitwise(models.Model):
    splitwise_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.ForeignKey(Transactions, on_delete=models.CASCADE, related_name='splitwise_entries')
    # NEW: Associate each split with a specific user
    syndicator_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='splitwise_entries')
    principal_amount = models.FloatField(validators=[MinValueValidator(0)])
    interest_amount = models.FloatField(validators=[MinValueValidator(0)])  # This stores ORIGINAL interest
    created_at = models.DateTimeField(auto_now_add=True)
    
    def get_interest_after_commission(self):
        """Calculate interest after commission deduction"""
        if not self.transaction_id.risk_taker_flag:
            return self.interest_amount
        
        # Get all syndicators excluding the risk taker (they don't pay commission to themselves)
        syndicators_excluding_risk_taker = self.transaction_id.splitwise_entries.exclude(
            syndicator_id=self.transaction_id.risk_taker_id
        )
        
        # If no syndicators excluding risk taker, return original interest
        if syndicators_excluding_risk_taker.count() == 0:
            return self.interest_amount
        
        # Calculate total interest available for commission (from syndicators excluding risk taker)
        total_interest_for_commission = sum(entry.interest_amount for entry in syndicators_excluding_risk_taker)
        
        # Calculate commission amount as percentage of total interest
        commission_amount = (self.transaction_id.risk_taker_commission / 100) * total_interest_for_commission
        
        # Calculate commission per syndicator (excluding risk taker)
        commission_per_syndicator = commission_amount / syndicators_excluding_risk_taker.count()
        
        # If this entry is for the risk taker, they don't pay commission to themselves
        if self.syndicator_id == self.transaction_id.risk_taker_id:
            return self.interest_amount
        
        # For other syndicators, deduct commission
        return max(0, self.interest_amount - commission_per_syndicator)
    
    def get_commission_deducted(self):
        """Get the commission amount deducted from this entry"""
        if not self.transaction_id.risk_taker_flag:
            return 0
        
        # Risk taker doesn't pay commission to themselves
        if self.syndicator_id == self.transaction_id.risk_taker_id:
            return 0
        
        # Get all syndicators excluding the risk taker
        syndicators_excluding_risk_taker = self.transaction_id.splitwise_entries.exclude(
            syndicator_id=self.transaction_id.risk_taker_id
        )
        
        if syndicators_excluding_risk_taker.count() == 0:
            return 0
        
        # Calculate total interest available for commission
        total_interest_for_commission = sum(entry.interest_amount for entry in syndicators_excluding_risk_taker)
        
        # Calculate commission amount as percentage of total interest
        commission_amount = (self.transaction_id.risk_taker_commission / 100) * total_interest_for_commission
        
        return commission_amount / syndicators_excluding_risk_taker.count()
    
    def __str__(self):
        return f"Split for {self.syndicator_id.username} in transaction {self.transaction_id.transaction_id}"