from rest_framework import serializers
from .models import CustomUser, Transactions

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


class PortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transactions
        fields = ['transaction_id', 'risk_taker_id', 'syndicators', 'total_principal_amount', 'total_interest', 'created_at', 'start_date']
