from datetime import date
from django.db.models.base import transaction
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import CustomUser, FriendList, FriendRequest, Splitwise, Transactions

from .serializers import PortfolioSerializer, RegisterSerializer, UserSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
# from rest_framework_simplejwt.authentication import JWTAuthentication
# from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
# from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import authenticate
from django.conf import settings
from django.db.models import Q
# Create your views here.

class RegisterView(APIView):

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User Registered."}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = []

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        user = authenticate(request, username=username, password=password)

        if user:
            if not user.is_active:
                return Response({"error": "Email is not verified"}, status=status.HTTP_403_FORBIDDEN)
            
            refresh = RefreshToken.for_user(user)
            
            # Set the refresh token as an HttpOnly cookie
            response = Response({
                "access": str(refresh.access_token),
                "user": UserSerializer(user).data
            })
            
            # Set the refresh token as HTTP-only cookie
            cookie_max_age = 3600 * 24 * 7  # 7 days
            response.set_cookie(
                key='refresh_token',
                value=str(refresh),
                max_age=cookie_max_age,
                httponly=True,
                samesite='Lax',  # Adjust based on your security requirements
                secure=settings.DEBUG is False,  # True in production
                path='/api/auth/'  # Path where the cookie is valid
            )
            
            return response
        return Response({"error": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)
    
    
class PortfolioView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            
            # Get all splitwise entries where user is a syndicate member
            splitwise_entries = Splitwise.objects.filter(syndicator_id=user)
            
            # Get transactions where user is risk taker
            risk_taker_transactions = Transactions.objects.filter(risk_taker_id=user)
            
            # Calculate total amounts
            total_principal = 0
            total_interest = 0
            
            # Add amounts from risk taker transactions
            for transaction in risk_taker_transactions:
                total_principal += transaction.total_principal_amount
                total_interest += transaction.total_principal_amount * transaction.total_interest / 100
            
            # Add amounts from splitwise entries (syndicate member transactions)
            for entry in splitwise_entries:
                total_principal += entry.principal_amount
                total_interest += entry.interest_amount
            
            return Response({
                "total_principal_amount": total_principal,
                "total_interest_amount": total_interest,
                "breakdown": {
                    "as_risk_taker": {
                        "principal": sum(t.total_principal_amount for t in risk_taker_transactions),
                        "interest": sum(t.total_principal_amount * t.total_interest / 100 for t in risk_taker_transactions)
                    },
                    "as_syndicate_member": {
                        "principal": sum(entry.principal_amount for entry in splitwise_entries),
                        "interest": sum(entry.interest_amount for entry in splitwise_entries)
                    }
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SyndicateView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get user directly from authenticated token
        user = request.user
        
        try:
            friend_list = FriendList.objects.get(user_id=user)
            
            # Get the actual friends data
            mutual_friends = friend_list.mutual_friends.all()
            friends_data = [
                {
                    "user_id": str(friend.user_id),
                    "username": friend.username,
                    "name": friend.name,
                    "email": friend.email
                }
                for friend in mutual_friends
            ]
            
            response_data = {
                "friend_list_id": str(friend_list.friend_id),
                "user": {
                    "user_id": str(user.user_id),
                    "username": user.username
                },
                "friends": friends_data,
                "created_at": friend_list.created_at
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except FriendList.DoesNotExist:
            return Response({
                "error": "Friend list not found for the authenticated user"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class AddMutualFriendView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Get username from authenticated user's token
        username = request.user.username
        mutual_friend_name = request.data.get("mutual_friend_name")
        
        # Validate required fields
        if not mutual_friend_name:
            return Response({
                "error": "mutual_friend_name is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user is trying to add themselves
        if username == mutual_friend_name:
            return Response({
                "error": "User cannot add themselves as a mutual friend"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Get the authenticated user (already verified by IsAuthenticated)
                user = request.user
                
                # Get the mutual friend by username
                try:
                    mutual_friend = CustomUser.objects.get(username=mutual_friend_name)
                except CustomUser.DoesNotExist:
                    return Response({
                        "error": f"Mutual friend with username '{mutual_friend_name}' not found"
                    }, status=status.HTTP_404_NOT_FOUND)
                
                # Check if there's an accepted friend request between these users
                # We need to check both directions: user->mutual_friend and mutual_friend->user
                friend_request_exists = FriendRequest.objects.filter(
                    Q(user_id=user, requested_id=mutual_friend, status='accepted') |
                    Q(user_id=mutual_friend, requested_id=user, status='accepted')
                ).exists()
                
                if friend_request_exists:
                    return Response({
                        "message": "These users are already friends through an accepted friend request."
                    }, status=status.HTTP_200_OK)
                
                if not friend_request_exists:
                    friend_request, created = FriendRequest.objects.get_or_create(
                        user_id=user, 
                        requested_id=mutual_friend
                    )
                
                # Prepare response data
                response_data = {
                    "message": "Friend request created successfully",
                    "friend_request_id": str(friend_request.request_id),
                    "user": username,
                    "mutual_friend": mutual_friend_name,
                    "status": friend_request.status,
                    "created": created
                }
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CheckFriendRequestStatusView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Check if username parameter is provided (not allowed with JWT auth)
        username_param = request.query_params.get("username")
        if username_param:
            return Response({
                "error": "Username parameter not allowed. This endpoint uses JWT authentication to identify the user automatically."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the authenticated user from JWT token
        authenticated_user = request.user
        
        try:
            # Find ALL friend requests involving the authenticated user (sender OR receiver)
            friend_requests = FriendRequest.objects.filter(
                Q(user_id=authenticated_user) | Q(requested_id=authenticated_user)
            ).order_by('-created_at')  # Order by most recent first
            
            if not friend_requests.exists():
                return Response({
                    "message": "No friend requests found",
                    "user": authenticated_user.username,
                    "user_id": str(authenticated_user.user_id),
                    "total_requests": 0,
                    "requests": []
                }, status=status.HTTP_200_OK)
            
            # Build list of all requests with details
            requests_data = []
            sent_requests = []
            received_requests = []
            
            for friend_request in friend_requests:
                request_info = {
                    "request_id": str(friend_request.request_id),
                    "requested_id": str(friend_request.requested_id.user_id),
                    "requested_username": friend_request.requested_id.username,
                    "requested_name": friend_request.requested_id.name or friend_request.requested_id.username,
                    "user_id": str(friend_request.user_id.user_id),
                    "sender_username": friend_request.user_id.username,
                    "sender_name": friend_request.user_id.name or friend_request.user_id.username,
                    "status": friend_request.status,
                    "created_at": friend_request.created_at.isoformat(),
                }
                
                # Determine if this request was sent by or received by the authenticated user
                if friend_request.user_id == authenticated_user:
                    request_info["request_type"] = "sent"
                    request_info["other_user"] = {
                        "user_id": str(friend_request.requested_id.user_id),
                        "username": friend_request.requested_id.username,
                        "name": friend_request.requested_id.name or friend_request.requested_id.username
                    }
                    sent_requests.append(request_info)
                else:
                    request_info["request_type"] = "received"
                    request_info["other_user"] = {
                        "user_id": str(friend_request.user_id.user_id),
                        "username": friend_request.user_id.username,
                        "name": friend_request.user_id.name or friend_request.user_id.username
                    }
                    received_requests.append(request_info)
                
                requests_data.append(request_info)
            
            # Count requests by status
            status_counts = {
                "pending": 0,
                "accepted": 0,
                "rejected": 0,
                "canceled": 0
            }
            
            for req in requests_data:
                status_counts[req["status"]] += 1
            
            return Response({
                "message": f"Found {len(requests_data)} friend requests for {authenticated_user.username}",
                "user": authenticated_user.username,
                "user_id": str(authenticated_user.user_id),
                "total_requests": len(requests_data),
                "sent_requests_count": len(sent_requests),
                "received_requests_count": len(received_requests),
                "status_summary": status_counts,
                "requests": {
                    "all": requests_data,
                    "sent": sent_requests,
                    "received": received_requests
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
class UpdateFriendRequestStatusView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        request_id = request.data.get("request_id")
        new_status = request.data.get("status")
        
        # Get the authenticated user from JWT token
        authenticated_user = request.user
        
        # Validate required fields
        if not request_id or not new_status:
            return Response({
                "error": "request_id and status are required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status value
        valid_statuses = ['pending', 'accepted', 'rejected', 'canceled']
        if new_status not in valid_statuses:
            return Response({
                "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Find the friend request by request_id
                friend_request = FriendRequest.objects.get(request_id=request_id)
                
                # Authorization: Check if the authenticated user is involved in this friend request
                requester = friend_request.user_id  # The user who sent the request
                requested = friend_request.requested_id  # The user who received the request
                
                # Verify the authenticated user is either the requester or the requested user
                if authenticated_user.user_id not in [requester.user_id, requested.user_id]:
                    return Response({
                        "error": "You are not authorized to update this friend request"
                    }, status=status.HTTP_403_FORBIDDEN)
                
                # Business logic: Only recipient can accept/reject, only sender can cancel
                if new_status in ['accepted', 'rejected']:
                    if authenticated_user.user_id != requested.user_id:
                        return Response({
                            "error": "Only the recipient can accept or reject a friend request"
                        }, status=status.HTTP_403_FORBIDDEN)
                elif new_status == 'canceled':
                    if authenticated_user.user_id != requester.user_id:
                        return Response({
                            "error": "Only the sender can cancel a friend request"
                        }, status=status.HTTP_403_FORBIDDEN)
                
                # Update the friend request status
                old_status = friend_request.status
                friend_request.status = new_status
                friend_request.save()
                
                response_data = {
                    "message": "Friend request status updated successfully",
                    "request_id": str(friend_request.request_id),
                    "old_status": old_status,
                    "new_status": new_status,
                    "authenticated_user": authenticated_user.username,
                    "requester": requester.username,
                    "recipient": requested.username
                }
                
                # If status is changed to 'accepted', add both users to each other's friend lists
                if new_status == 'accepted':
                    # Get or create friend list for the requester
                    requester_friend_list, created1 = FriendList.objects.get_or_create(user_id=requester)
                    
                    # Get or create friend list for the requested user
                    requested_friend_list, created2 = FriendList.objects.get_or_create(user_id=requested)
                    
                    # Add each user to the other's mutual friends list (if not already added)
                    if not requester_friend_list.mutual_friends.filter(user_id=requested.user_id).exists():
                        requester_friend_list.mutual_friends.add(requested)
                    
                    if not requested_friend_list.mutual_friends.filter(user_id=requester.user_id).exists():
                        requested_friend_list.mutual_friends.add(requester)
                    
                    response_data.update({
                        "friends_added": True,
                        "requester_details": {
                            "user_id": str(requester.user_id),
                            "username": requester.username,
                            "name": requester.name
                        },
                        "recipient_details": {
                            "user_id": str(requested.user_id),
                            "username": requested.username,
                            "name": requested.name
                        },
                        "friend_lists_created": {
                            "requester_list_created": created1,
                            "requested_list_created": created2
                        }
                    })
                
                # If status is changed to 'rejected' or 'canceled', remove from friend lists if they exist
                elif new_status in ['rejected', 'canceled']:
                    try:
                        # Remove from requester's friend list
                        requester_friend_list = FriendList.objects.get(user_id=requester)
                        if requester_friend_list.mutual_friends.filter(user_id=requested.user_id).exists():
                            requester_friend_list.mutual_friends.remove(requested)
                    except FriendList.DoesNotExist:
                        pass
                    
                    try:
                        # Remove from requested user's friend list
                        requested_friend_list = FriendList.objects.get(user_id=requested)
                        if requested_friend_list.mutual_friends.filter(user_id=requester.user_id).exists():
                            requested_friend_list.mutual_friends.remove(requester)
                    except FriendList.DoesNotExist:
                        pass
                    
                    response_data.update({
                        "friends_removed": True
                    })
                
                return Response(response_data, status=status.HTTP_200_OK)
                
        except FriendRequest.DoesNotExist:
            return Response({
                "error": "Friend request not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# Updated view using your existing PortfolioSerializer
class AllTransactionView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get all transactions where user is either risk taker or syndicate member
            # First get transactions where user is risk taker
            risk_taker_transactions = Transactions.objects.filter(risk_taker_id=request.user)
            
            # Then get transactions where user is syndicate member
            splitwise_entries = Splitwise.objects.filter(syndicator_id=request.user)
            syndicate_transactions = Transactions.objects.filter(
                transaction_id__in=splitwise_entries.values('transaction_id')
            )
            
            # Combine both sets of transactions
            all_transactions = list(risk_taker_transactions) + list(syndicate_transactions)
            
            # Remove duplicates (same transaction appearing in both lists)
            unique_transactions = []
            seen_transaction_ids = set()
            
            for transaction in all_transactions:
                if transaction.transaction_id not in seen_transaction_ids:
                    unique_transactions.append(transaction)
                    seen_transaction_ids.add(transaction.transaction_id)
            
            # Serialize the data
            serializer = PortfolioSerializer(unique_transactions, many=True)
            
            # Count transactions where user is risk taker vs syndicate member
            risk_taker_count = len(risk_taker_transactions)
            syndicate_count = len(syndicate_transactions)
            
            response_data = {
                "message": f"Transactions retrieved successfully for {request.user.username}",
                "user": {
                    "user_id": str(request.user.user_id),
                    "username": request.user.username,
                    "name": request.user.name or request.user.username
                },
                "transaction_counts": {
                    "total": len(unique_transactions),
                    "as_risk_taker": risk_taker_count,
                    "as_syndicate_member": syndicate_count
                },
                "transactions": serializer.data
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CreateTransactionView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Get user directly from authenticated token
        risk_taker = request.user
        
        # Extract data from request
        total_principal_amount = request.data.get("total_principal_amount")
        total_interest_amount = request.data.get("total_interest_amount")
        syndicate_details = request.data.get("syndicate_details", {})
        
        # Validation
        if total_principal_amount is None or total_interest_amount is None:
            return Response({
                "error": "total_principal_amount and total_interest_amount are required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                syndicators_list = []
                splitwise_entries = []
                
                # Check if syndicate details are provided
                if syndicate_details:
                    # Validate all syndicate usernames exist
                    syndicate_usernames = list(syndicate_details.keys())
                    existing_users = CustomUser.objects.filter(username__in=syndicate_usernames)
                    existing_usernames = set(user.username for user in existing_users)
                    
                    missing_usernames = set(syndicate_usernames) - existing_usernames
                    if missing_usernames:
                        return Response({
                            "error": f"Users not found: {', '.join(missing_usernames)}"
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Check if all syndicators have accepted friend status with risk_taker
                    # (except for the risk_taker themselves)
                    non_friends = []
                    for user in existing_users:
                        # Skip friend validation if syndicator is the risk_taker themselves
                        if user.username == risk_taker.username:
                            continue
                            
                        # Check if there's an accepted friend request between risk_taker and syndicate member
                        friend_request_exists = FriendRequest.objects.filter(
                            Q(user_id=risk_taker, requested_id=user, status='accepted') |
                            Q(user_id=user, requested_id=risk_taker, status='accepted')
                        ).exists()
                        
                        if not friend_request_exists:
                            non_friends.append(user.username)
                    
                    if non_friends:
                        return Response({
                            "error": f"Syndicator(s) {', '.join(non_friends)} are not accepted friends. Please ensure friend requests are accepted before creating transactions."
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Create syndicators list with user IDs
                    for user in existing_users:
                        syndicators_list.append({
                            'user_id': str(user.user_id),
                            'username': user.username
                        })
                    
                    # Validate that total amounts match splitwise details
                    total_splitwise_principal = 0
                    
                    for username_key, details in syndicate_details.items():
                        principal_amount = details.get('principal_amount', 0)
                        interest_amount = details.get('interest', 0)
                        total_splitwise_principal += float(principal_amount)
                        
                        # Check if each individual interest amount equals total_interest_amount
                        if abs(float(total_interest_amount) - float(interest_amount)) > 0.01:
                            return Response({
                                "error": f"Interest amount for {username_key} ({interest_amount}) must equal total_interest_amount ({total_interest_amount}). All syndicators must have the same interest amount."
                            }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Check if total principal matches sum of splitwise principal amounts
                    if abs(float(total_principal_amount) - total_splitwise_principal) > 0.01:
                        return Response({
                            "error": f"Total principal amount ({total_principal_amount}) does not match sum of splitwise principal amounts ({total_splitwise_principal})"
                        }, status=status.HTTP_400_BAD_REQUEST)
                
                # Create the transaction
                new_transaction = Transactions.objects.create(
                    risk_taker_id=risk_taker,
                    syndicators=syndicators_list,
                    total_principal_amount=float(total_principal_amount),
                    total_interest=float(total_interest_amount),
                    start_date=date.today()
                )
                
                # Create Splitwise entries only if there are syndicators
                if syndicate_details:
                    # Create a mapping of username to user object for easier lookup
                    username_to_user = {user.username: user for user in existing_users}
                    
                    for username_key, details in syndicate_details.items():
                        principal_amount = details.get('principal_amount', 0)  # Fixed typo
                        interest_amount = details.get('interest', 0)
                        
                        # Get the user object for this username
                        syndicator_user = username_to_user[username_key]
                        
                        # Create splitwise entry with user association
                        splitwise_entry = Splitwise.objects.create(
                            transaction_id=new_transaction,
                            syndicator_id=syndicator_user,  # NEW: Associate with specific user
                            principal_amount=float(principal_amount),
                            interest_amount=float(interest_amount)
                        )
                        splitwise_entries.append({
                            'splitwise_id': str(splitwise_entry.splitwise_id),
                            'syndicator_username': syndicator_user.username,
                            'syndicator_user_id': str(syndicator_user.user_id),
                            'principal_amount': splitwise_entry.principal_amount,
                            'interest_amount': splitwise_entry.interest_amount
                        })
                
                # Prepare response
                response_data = {
                    "message": "Transaction created successfully",
                    "transaction_id": str(new_transaction.transaction_id),
                    "risk_taker": {
                        "user_id": str(risk_taker.user_id),
                        "username": risk_taker.username
                    },
                    "total_principal_amount": new_transaction.total_principal_amount,
                    "total_interest": new_transaction.total_interest,
                    "transaction_type": "syndicated" if syndicate_details else "solo"
                }
                
                if syndicate_details:
                    response_data["splitwise_entries_count"] = len(splitwise_entries)
                    response_data["splitwise_entries"] = splitwise_entries
                else:
                    response_data["note"] = "Solo transaction - risk taker is solely responsible"
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
        except ValueError as e:
            return Response({
                "error": f"Invalid data format: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class UserSplitwiseView(APIView):
    """Get all splitwise entries for the authenticated user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            
            # Get all splitwise entries where the user is a syndicator
            splitwise_entries = Splitwise.objects.filter(syndicator_id=user).select_related(
                'transaction_id', 
                'transaction_id__risk_taker_id'
            ).order_by('-created_at')
            
            if not splitwise_entries.exists():
                return Response({
                    "message": f"No splitwise entries found for {user.username}",
                    "user": {
                        "user_id": str(user.user_id),
                        "username": user.username
                    },
                    "splitwise_count": 0,
                    "splitwise_entries": []
                }, status=status.HTTP_200_OK)
            
            # Serialize the data
            serialized_entries = []
            total_principal_committed = 0
            total_interest_earning = 0
            
            for entry in splitwise_entries:
                total_principal_committed += entry.principal_amount
                total_interest_earning += entry.interest_amount
                
                serialized_entries.append({
                    "splitwise_id": str(entry.splitwise_id),
                    "transaction_id": str(entry.transaction_id.transaction_id),
                    "risk_taker": {
                        "user_id": str(entry.transaction_id.risk_taker_id.user_id),
                        "username": entry.transaction_id.risk_taker_id.username,
                        "name": entry.transaction_id.risk_taker_id.name
                    },
                    "principal_amount": entry.principal_amount,
                    "interest_amount": entry.interest_amount,
                    "transaction_start_date": entry.transaction_id.start_date.isoformat(),
                    "splitwise_created_at": entry.created_at.isoformat()
                })
            
            response_data = {
                "message": f"Splitwise entries retrieved for {user.username}",
                "user": {
                    "user_id": str(user.user_id),
                    "username": user.username,
                    "name": user.name
                },
                "summary": {
                    "total_principal_committed": total_principal_committed,
                    "total_interest_earning": total_interest_earning,
                    "splitwise_count": len(serialized_entries)
                },
                "splitwise_entries": serialized_entries
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TransactionSplitwiseView(APIView):
    """Get all splitwise entries for a specific transaction"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, transaction_id):
        try:
            user = request.user
            
            # Verify the transaction exists and the user has access to it
            # (either as risk_taker or as a syndicator)
            try:
                transaction = Transactions.objects.get(transaction_id=transaction_id)
            except Transactions.DoesNotExist:
                return Response({
                    "error": "Transaction not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if user has permission to view this transaction
            user_has_access = False
            
            # Check if user is the risk taker
            if transaction.risk_taker_id == user:
                user_has_access = True
            else:
                # Check if user is one of the syndicators
                user_splitwise = Splitwise.objects.filter(
                    transaction_id=transaction,
                    syndicator_id=user
                ).exists()
                if user_splitwise:
                    user_has_access = True
            
            if not user_has_access:
                return Response({
                    "error": "You don't have permission to view this transaction"
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get all splitwise entries for this transaction
            splitwise_entries = Splitwise.objects.filter(
                transaction_id=transaction
            ).select_related('syndicator_id').order_by('created_at')
            
            # Serialize the data
            serialized_entries = []
            for entry in splitwise_entries:
                serialized_entries.append({
                    "splitwise_id": str(entry.splitwise_id),
                    "syndicator": {
                        "user_id": str(entry.syndicator_id.user_id),
                        "username": entry.syndicator_id.username,
                        "name": entry.syndicator_id.name,
                        "email": entry.syndicator_id.email
                    },
                    "principal_amount": entry.principal_amount,
                    "interest_amount": entry.interest_amount,
                    "created_at": entry.created_at.isoformat()
                })
            
            response_data = {
                "message": "Transaction splitwise details retrieved successfully",
                "transaction": {
                    "transaction_id": str(transaction.transaction_id),
                    "risk_taker": {
                        "user_id": str(transaction.risk_taker_id.user_id),
                        "username": transaction.risk_taker_id.username,
                        "name": transaction.risk_taker_id.name
                    },
                    "total_principal_amount": transaction.total_principal_amount,
                    "total_interest": transaction.total_interest,
                    "start_date": transaction.start_date.isoformat(),
                    "created_at": transaction.created_at.isoformat()
                },
                "splitwise_summary": {
                    "total_splits": len(serialized_entries),
                    "total_principal_split": sum(entry.principal_amount for entry in splitwise_entries),
                    "total_interest_split": sum(entry.interest_amount for entry in splitwise_entries)
                },
                "splitwise_entries": serialized_entries
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)