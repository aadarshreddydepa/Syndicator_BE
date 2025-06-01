from django.urls import path
from .views import PortfolioView, RegisterView, LoginView, SyndicateView, AddMutualFriendView

urlpatterns = [
    path('register/', RegisterView.as_view(), name="register"),
    path('login/', LoginView.as_view(), name="login"),
    path('portfolio/', PortfolioView.as_view(), name="portfolio"),
    path("syndicate/", SyndicateView.as_view(), name="syndicate"),
    path("create_friend/", AddMutualFriendView.as_view(), name="create_friend_list"),
]