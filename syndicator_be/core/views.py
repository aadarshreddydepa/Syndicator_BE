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
        username= request.data.get("username")
        try:
            user = CustomUser.objects.get(username=username)
            transactions = Transactions.objects.filter(risk_taker_id=user)
            t_principal_amount = 0
            t_interest_amount = 0
            for transaction in transactions:
                t_principal_amount += transaction.total_principal_amount
                t_interest_amount += transaction.total_principal_amount * transaction.total_interest / 100
            return Response({"total_principal_amount": t_principal_amount, "total_interest_amount": t_interest_amount}, status=status.HTTP_201_CREATED)
        except CustomUser.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        except Transactions.DoesNotExist:
            return Response({"error": "Transactions not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
class SyndicateView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        username = request.query_params.get("username")  # Changed from request.data
        
        if not username:
            return Response({"error": "Username parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(username=username)
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
            
            return Response(response_data, status=status.HTTP_200_OK)  # Changed status code
            
        except CustomUser.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        except FriendList.DoesNotExist:
            return Response({"error": "Friend list not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AddMutualFriendView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        username = request.data.get("username")
        mutual_friend_name = request.data.get("mutual_friend_name")
        
        # Validate required fields
        if not username or not mutual_friend_name:
            return Response({
                "error": "Both username and mutual_friend_name are required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user is trying to add themselves
        if username == mutual_friend_name:
            return Response({
                "error": "User cannot add themselves as a mutual friend"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                user = CustomUser.objects.get(username=username)
                mutual_friend = CustomUser.objects.get(username=mutual_friend_name)
                
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
                    friend_request, created = FriendRequest.objects.get_or_create(user_id=user, requested_id=mutual_friend)
                # Check if mutual friend is already in the list
                # if friend_list.mutual_friends.filter(username=mutual_friend_name).exists():
                #     return Response({
                #         "message": "User is already in the mutual friends list",
                #         "friend_list_id": str(friend_list.friend_id),
                #         "user": username,
                #         "mutual_friend": mutual_friend_name
                #     }, status=status.HTTP_200_OK)
                
                # Add mutual friend to the list
                # friend_list.mutual_friends.add(mutual_friend)
                
                # Prepare response data
                response_data = {
                    "message": "Mutual friend added successfully",
                    "friend_request_id": str(friend_request.request_id),
                    "user": username,
                    "mutual_friend": mutual_friend_name,
                    "status": friend_request.status,
        
                }
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
        except CustomUser.DoesNotExist:
            # Check which user doesn't exist
            try:
                CustomUser.objects.get(username=username)
                # If we reach here, the main user exists, so mutual friend doesn't exist
                return Response({
                    "error": f"Mutual friend with username '{mutual_friend_name}' not found"
                }, status=status.HTTP_404_NOT_FOUND)
            except CustomUser.DoesNotExist:
                return Response({
                    "error": f"User with username '{username}' not found"
                }, status=status.HTTP_404_NOT_FOUND)
                
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CheckFriendRequestStatusView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        username = request.query_params.get("username")
        try:
            user = CustomUser.objects.get(username=username)
            friend_request = FriendRequest.objects.get(user_id=user)
            return Response({
                "message": "User is in the mutual friends list",
                "request_id": str(friend_request.request_id),
                "requested_id": str(friend_request.requested_id),
                "user_id": str(friend_request.user_id),
                "status": friend_request.status,
                "user": username
            }, status=status.HTTP_200_OK)
        except FriendRequest.DoesNotExist:
            return Response({
                "error": "Friend request not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            

class UpdateFriendRequestStatusView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        username = request.data.get("username")
        request_id = request.data.get("request_id")
        new_status = request.data.get("status")
        
        # Validate required fields
        if not username or not request_id or not new_status:
            return Response({
                "error": "username, request_id, and status are required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status value
        valid_statuses = ['pending', 'accepted', 'rejected', 'canceled']
        if new_status not in valid_statuses:
            return Response({
                "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                user = CustomUser.objects.get(username=username)
                friend_request = FriendRequest.objects.get(user_id=user, request_id=request_id)
                
                # Update the friend request status
                old_status = friend_request.status
                friend_request.status = new_status
                friend_request.save()
                
                response_data = {
                    "message": "Friend request status updated successfully",
                    "request_id": str(friend_request.request_id),
                    "old_status": old_status,
                    "new_status": new_status,
                    "user": username
                }
                
                # If status is changed to 'accepted', add both users to each other's friend lists
                if new_status == 'accepted':
                    # Get the users involved in the friend request
                    requester = friend_request.user_id  # The user who sent the request
                    requested = friend_request.requested_id  # The user who received the request
                    
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
                        "requester": {
                            "user_id": str(requester.user_id),
                            "username": requester.username,
                            "name": requester.name
                        },
                        "requested": {
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
                    requester = friend_request.user_id
                    requested = friend_request.requested_id
                    
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
                
        except CustomUser.DoesNotExist:
            return Response({
                "error": f"User with username '{username}' not found"
            }, status=status.HTTP_404_NOT_FOUND)
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
        username = request.query_params.get("username")
        
        if not username:
            return Response({
                "error": "Username parameter is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(username=username)
            transactions = Transactions.objects.filter(risk_taker_id=user)
            
            # Use your existing PortfolioSerializer
            serializer = PortfolioSerializer(transactions, many=True)
            
            return Response({
                "transactions": serializer.data
            }, status=status.HTTP_200_OK)
            
        except CustomUser.DoesNotExist:
            return Response({
                "error": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CreateTransactionView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Extract data from request
        username = request.data.get("username")
        total_principal_amount = request.data.get("total_prinicpal_amount")  # Note: keeping your typo for consistency
        total_interest_amount = request.data.get("total_interest_amount")
        syndicate_details = request.data.get("syndicate_details", {})
        
        # Validation
        if not username:
            return Response({
                "error": "Username is required"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if total_principal_amount is None or total_interest_amount is None:
            return Response({
                "error": "total_prinicpal_amount and total_interest_amount are required"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        if not syndicate_details:
            return Response({
                "error": "syndicate_details is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Get the risk taker user
                risk_taker = CustomUser.objects.get(username=username)
                
                # Validate all syndicate usernames exist
                syndicate_usernames = list(syndicate_details.keys())
                existing_users = CustomUser.objects.filter(username__in=syndicate_usernames)
                existing_usernames = set(user.username for user in existing_users)
                
                missing_usernames = set(syndicate_usernames) - existing_usernames
                if missing_usernames:
                    return Response({
                        "error": f"Users not found: {', '.join(missing_usernames)}"
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Create syndicators list with user IDs
                syndicators_list = []
                for user in existing_users:
                    syndicators_list.append({
                        'user_id': str(user.user_id),
                        'username': user.username
                    })
                
                # Create the transaction
                new_transaction = Transactions.objects.create(
                    risk_taker_id=risk_taker,
                    syndicators=syndicators_list,
                    total_prinicipal_amount=float(total_principal_amount),
                    total_interest=float(total_interest_amount),
                    start_date=date.today()  # You can modify this as needed
                )
                
                # Create Splitwise entries for each syndicate member
                splitwise_entries = []
                for username_key, details in syndicate_details.items():
                    principal_amount = details.get('prinicipal_amount', 0)  # Note: keeping your typo
                    interest_amount = details.get('interest', 0)
                    
                    splitwise_entry = Splitwise.objects.create(
                        transaction_id=new_transaction,
                        principal_amount=float(principal_amount),
                        interest_amount=float(interest_amount)
                    )
                    splitwise_entries.append(splitwise_entry)
                
                # Return success response
                return Response({
                    "message": "Transaction created successfully",
                    "transaction_id": str(new_transaction.transaction_id),
                    "total_principal_amount": new_transaction.total_prinicipal_amount,
                    "total_interest": new_transaction.total_interest,
                    "splitwise_entries_count": len(splitwise_entries)
                }, status=status.HTTP_201_CREATED)
                
        except CustomUser.DoesNotExist:
            return Response({
                "error": f"User with username '{username}' not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({
                "error": f"Invalid data format: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)