from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserViewSet, UserRegistrationView, FinovaIDLoginView, VerifyEmailOTPView

router = DefaultRouter()
router.register(r'', UserViewSet, basename='user')

app_name = 'users'

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('login/', FinovaIDLoginView.as_view(), name='login'),
    path('verify-email/', VerifyEmailOTPView.as_view(), name='verify_email'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('', include(router.urls)),
]