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

# New Splitwise Serializer
class SplitwiseSerializer(serializers.ModelSerializer):
    syndicator_username = serializers.CharField(source='syndicator_id.username', read_only=True)
    syndicator_name = serializers.CharField(source='syndicator_id.name', read_only=True)
    syndicator_email = serializers.CharField(source='syndicator_id.email', read_only=True)
    
    class Meta:
        model = Splitwise
        fields = [
            'splitwise_id', 
            'syndicator_id', 
            'syndicator_username', 
            'syndicator_name', 
            'syndicator_email',
            'principal_amount', 
            'interest_amount', 
            'created_at'
        ]

# Updated Portfolio Serializer with Splitwise entries
class PortfolioSerializer(serializers.ModelSerializer):
    splitwise_entries = SplitwiseSerializer(many=True, read_only=True)
    risk_taker_username = serializers.CharField(source='risk_taker_id.username', read_only=True)
    risk_taker_name = serializers.CharField(source='risk_taker_id.name', read_only=True)

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
            'created_at',
            'start_date',
            'splitwise_entries',
            'risk_taker_flag',
            'risk_taker_commission'
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        if instance.risk_taker_flag and instance.risk_taker_commission > 0:
            commission_percentage = instance.risk_taker_commission
            total_commission_amount = 0

            for split_entry in representation.get('splitwise_entries', []):
                original_interest = split_entry.get('interest_amount', 0)
                commission_on_split = (original_interest * commission_percentage) / 100
                total_commission_amount += commission_on_split
                split_entry['interest_amount'] = original_interest - commission_on_split

            representation['risk_taker_commission_amount'] = total_commission_amount

        return representation