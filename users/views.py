from rest_framework import viewsets, status, generics, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from .serializers import (
    UserRegistrationSerializer,
    UserProfileSerializer,
    UserPublicSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    UserStatsSerializer,
    FinovaIDLoginSerializer,
    EmailOTPVerifySerializer,
    UserWatchlistSerializer
)
from .models import EmailVerificationOTP, UserWatchlist
from groups.models import GroupHolding
from groups.serializers import GroupHoldingSerializer
from market.models import StockCache
from django.core.mail import send_mail
import random
from rest_framework_simplejwt.tokens import RefreshToken
from .permissions import IsOwnerOrReadOnly

User = get_user_model()


class UserRegistrationView(generics.CreateAPIView):
    """
    User registration endpoint
    POST /api/users/register/
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Generate 6-digit OTP
        otp_code = f"{random.randint(100000, 999999)}"
        EmailVerificationOTP.objects.create(user=user, otp=otp_code)
        
        # Send Email Verification
        send_mail(
            subject='Verify your Finova Email',
            message=f'Hello {user.first_name},\n\nYour Finova Verification Code is: {otp_code}\n\nThis code will expire in 10 minutes.\n\nYour Finova ID is: {user.finova_id}',
            from_email='support@finova.com',
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        return Response({
            "user": UserProfileSerializer(user, context=self.get_serializer_context()).data,
            "message": "Account created successfully! Please check your email for the verification code."
        }, status=status.HTTP_201_CREATED)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user CRUD operations
    
    list: GET /api/users/
    retrieve: GET /api/users/{id}/
    update: PUT /api/users/{id}/
    partial_update: PATCH /api/users/{id}/
    destroy: DELETE /api/users/{id}/
    """
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'retrieve' and self.request.user != self.get_object():
            return UserPublicSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserProfileSerializer
    
    def get_queryset(self):
        """
        Optionally filter verified users or search
        """
        queryset = User.objects.all()
        
        # Filter verified users
        verified = self.request.query_params.get('verified', None)
        if verified is not None:
            queryset = queryset.filter(is_verified=True)
        
        # Search by username
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(username__icontains=search)
        
        return queryset
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Get current authenticated user profile
        GET /api/users/me/
        """
        serializer = UserProfileSerializer(request.user, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['put', 'patch'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """
        Update current user profile
        PUT/PATCH /api/users/update_profile/
        """
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=request.method == 'PATCH',
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            "user": UserProfileSerializer(request.user, context={'request': request}).data,
            "message": "Profile updated successfully"
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """
        Change user password
        POST /api/users/change_password/
        """
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        return Response({
            "message": "Password changed successfully"
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def stats(self, request, pk=None):
        """
        Get user statistics
        GET /api/users/{id}/stats/
        """
        user = self.get_object()
        serializer = UserStatsSerializer(user)
        return Response(serializer.data)
    

    
    @action(detail=False, methods=['delete'], permission_classes=[IsAuthenticated])
    def deactivate_account(self, request):
        """
        Deactivate user account (soft delete)
        DELETE /api/users/deactivate_account/
        """
        user = request.user
        user.is_active = False
        user.save()
        
        return Response({
            "message": "Account deactivated successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def dashboard(self, request):
        """
        Main dashboard data: Aggregate holdings from all user groups + watchlist
        GET /api/users/dashboard/
        """
        # 1. Get holdings from all groups user belongs to
        # Note: joined_groups is related_name from GroupMember
        user_groups_ids = request.user.group_memberships.all().values_list('group_id', flat=True)
        holdings = GroupHolding.objects.filter(group_id__in=user_groups_ids)
        holdings_data = GroupHoldingSerializer(holdings, many=True).data

        # 2. Get user's personal watchlist
        watchlist, _ = UserWatchlist.objects.get_or_create(user=request.user)
        
        # Hydrate watchlist symbols with current price data
        watchlist_stocks = StockCache.objects.filter(symbol__in=watchlist.symbols)
        
        # Minimal data for watchlist
        watchlist_data = []
        for symbol in watchlist.symbols:
            stock = next((s for s in watchlist_stocks if s.symbol == symbol), None)
            watchlist_data.append({
                'symbol': symbol,
                'current_price': float(stock.current_price) if stock and stock.current_price else 0,
                'percent_change': float(stock.percent_change) if stock and stock.percent_change else 0,
            })

        return Response({
            "invested": holdings_data,
            "watchlist": watchlist_data
        })

    @action(detail=False, methods=['post', 'delete'], permission_classes=[IsAuthenticated])
    def watchlist(self, request):
        """
        Add or remove symbols from personal watchlist
        POST/DELETE /api/users/watchlist/
        """
        symbol = request.data.get('symbol', '').upper()
        if not symbol:
            return Response({"error": "Symbol is required"}, status=status.HTTP_400_BAD_REQUEST)

        watchlist, _ = UserWatchlist.objects.get_or_create(user=request.user)
        
        if request.method == 'POST':
            if symbol not in watchlist.symbols:
                watchlist.symbols.append(symbol)
                watchlist.save()
            return Response({"symbols": watchlist.symbols, "message": f"Added {symbol}"})
            
        elif request.method == 'DELETE':
            if symbol in watchlist.symbols:
                watchlist.symbols.remove(symbol)
                watchlist.save()
            return Response({"symbols": watchlist.symbols, "message": f"Removed {symbol}"})

class FinovaIDLoginView(generics.GenericAPIView):
    """
    Login endpoint using Finova ID and Password
    POST /api/users/login/
    """
    serializer_class = FinovaIDLoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        finova_id = serializer.validated_data['finova_id'].upper()
        password = serializer.validated_data['password']
        
        try:
            user = User.objects.get(finova_id=finova_id)
        except User.DoesNotExist:
            return Response({"detail": "Invalid Finova ID or password."}, status=status.HTTP_401_UNAUTHORIZED)
            
        if not user.check_password(password):
            return Response({"detail": "Invalid Finova ID or password."}, status=status.HTTP_401_UNAUTHORIZED)
            
        if getattr(user, 'is_active', None) is False:
            return Response({"detail": "User account is disabled."}, status=status.HTTP_401_UNAUTHORIZED)
            
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserProfileSerializer(user, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class VerifyEmailOTPView(generics.GenericAPIView):
    """
    Verify Email using OTP
    POST /api/users/verify-email/
    """
    serializer_class = EmailOTPVerifySerializer
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        
        try:
            user = User.objects.get(email=email)
            otp_record = user.email_verification_otp
        except (User.DoesNotExist, EmailVerificationOTP.DoesNotExist):
            return Response({"detail": "Invalid email or no OTP requested."}, status=status.HTTP_400_BAD_REQUEST)
            
        if otp_record.otp != otp:
            return Response({"detail": "Invalid OTP code."}, status=status.HTTP_400_BAD_REQUEST)
            
        if not otp_record.is_valid():
            otp_record.delete()
            return Response({"detail": "OTP has expired. Please request another one."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Verify user
        user.is_verified = True
        user.save(update_fields=['is_verified'])
        otp_record.delete()
        
        return Response({
            "message": "Email verified successfully! You can now log in."
        }, status=status.HTTP_200_OK)