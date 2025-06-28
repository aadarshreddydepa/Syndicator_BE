from rest_framework import serializers
from .models import CustomUser, Transactions, Splitwise

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['user_id', 'username', 'email', 'phone_number']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only = True)
    
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'phone_number']
    
    def create(self, validated_data):
        user = CustomUser.objects.create_user(**validated_data)
        user.save()
        return user

# Updated Splitwise Serializer with Commission Support
class SplitwiseSerializer(serializers.ModelSerializer):
    syndicator_username = serializers.CharField(source='syndicator_id.username', read_only=True)
    syndicator_name = serializers.CharField(source='syndicator_id.name', read_only=True)
    syndicator_email = serializers.CharField(source='syndicator_id.email', read_only=True)
    
    # Commission-related fields
    original_interest = serializers.FloatField(source='interest_amount', read_only=True)
    interest_after_commission = serializers.SerializerMethodField()
    commission_deducted = serializers.SerializerMethodField()
    
    class Meta:
        model = Splitwise
        fields = [
            'splitwise_id', 
            'syndicator_id', 
            'syndicator_username', 
            'syndicator_name', 
            'syndicator_email',
            'principal_amount', 
            'original_interest',
            'interest_after_commission',
            'commission_deducted',
            'created_at'
        ]
    
    def get_interest_after_commission(self, obj):
        return obj.get_interest_after_commission()
    
    def get_commission_deducted(self, obj):
        if not obj.transaction_id.risk_taker_flag:
            return 0
        
        total_syndicators = obj.transaction_id.splitwise_entries.count()
        if total_syndicators == 0:
            return 0
            
        return obj.transaction_id.risk_taker_commission / total_syndicators

# Updated Portfolio Serializer with Commission Support
class PortfolioSerializer(serializers.ModelSerializer):
    splitwise_entries = SplitwiseSerializer(many=True, read_only=True)
    risk_taker_username = serializers.CharField(source='risk_taker_id.username', read_only=True)
    risk_taker_name = serializers.CharField(source='risk_taker_id.name', read_only=True)
    
    # Commission-related fields
    total_commission_earned = serializers.SerializerMethodField()
    commission_flag = serializers.BooleanField(source='risk_taker_flag', read_only=True)
    commission_rate = serializers.FloatField(source='risk_taker_commission', read_only=True)
    
    class Meta:
        model = Transactions
        fields = [
            'transaction_id', 
            'risk_taker_id', 
            'risk_taker_username',
            'risk_taker_name',
            'syndicators', 
            'total_principal_amount', 
            'total_interest', 
            'commission_flag',
            'commission_rate',
            'total_commission_earned',
            'created_at', 
            'start_date',
            'splitwise_entries'
        ]
    
    def get_total_commission_earned(self, obj):
        """Calculate total commission earned by risk taker"""
        if not obj.risk_taker_flag:
            return 0
        return obj.risk_taker_commission