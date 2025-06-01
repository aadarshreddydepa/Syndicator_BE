from django.db.models.base import transaction
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import CustomUser, FriendList, FriendRequest, Transactions

from .serializers import RegisterSerializer, UserSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
# from rest_framework_simplejwt.authentication import JWTAuthentication
# from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
# from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import authenticate
from django.conf import settings

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
                # Get both users by username
                user = CustomUser.objects.get(username=username)
                mutual_friend = CustomUser.objects.get(username=mutual_friend_name)
                
                # Get or create the friend list for the user
                friend_list, created = FriendList.objects.get_or_create(user_id=user)
                
                # Check if mutual friend is already in the list
                if friend_list.mutual_friends.filter(username=mutual_friend_name).exists():
                    return Response({
                        "message": "User is already in the mutual friends list",
                        "friend_list_id": str(friend_list.friend_id),
                        "user": username,
                        "mutual_friend": mutual_friend_name
                    }, status=status.HTTP_200_OK)
                
                # Add mutual friend to the list
                friend_list.mutual_friends.add(mutual_friend)
                
                # Prepare response data
                response_data = {
                    "message": "Mutual friend added successfully",
                    "friend_list_id": str(friend_list.friend_id),
                    "user": {
                        "user_id": str(user.user_id),
                        "username": user.username,
                        "name": user.name
                    },
                    "added_friend": {
                        "user_id": str(mutual_friend.user_id),
                        "username": mutual_friend.username,
                        "name": mutual_friend.name
                    },
                    "friend_list_created": created
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
        status = request.data.get("status")
        try:
            user = CustomUser.objects.get(username=username)
            friend_request = FriendRequest.objects.get(user_id=user, request_id=request_id)
            friend_request.status = status
            friend_request.save()
            return Response({
                "message": "Friend request status updated successfully"
            }, status=status.HTTP_200_OK)
        except FriendRequest.DoesNotExist:
            return Response({
                "error": "Friend request not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                "error": f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)