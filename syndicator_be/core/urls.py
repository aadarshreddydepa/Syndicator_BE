from django.urls import path
from .views import PortfolioView, RegisterView, LoginView, SyndicateView

urlpatterns = [
    path('register/', RegisterView.as_view(), name="register"),
    path('login/', LoginView.as_view(), name="login"),
    path('portfolio/', PortfolioView.as_view(), name="portfolio"),
    path("syndicate/", SyndicateView.as_view(), name="syndicate"),
]