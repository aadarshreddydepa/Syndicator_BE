from django.urls import path
from .views import CheckFriendRequestStatusView, PortfolioView, RegisterView, LoginView, SyndicateView, AddMutualFriendView, UpdateFriendRequestStatusView

urlpatterns = [
    path('register/', RegisterView.as_view(), name="register"),
    path('login/', LoginView.as_view(), name="login"),
    path('portfolio/', PortfolioView.as_view(), name="portfolio"),
    path("syndicate/", SyndicateView.as_view(), name="syndicate"),
    path("create_friend/", AddMutualFriendView.as_view(), name="create_friend_list"),
    path("check_friend_request_status/", CheckFriendRequestStatusView.as_view(), name="check_friend_request_status"),
    path("update_friend_request_status/", UpdateFriendRequestStatusView.as_view(), name="update_friend_request_status")
]