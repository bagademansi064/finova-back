from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from django.db.models import Count, Q
from .models import (
    Group, GroupMember, GroupMessage, GroupWallet, WalletTransaction,
    Discussion, DiscussionComment, TradePoll, Vote, JoinRequest,
    GroupInvitation
)
from .serializers import (
    GroupCreateSerializer, GroupListSerializer, GroupDetailSerializer,
    GroupUpdateSerializer, GroupMemberSerializer,
    GroupMessageSerializer, GroupMessageCreateSerializer,
    DiscussionSerializer, DiscussionCreateSerializer,
    DiscussionCommentSerializer,
    TradePollSerializer, VoteCreateSerializer, VoteSerializer,
    JoinRequestSerializer, GroupInvitationSerializer
)
from .permissions import IsGroupMember, IsGroupAdmin


# ──────────────────── Helper Mixin ────────────────────

class GroupLookupMixin:
    """Mixin to resolve a group from the URL's finova_id kwarg."""

    def get_group(self):
        finova_id = self.kwargs.get('group_finova_id')
        if not finova_id:
            return None
        return get_object_or_404(Group, finova_id=finova_id, is_active=True)


# ──────────────────── Group CRUD ────────────────────

class GroupViewSet(viewsets.ModelViewSet):
    """
    Investment Group management.

    POST   /api/groups/                         — create a new group
    GET    /api/groups/                         — list your groups
    GET    /api/groups/{finova_id}/              — group detail (about)
    PATCH  /api/groups/{finova_id}/              — update group settings (admin)
    DELETE /api/groups/{finova_id}/              — deactivate group (admin)
    POST   /api/groups/{finova_id}/join/         — join a group
    POST   /api/groups/{finova_id}/leave/        — leave a group
    GET    /api/groups/{finova_id}/members/       — list members
    PATCH  /api/groups/{finova_id}/promote/       — promote/demote member (admin)
    POST   /api/groups/{finova_id}/kick/          — kick member (admin)
    """
    permission_classes = [IsAuthenticated]
    lookup_field = 'finova_id'

    def get_queryset(self):
        user = self.request.user
        if self.action == 'list':
            # Show groups where the user is a member
            return Group.objects.filter(
                members__user=user, members__is_active=True, is_active=True
            ).distinct()
        return Group.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action == 'create':
            return GroupCreateSerializer
        elif self.action == 'list':
            return GroupListSerializer
        elif self.action in ['update', 'partial_update']:
            return GroupUpdateSerializer
        return GroupDetailSerializer

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsGroupAdmin()]
        return super().get_permissions()

    def get_group(self):
        """For permission classes that need group context."""
        finova_id = self.kwargs.get('finova_id') or self.kwargs.get('pk')
        if finova_id:
            return Group.objects.filter(finova_id=finova_id, is_active=True).first()
        return None

    def perform_destroy(self, instance):
        """Soft-delete: deactivate instead of deleting."""
        instance.is_active = False
        instance.save(update_fields=['is_active'])

    @action(detail=False, methods=['get'])
    def garden(self, request):
        """List top performing groups for the Garden section."""
        groups = self.get_queryset().annotate(
            num_members=Count('members', filter=Q(members__is_active=True))
        ).order_by('-num_members', '-wallet__current_balance')[:20]
        serializer = GroupListSerializer(groups, many=True)
        return Response(serializer.data)

    # ── Join / Leave ──

    @action(detail=True, methods=['post'])
    def join(self, request, finova_id=None):
        """Join a group or send a join request by its Finova ID."""
        group = self.get_object()

        # Check minimum trust score
        if request.user.consensus_score < group.minimum_trust_score:
            return Response(
                {"error": f"Requires a trust score of at least {group.minimum_trust_score}."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if group.is_full:
            return Response(
                {"error": f"Group is full ({group.member_count}/{group.max_members})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Handle closed groups (Requires Join Request)
        if group.requires_approval:
            # Check if request already exists
            existing_request = group.join_requests.filter(user=request.user).first()
            if existing_request:
                if existing_request.status == 'pending':
                    return Response({"message": "You already have a pending request."}, status=status.HTTP_200_OK)
                elif existing_request.status == 'approved':
                    pass # Continue to join if somehow it's approved but user left
                elif existing_request.status == 'rejected':
                    return Response({"error": "Your join request was previously rejected."}, status=status.HTTP_403_FORBIDDEN)
            
            # If not previously requested or trying again
            if not existing_request or existing_request.status != 'approved':
                message = request.data.get('message', '').strip()
                JoinRequest.objects.create(group=group, user=request.user, message=message[:500])
                return Response(
                    {"message": "Join request sent. Awaiting admin approval.", "group_finova_id": group.finova_id},
                    status=status.HTTP_202_ACCEPTED,
                )

        # Standard direct join or completing an approved request
        membership, created = GroupMember.objects.get_or_create(
            group=group, user=request.user,
            defaults={'role': 'member'},
        )

        if not created and membership.is_active:
            return Response(
                {"error": "You are already a member of this group."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif not created:
            # Re-activate if previously left
            membership.is_active = True
            membership.save(update_fields=['is_active'])

        return Response(
            {"message": f"Joined {group.name} successfully.", "group_finova_id": group.finova_id},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def leave(self, request, finova_id=None):
        """Leave a group."""
        group = self.get_object()
        membership = GroupMember.objects.filter(
            group=group, user=request.user, is_active=True
        ).first()

        if not membership:
            return Response(
                {"error": "You are not a member of this group."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if membership.role == 'admin' and group.members.filter(role='admin', is_active=True).count() <= 1:
            return Response(
                {"error": "You are the only admin. Transfer admin role before leaving."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership.is_active = False
        membership.save(update_fields=['is_active'])

        return Response(
            {"message": f"Left {group.name} successfully."},
            status=status.HTTP_200_OK,
        )

    # ── Member Management ──

    @action(detail=True, methods=['get'])
    def members(self, request, finova_id=None):
        """List all active members of a group."""
        group = self.get_object()
        members = group.members.filter(is_active=True).select_related('user')
        serializer = GroupMemberSerializer(members, many=True)
        return Response(serializer.data)

    # ── Admin Join Requests ──

    @action(detail=True, methods=['get'])
    def requests(self, request, finova_id=None):
        """List pending join requests. Admins only."""
        group = self.get_object()
        admin_membership = group.members.filter(user=request.user, role='admin', is_active=True).first()
        if not admin_membership:
            return Response({"error": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
            
        join_requests = group.join_requests.filter(status='pending').select_related('user')
        serializer = JoinRequestSerializer(join_requests, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='approve-request')
    def approve_request(self, request, finova_id=None):
        """Approve a join request."""
        group = self.get_object()
        admin_membership = group.members.filter(user=request.user, role='admin', is_active=True).first()
        if not admin_membership:
            return Response({"error": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
            
        user_finova_id = request.data.get('user_finova_id')
        join_request = group.join_requests.filter(status='pending', user__finova_id=user_finova_id).first()
        
        if not join_request:
            return Response({"error": "Pending request not found."}, status=status.HTTP_404_NOT_FOUND)
            
        if group.is_full:
            return Response({"error": "Group is full."}, status=status.HTTP_400_BAD_REQUEST)
            
        join_request.status = 'approved'
        join_request.save(update_fields=['status'])
        
        membership, created = GroupMember.objects.get_or_create(
            group=group, user=join_request.user,
            defaults={'role': 'member'}
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=['is_active'])
            
        return Response({"message": f"Approved {join_request.user.username} to join {group.name}."})

    @action(detail=True, methods=['post'], url_path='reject-request')
    def reject_request(self, request, finova_id=None):
        """Reject a join request."""
        group = self.get_object()
        admin_membership = group.members.filter(user=request.user, role='admin', is_active=True).first()
        if not admin_membership:
            return Response({"error": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
            
        user_finova_id = request.data.get('user_finova_id')
        join_request = group.join_requests.filter(status='pending', user__finova_id=user_finova_id).first()
        
        if not join_request:
            return Response({"error": "Pending request not found."}, status=status.HTTP_404_NOT_FOUND)
            
        join_request.status = 'rejected'
        join_request.save(update_fields=['status'])
        
        return Response({"message": f"Rejected {join_request.user.username}'s request."})

    @action(detail=True, methods=['patch'], url_path='promote')
    def promote(self, request, finova_id=None):
        """
        Promote or demote a member. Admin only.
        Body: { "user_finova_id": "ABC123", "role": "moderator" }
        """
        group = self.get_object()
        admin_membership = group.members.filter(
            user=request.user, role='admin', is_active=True
        ).first()
        if not admin_membership:
            return Response(
                {"error": "Only admins can promote or demote members."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_finova_id = request.data.get('user_finova_id')
        new_role = request.data.get('role')

        if new_role not in ['admin', 'moderator', 'member']:
            return Response(
                {"error": "Role must be 'admin', 'moderator', or 'member'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth import get_user_model
        User = get_user_model()
        target_user = User.objects.filter(finova_id=user_finova_id).first()
        if not target_user:
            return Response(
                {"error": f"User {user_finova_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        membership = group.members.filter(user=target_user, is_active=True).first()
        if not membership:
            return Response(
                {"error": "User is not an active member of this group."},
                status=status.HTTP_404_NOT_FOUND,
            )

        membership.role = new_role
        membership.save(update_fields=['role'])

        return Response({
            "message": f"{target_user.username} is now {new_role} in {group.name}.",
        })

    @action(detail=True, methods=['post'], url_path='kick')
    def kick(self, request, finova_id=None):
        """
        Kick a member from the group. Admin only.
        Body: { "user_finova_id": "ABC123" }
        """
        group = self.get_object()
        admin_membership = group.members.filter(
            user=request.user, role='admin', is_active=True
        ).first()
        if not admin_membership:
            return Response(
                {"error": "Only admins can kick members."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_finova_id = request.data.get('user_finova_id')
        from django.contrib.auth import get_user_model
        User = get_user_model()
        target_user = User.objects.filter(finova_id=user_finova_id).first()
        if not target_user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if target_user == request.user:
            return Response({"error": "You cannot kick yourself."}, status=status.HTTP_400_BAD_REQUEST)

        membership = group.members.filter(user=target_user, is_active=True).first()
        if not membership:
            return Response({"error": "User is not in this group."}, status=status.HTTP_404_NOT_FOUND)

        membership.is_active = False
        membership.save(update_fields=['is_active'])

        return Response({"message": f"{target_user.username} has been removed from {group.name}."})

    # ── Invitations ──

    @action(detail=True, methods=['post'], url_path='invite')
    def invite(self, request, finova_id=None):
        """
        Invite a user by Finova ID. Admin/moderator only.
        Body: { "user_finova_id": "ABC123" }
        """
        group = self.get_object()
        
        # Check permissions
        is_admin_or_mod = group.members.filter(
            user=request.user, 
            role__in=['admin', 'moderator'], 
            is_active=True
        ).exists()
        
        if not is_admin_or_mod:
            return Response({"error": "Only admins or moderators can invite members."}, status=status.HTTP_403_FORBIDDEN)
            
        user_finova_id = request.data.get('user_finova_id')
        if not user_finova_id:
            return Response({"error": "user_finova_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            
        from django.contrib.auth import get_user_model
        User = get_user_model()
        target_user = User.objects.filter(finova_id=user_finova_id.upper()).first()
        
        if not target_user:
            return Response({"error": "User with this Finova ID not found."}, status=status.HTTP_404_NOT_FOUND)
            
        if group.members.filter(user=target_user, is_active=True).exists():
            return Response({"error": "User is already a member of this group."}, status=status.HTTP_400_BAD_REQUEST)
            
        if group.is_full:
            return Response({"error": "Group is full."}, status=status.HTTP_400_BAD_REQUEST)
            
        invitation, created = GroupInvitation.objects.get_or_create(
            group=group,
            invitee=target_user,
            defaults={'invited_by': request.user, 'status': 'pending'}
        )
        
        if not created:
            if invitation.status == 'pending':
                return Response({"message": "An invitation is already pending for this user."}, status=status.HTTP_200_OK)
            # Re-invite if previously rejected
            invitation.status = 'pending'
            invitation.invited_by = request.user
            invitation.save()
            
        return Response({"message": f"Invitation sent to {target_user.username} successfully."}, status=status.HTTP_201_CREATED)

    # ── Wallet Management ──

    @action(detail=True, methods=['get'])
    def wallet(self, request, finova_id=None):
        """Retrieve the group's pooled capital balance."""
        group = self.get_object()
        from .serializers import GroupWalletSerializer
        serializer = GroupWalletSerializer(group.wallet)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def deposit(self, request, finova_id=None):
        """Atomically deposit funds from user's individual capital to group pool."""
        group = self.get_object()
        user = request.user
        amount = request.data.get('amount')
        
        from decimal import Decimal, InvalidOperation
        try:
            amount = Decimal(str(amount))
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return Response({"error": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
            
        from django.db import transaction
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(id=user.id)
            locked_wallet = GroupWallet.objects.select_for_update().get(group=group)
            
            if locked_user.individual_virtual_capital < amount:
                return Response({"error": "Insufficient individual capital."}, status=status.HTTP_400_BAD_REQUEST)
                
            locked_user.individual_virtual_capital -= amount
            locked_user.save(update_fields=['individual_virtual_capital'])
            
            locked_wallet.current_balance += amount
            locked_wallet.save(update_fields=['current_balance'])
            
            WalletTransaction.objects.create(
                wallet=locked_wallet, user=locked_user, amount=amount, transaction_type='deposit'
            )
            
        return Response({
            "message": f"Successfully deposited {amount}.", 
            "new_pool_balance": locked_wallet.current_balance,
            "your_remaining_capital": locked_user.individual_virtual_capital
        })

    @action(detail=True, methods=['post'])
    def withdraw(self, request, finova_id=None):
        """Atomically withdraw funds from group pool back to user's individual capital."""
        group = self.get_object()
        user = request.user
        amount = request.data.get('amount')
        
        from decimal import Decimal, InvalidOperation
        try:
            amount = Decimal(str(amount))
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return Response({"error": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
            
        from django.db import transaction
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        with transaction.atomic():
            locked_user = User.objects.select_for_update().get(id=user.id)
            locked_wallet = GroupWallet.objects.select_for_update().get(group=group)
            
            if locked_wallet.current_balance < amount:
                return Response({"error": "Insufficient group pool funds."}, status=status.HTTP_400_BAD_REQUEST)
                
            locked_wallet.current_balance -= amount
            locked_wallet.save(update_fields=['current_balance'])
            
            locked_user.individual_virtual_capital += amount
            locked_user.save(update_fields=['individual_virtual_capital'])
            
            WalletTransaction.objects.create(
                wallet=locked_wallet, user=locked_user, amount=amount, transaction_type='withdraw'
            )
            
        return Response({
            "message": f"Successfully withdrew {amount}.", 
            "new_pool_balance": locked_wallet.current_balance,
            "your_new_capital": locked_user.individual_virtual_capital
        })


# ──────────────────── Group Messages ────────────────────

class GroupMessageViewSet(GroupLookupMixin, viewsets.ModelViewSet):
    """
    Chat messages inside a group.

    GET    /api/groups/{finova_id}/messages/       — message history (paginated)
    POST   /api/groups/{finova_id}/messages/       — send a message
    PATCH  /api/groups/{finova_id}/messages/{id}/   — edit or pin/unpin (admin)
    """
    permission_classes = [IsAuthenticated, IsGroupMember]
    http_method_names = ['get', 'post', 'patch']

    def get_queryset(self):
        group = self.get_group()
        return GroupMessage.objects.filter(group=group).select_related('sender')

    def get_serializer_class(self):
        if self.action == 'create':
            return GroupMessageCreateSerializer
        return GroupMessageSerializer

    def perform_create(self, serializer):
        group = self.get_group()
        serializer.save(group=group, sender=self.request.user)

    @action(detail=True, methods=['patch'], url_path='pin')
    def pin(self, request, group_finova_id=None, pk=None):
        """Pin or unpin a message. Admin/moderator only."""
        message = self.get_object()
        group = self.get_group()
        member = group.members.filter(
            user=request.user, role__in=['admin', 'moderator'], is_active=True
        ).first()
        if not member:
            return Response(
                {"error": "Only admins/moderators can pin messages."},
                status=status.HTTP_403_FORBIDDEN,
            )
        message.is_pinned = not message.is_pinned
        message.save(update_fields=['is_pinned'])
        action_word = "pinned" if message.is_pinned else "unpinned"
        return Response({"message": f"Message {action_word}."})


# ──────────────────── Discussions ────────────────────

class DiscussionViewSet(GroupLookupMixin, viewsets.ModelViewSet):
    """
    Discussion-to-Poll Pipeline within a group.

    GET    /api/groups/{finova_id}/discussions/              — list discussions
    POST   /api/groups/{finova_id}/discussions/              — propose a new discussion
    GET    /api/groups/{finova_id}/discussions/{id}/          — discussion detail
    POST   /api/groups/{finova_id}/discussions/{id}/comment/  — add comment
    """
    permission_classes = [IsAuthenticated, IsGroupMember]
    http_method_names = ['get', 'post']

    def get_queryset(self):
        group = self.get_group()
        return Discussion.objects.filter(group=group).select_related('proposed_by')

    def get_serializer_class(self):
        if self.action == 'create':
            return DiscussionCreateSerializer
        return DiscussionSerializer

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to inject requires_additional_funding flag."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        
        # Funding validation logic
        if instance.discussion_type == 'buy' and (instance.status == 'pooling' or (instance.status == 'open' and instance.group.wallet.current_balance < instance.required_capital)):
            data['requires_additional_funding'] = True
        else:
            data['requires_additional_funding'] = False
            
        return Response(data)

    def perform_create(self, serializer):
        group = self.get_group()
        serializer.save(group=group, proposed_by=self.request.user)

    @action(detail=True, methods=['post'])
    def comment(self, request, group_finova_id=None, pk=None):
        """
        Add a comment to a discussion. Increments engagement.
        Auto-unlocks voting when threshold is met.
        Body: { "content": "I think this is a good buy because..." }
        """
        discussion = self.get_object()

        if discussion.status != 'open':
            return Response(
                {"error": "Discussion is no longer open for comments."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content = request.data.get('content', '').strip()
        if not content:
            return Response(
                {"error": "Comment content is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comment = DiscussionComment.objects.create(
            discussion=discussion,
            author=request.user,
            content=content,
        )

        # Increment engagement
        discussion.engagement_count += 1
        discussion.save(update_fields=['engagement_count'])

        # Auto-unlock voting if threshold met
        poll = None
        if discussion.can_unlock_voting:
            poll = discussion.unlock_voting()

        response_data = DiscussionCommentSerializer(comment).data
        if poll:
            response_data['voting_unlocked'] = True
            response_data['poll_id'] = str(poll.id)

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='direct-vote')
    def direct_vote(self, request, group_finova_id=None, pk=None):
        """
        Bypass discussion and proceed to Voting or Pooling based on capital constraints.
        If underfunded, sets expires_at.
        """
        discussion = self.get_object()
        
        if discussion.status != 'open':
            return Response({"error": "Proposal is not open."}, status=status.HTTP_400_BAD_REQUEST)
            
        wallet = discussion.group.wallet
        if discussion.discussion_type == 'buy' and wallet.current_balance < discussion.required_capital:
            discussion.status = 'pooling'
            discussion.expires_at = timezone.now() + timezone.timedelta(hours=24)
            discussion.save(update_fields=['status', 'expires_at'])
            return Response({
                "message": "Insufficient funds. Proposal moved to POOLING.",
                "requires_additional_funding": True,
                "expires_at": discussion.expires_at
            })
            
        poll = discussion.unlock_voting()
        return Response({
            "message": "Funds sufficient. Voting unlocked.",
            "requires_additional_funding": False,
            "poll_id": str(poll.id) if poll else None
        })


# ──────────────────── Trade Polls & Voting ────────────────────

class TradePollViewSet(GroupLookupMixin, viewsets.ReadOnlyModelViewSet):
    """
    Trade polls and voting within a group.

    GET    /api/groups/{finova_id}/polls/              — list polls
    GET    /api/groups/{finova_id}/polls/{id}/          — poll detail + results
    POST   /api/groups/{finova_id}/polls/{id}/vote/     — cast vote
    """
    permission_classes = [IsAuthenticated, IsGroupMember]
    serializer_class = TradePollSerializer

    def get_queryset(self):
        group = self.get_group()
        return TradePoll.objects.filter(
            discussion__group=group
        ).select_related('discussion')

    @action(detail=True, methods=['post'])
    def vote(self, request, group_finova_id=None, pk=None):
        """
        Cast a vote on a trade poll.
        Body: { "choice": "buy" }  (options: buy, sell, hold)
        """
        poll = self.get_object()

        if poll.status != 'active':
            return Response(
                {"error": "This poll is no longer active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if poll.is_expired:
            poll.resolve()
            return Response(
                {"error": "Voting deadline has passed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Capital contribution gate: User must have deposited at least once.
        has_deposited = WalletTransaction.objects.filter(
            wallet=poll.discussion.group.wallet,
            user=request.user,
            transaction_type='deposit'
        ).exists()

        if not has_deposited:
            return Response(
                {"error": "You must contribute to the pool capital before voting."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check user hasn't already voted
        if Vote.objects.filter(poll=poll, voter=request.user).exists():
            return Response(
                {"error": "You have already voted on this poll."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        choice = serializer.validated_data['choice']

        # Create vote
        vote = Vote.objects.create(
            poll=poll, voter=request.user, choice=choice
        )

        # Update tallies
        if choice == 'buy':
            poll.result_buy_count += 1
        elif choice == 'sell':
            poll.result_sell_count += 1
        elif choice == 'hold':
            poll.result_hold_count += 1
        poll.save(update_fields=['result_buy_count', 'result_sell_count', 'result_hold_count'])

        # Increment user's global vote counter
        request.user.record_vote()

        # Check for Turbo-Reduction
        poll.apply_turbo_reduction()

        # Check if quorum met → auto-resolve
        if poll.quorum_met:
            poll.resolve()

        return Response({
            "message": f"Vote '{choice}' recorded.",
            "turbo_applied": poll.turbo_reduction_applied,
            "poll": TradePollSerializer(poll).data,
        }, status=status.HTTP_201_CREATED)


# ──────────────────── Group Invitations ────────────────────

class GroupInvitationViewSet(viewsets.ModelViewSet):
    """
    User-side management of group invitations.
    GET /api/invitations/          — list your received invitations
    POST /api/invitations/{id}/respond/ — accept or reject
    """
    permission_classes = [IsAuthenticated]
    serializer_class = GroupInvitationSerializer
    http_method_names = ['get', 'post']

    def get_queryset(self):
        return GroupInvitation.objects.filter(invitee=self.request.user, status='pending').select_related('group', 'invited_by')

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """Respond to an invitation: { "action": "accept" | "reject" }"""
        invitation = self.get_object()
        user_action = request.data.get('action')

        if user_action == 'accept':
            if invitation.group.is_full:
                return Response({"error": "Group is full."}, status=status.HTTP_400_BAD_REQUEST)
            
            invitation.status = 'accepted'
            invitation.save()

            # Create membership
            membership, created = GroupMember.objects.get_or_create(
                group=invitation.group, user=request.user,
                defaults={'role': 'member'}
            )
            if not created and not membership.is_active:
                membership.is_active = True
                membership.save()
            
            return Response({"message": f"Joined {invitation.group.name} successfully."})
        
        elif user_action == 'reject':
            invitation.status = 'rejected'
            invitation.save()
            return Response({"message": "Invitation rejected."})
        
        return Response({"error": "Invalid action. Use 'accept' or 'reject'."}, status=status.HTTP_400_BAD_REQUEST)

