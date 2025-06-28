from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from .models import CustomUser, Transactions, Splitwise, FriendRequest
from datetime import date

class TransactionBusinessLogicTests(APITestCase):
    def setUp(self):
        # Create test users
        self.risk_taker = CustomUser.objects.create_user(
            username='risktaker',
            email='risktaker@test.com',
            password='testpass123'
        )
        
        self.syndicator1 = CustomUser.objects.create_user(
            username='syndicator1',
            email='syndicator1@test.com',
            password='testpass123'
        )
        
        self.syndicator2 = CustomUser.objects.create_user(
            username='syndicator2',
            email='syndicator2@test.com',
            password='testpass123'
        )
        
        # Create friend relationships
        FriendRequest.objects.create(
            user_id=self.risk_taker,
            requested_id=self.syndicator1,
            status='accepted'
        )
        
        FriendRequest.objects.create(
            user_id=self.risk_taker,
            requested_id=self.syndicator2,
            status='accepted'
        )
        
        # Authenticate as risk taker
        self.client.force_authenticate(user=self.risk_taker)
    
    def test_case_1_solo_transaction_auto_create_splitwise(self):
        """Test Case 1: Solo transaction - auto-create splitwise entry for risk taker"""
        data = {
            "total_principal_amount": 1000,
            "total_interest_amount": 200,  # 20% interest
            "risk_taker_flag": False,
            "risk_taker_commission": 0
        }
        
        response = self.client.post(reverse('create_transaction'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify transaction was created
        transaction = Transactions.objects.get(risk_taker_id=self.risk_taker)
        self.assertEqual(transaction.total_principal_amount, 1000)
        self.assertEqual(transaction.total_interest, 200)
        self.assertFalse(transaction.risk_taker_flag)
        
        # Verify single splitwise entry was auto-created for risk taker
        splitwise_entries = Splitwise.objects.filter(transaction_id=transaction)
        self.assertEqual(splitwise_entries.count(), 1)
        
        splitwise_entry = splitwise_entries.first()
        self.assertEqual(splitwise_entry.syndicator_id, self.risk_taker)
        self.assertEqual(splitwise_entry.principal_amount, 1000)
        self.assertEqual(splitwise_entry.interest_amount, 200)
        self.assertEqual(splitwise_entry.get_interest_after_commission(), 200)  # No commission
        self.assertEqual(splitwise_entry.get_commission_deducted(), 0)
    
    def test_case_2_syndicated_transaction_no_commission(self):
        """Test Case 2: Syndicated transaction with multiple syndicators, no commission"""
        data = {
            "total_principal_amount": 1000,
            "total_interest_amount": 200,  # 20% interest
            "risk_taker_flag": False,
            "risk_taker_commission": 0,
            "syndicate_details": {
                "syndicator1": {
                    "principal_amount": 600,
                    "interest": 200
                },
                "syndicator2": {
                    "principal_amount": 400,
                    "interest": 200
                }
            }
        }
        
        response = self.client.post(reverse('create_transaction'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify transaction and splitwise entries
        transaction = Transactions.objects.get(risk_taker_id=self.risk_taker)
        splitwise_entries = Splitwise.objects.filter(transaction_id=transaction)
        self.assertEqual(splitwise_entries.count(), 2)
        
        # Check each syndicator's entry
        for entry in splitwise_entries:
            self.assertEqual(entry.interest_amount, 200)  # Original interest
            self.assertEqual(entry.get_interest_after_commission(), 200)  # No commission
            self.assertEqual(entry.get_commission_deducted(), 0)
    
    def test_case_3_commission_only_risk_taker_not_in_splitwise(self):
        """Test Case 3: Commission transaction where risk taker is NOT in splitwise"""
        data = {
            "total_principal_amount": 1000,
            "total_interest_amount": 200,  # 20% interest
            "risk_taker_flag": True,
            "risk_taker_commission": 50,  # 50% commission
            "syndicate_details": {
                "syndicator1": {
                    "principal_amount": 600,
                    "interest": 200
                },
                "syndicator2": {
                    "principal_amount": 400,
                    "interest": 200
                }
            }
        }
        
        response = self.client.post(reverse('create_transaction'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify transaction
        transaction = Transactions.objects.get(risk_taker_id=self.risk_taker)
        self.assertTrue(transaction.risk_taker_flag)
        self.assertEqual(transaction.risk_taker_commission, 50)
        
        # Verify splitwise entries - each syndicator pays 50% of their interest
        splitwise_entries = Splitwise.objects.filter(transaction_id=transaction)
        self.assertEqual(splitwise_entries.count(), 2)
        
        for entry in splitwise_entries:
            self.assertEqual(entry.interest_amount, 200)  # Original interest
            self.assertEqual(entry.get_interest_after_commission(), 100)  # 200 - 50% = 100
            self.assertEqual(entry.get_commission_deducted(), 100)  # 50% of 200 = 100
    
    def test_case_4_commission_with_risk_taker_in_splitwise(self):
        """Test Case 4: Commission transaction where risk taker IS in splitwise (shouldn't pay commission to themselves)"""
        data = {
            "total_principal_amount": 1000,
            "total_interest_amount": 200,  # 20% interest
            "risk_taker_flag": True,
            "risk_taker_commission": 50,  # 50% commission
            "syndicate_details": {
                "risktaker": {  # Risk taker is also a syndicator
                    "principal_amount": 400,
                    "interest": 200
                },
                "syndicator1": {
                    "principal_amount": 600,
                    "interest": 200
                }
            }
        }
        
        response = self.client.post(reverse('create_transaction'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify transaction
        transaction = Transactions.objects.get(risk_taker_id=self.risk_taker)
        self.assertTrue(transaction.risk_taker_flag)
        self.assertEqual(transaction.risk_taker_commission, 50)
        
        # Verify splitwise entries
        splitwise_entries = Splitwise.objects.filter(transaction_id=transaction)
        self.assertEqual(splitwise_entries.count(), 2)
        
        # Find risk taker's entry
        risk_taker_entry = splitwise_entries.get(syndicator_id=self.risk_taker)
        self.assertEqual(risk_taker_entry.interest_amount, 200)  # Original interest
        self.assertEqual(risk_taker_entry.get_interest_after_commission(), 200)  # No commission (to themselves)
        self.assertEqual(risk_taker_entry.get_commission_deducted(), 0)
        
        # Find other syndicator's entry
        other_entry = splitwise_entries.exclude(syndicator_id=self.risk_taker).first()
        self.assertEqual(other_entry.interest_amount, 200)  # Original interest
        self.assertEqual(other_entry.get_interest_after_commission(), 100)  # 200 - 50% = 100
        self.assertEqual(other_entry.get_commission_deducted(), 100)  # 50% of 200 = 100
    
    def test_commission_validation_exceeds_available_interest(self):
        """Test that commission cannot exceed 100%"""
        data = {
            "total_principal_amount": 1000,
            "total_interest_amount": 200,
            "risk_taker_flag": True,
            "risk_taker_commission": 150,  # Exceeds 100%
            "syndicate_details": {
                "syndicator1": {
                    "principal_amount": 1000,
                    "interest": 200
                }
            }
        }
        
        response = self.client.post(reverse('create_transaction'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("risk_taker_commission must be between 0 and 100", response.data['error'])
    
    def test_commission_validation_with_risk_taker_in_splitwise(self):
        """Test commission validation when risk taker is in splitwise (should exclude them from commission calculation)"""
        data = {
            "total_principal_amount": 1000,
            "total_interest_amount": 200,
            "risk_taker_flag": True,
            "risk_taker_commission": 80,  # Should be valid since it's a percentage
            "syndicate_details": {
                "risktaker": {
                    "principal_amount": 500,
                    "interest": 200
                },
                "syndicator1": {
                    "principal_amount": 500,
                    "interest": 200
                }
            }
        }
        
        response = self.client.post(reverse('create_transaction'), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)  # Should succeed since commission is a percentage

class SplitwiseModelTests(TestCase):
    def setUp(self):
        self.risk_taker = CustomUser.objects.create_user(
            username='risktaker',
            email='risktaker@test.com',
            password='testpass123'
        )
        
        self.syndicator = CustomUser.objects.create_user(
            username='syndicator',
            email='syndicator@test.com',
            password='testpass123'
        )
    
    def test_get_interest_after_commission_no_commission(self):
        """Test interest calculation when no commission is applied"""
        transaction = Transactions.objects.create(
            risk_taker_id=self.risk_taker,
            total_principal_amount=1000,
            total_interest=200,
            risk_taker_flag=False,
            risk_taker_commission=0,
            start_date=date.today()
        )
        
        splitwise_entry = Splitwise.objects.create(
            transaction_id=transaction,
            syndicator_id=self.syndicator,
            principal_amount=1000,
            interest_amount=200
        )
        
        self.assertEqual(splitwise_entry.get_interest_after_commission(), 200)
        self.assertEqual(splitwise_entry.get_commission_deducted(), 0)
    
    def test_get_interest_after_commission_with_commission(self):
        """Test interest calculation when commission is applied"""
        transaction = Transactions.objects.create(
            risk_taker_id=self.risk_taker,
            total_principal_amount=1000,
            total_interest=200,
            risk_taker_flag=True,
            risk_taker_commission=50,  # 50% commission
            start_date=date.today()
        )
        
        splitwise_entry = Splitwise.objects.create(
            transaction_id=transaction,
            syndicator_id=self.syndicator,
            principal_amount=1000,
            interest_amount=200
        )
        
        self.assertEqual(splitwise_entry.get_interest_after_commission(), 100)  # 200 - 50% = 100
        self.assertEqual(splitwise_entry.get_commission_deducted(), 100)  # 50% of 200 = 100
    
    def test_risk_taker_does_not_pay_commission_to_themselves(self):
        """Test that risk taker doesn't pay commission to themselves"""
        transaction = Transactions.objects.create(
            risk_taker_id=self.risk_taker,
            total_principal_amount=1000,
            total_interest=200,
            risk_taker_flag=True,
            risk_taker_commission=50,  # 50% commission
            start_date=date.today()
        )
        
        # Create entry for risk taker
        risk_taker_entry = Splitwise.objects.create(
            transaction_id=transaction,
            syndicator_id=self.risk_taker,
            principal_amount=500,
            interest_amount=200
        )
        
        # Create entry for other syndicator
        syndicator_entry = Splitwise.objects.create(
            transaction_id=transaction,
            syndicator_id=self.syndicator,
            principal_amount=500,
            interest_amount=200
        )
        
        # Risk taker should not pay commission to themselves
        self.assertEqual(risk_taker_entry.get_interest_after_commission(), 200)
        self.assertEqual(risk_taker_entry.get_commission_deducted(), 0)
        
        # Other syndicator should pay 50% commission
        self.assertEqual(syndicator_entry.get_interest_after_commission(), 100)  # 200 - 50% = 100
        self.assertEqual(syndicator_entry.get_commission_deducted(), 100)  # 50% of 200 = 100
