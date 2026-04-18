from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Group, GroupMember, GroupMessage, GroupWallet, WalletTransaction,
    Discussion, DiscussionComment, TradePoll, Vote, JoinRequest,
    GroupInvitation, GroupHolding
)
from market.models import StockCache

User = get_user_model()


class GroupHoldingSerializer(serializers.ModelSerializer):
    current_price = serializers.SerializerMethodField()
    profit_loss_percent = serializers.SerializerMethodField()
    group_name = serializers.ReadOnlyField(source='group.name')

    class Meta:
        model = GroupHolding
        fields = [
            'id', 'group', 'group_name', 'stock_symbol', 'quantity', 
            'average_buy_price', 'total_invested', 'current_price', 
            'profit_loss_percent', 'updated_at'
        ]

    def get_current_price(self, obj):
        stock = StockCache.objects.filter(symbol=obj.stock_symbol).first()
        return stock.current_price if stock else None

    def get_profit_loss_percent(self, obj):
        stock = StockCache.objects.filter(symbol=obj.stock_symbol).first()
        if stock and stock.current_price and obj.average_buy_price > 0:
            diff = stock.current_price - obj.average_buy_price
            return (diff / obj.average_buy_price) * 100
        return 0


# ──────────────────────── Member Serializers ────────────────────────

class GroupMemberSerializer(serializers.ModelSerializer):
    """Serializer for group membership details."""
    username = serializers.CharField(source='user.username', read_only=True)
    finova_id = serializers.CharField(source='user.finova_id', read_only=True)
    profile_picture = serializers.ImageField(source='user.profile_picture', read_only=True)
    user_level = serializers.CharField(source='user.user_level', read_only=True)
    consensus_score = serializers.IntegerField(source='user.consensus_score', read_only=True)

    class Meta:
        model = GroupMember
        fields = [
            'id', 'finova_id', 'username', 'profile_picture',
            'user_level', 'consensus_score', 'role', 'is_active', 'joined_at',
        ]
        read_only_fields = ['id', 'joined_at']


class JoinRequestSerializer(serializers.ModelSerializer):
    """Serializer for group join requests."""
    username = serializers.CharField(source='user.username', read_only=True)
    finova_id = serializers.CharField(source='user.finova_id', read_only=True)
    profile_picture = serializers.ImageField(source='user.profile_picture', read_only=True)
    user_level = serializers.CharField(source='user.user_level', read_only=True)
    consensus_score = serializers.IntegerField(source='user.consensus_score', read_only=True)

    class Meta:
        model = JoinRequest
        fields = [
            'id', 'group', 'user', 'finova_id', 'username', 'profile_picture',
            'user_level', 'consensus_score', 'status', 'message', 'created_at'
        ]
        read_only_fields = ['id', 'group', 'user', 'status', 'created_at']


class GroupInvitationSerializer(serializers.ModelSerializer):
    """Serializer for group invitations sent by admins to users."""
    group_name = serializers.CharField(source='group.name', read_only=True)
    group_finova_id = serializers.CharField(source='group.finova_id', read_only=True)
    group_member_count = serializers.IntegerField(source='group.member_count', read_only=True)
    group_risk_level = serializers.CharField(source='group.risk_level', read_only=True)
    group_description = serializers.CharField(source='group.description', read_only=True)
    invited_by_username = serializers.CharField(source='invited_by.username', read_only=True)
    invitee_username = serializers.CharField(source='invitee.username', read_only=True)
    invitee_finova_id = serializers.CharField(source='invitee.finova_id', read_only=True)

    class Meta:
        model = GroupInvitation
        fields = [
            'id', 'group', 'group_name', 'group_finova_id', 
            'group_member_count', 'group_risk_level', 'group_description',
            'invited_by', 'invited_by_username',
            'invitee', 'invitee_username', 'invitee_finova_id',
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'group', 'invited_by', 'invitee', 'status', 'created_at', 'updated_at']


# ──────────────────────── Group Serializers ────────────────────────

class WalletTransactionSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = WalletTransaction
        fields = ['id', 'user_username', 'amount', 'transaction_type', 'reference_id', 'created_at']


class GroupWalletSerializer(serializers.ModelSerializer):
    transactions = WalletTransactionSerializer(many=True, read_only=True)
    
    class Meta:
        model = GroupWallet
        fields = ['id', 'current_balance', 'updated_at', 'transactions']


class GroupCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new investment group."""
    invited_finova_ids = serializers.ListField(
        child=serializers.CharField(max_length=10),
        write_only=True,
        required=False,
        help_text="Optional list of Finova IDs to invite during creation."
    )

    class Meta:
        model = Group
        fields = [
            'name', 'description', 'guidelines', 'group_photo',
            'risk_level', 'max_members', 'requires_approval', 'minimum_trust_score',
            'invited_finova_ids'
        ]

    def validate_max_members(self, value):
        if value < 2:
            raise serializers.ValidationError("A group must allow at least 2 members.")
        if value > 50:
            raise serializers.ValidationError("A group can have at most 50 members.")
        return value

    def create(self, validated_data):
        invited_finova_ids = validated_data.pop('invited_finova_ids', [])
        user = self.context['request'].user
        group = Group.objects.create(created_by=user, **validated_data)
        
        # Handle initial invitations
        if invited_finova_ids:
            for fid in invited_finova_ids:
                invitee = User.objects.filter(finova_id=fid.upper()).first()
                if invitee and invitee != user:
                    GroupInvitation.objects.get_or_create(
                        group=group,
                        invited_by=user,
                        invitee=invitee
                    )
        
        return group


class GroupListSerializer(serializers.ModelSerializer):
    """Compact serializer for listing groups."""
    member_count = serializers.ReadOnlyField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Group
        fields = [
            'id', 'finova_id', 'name', 'group_photo', 'risk_level',
            'member_count', 'max_members', 'created_by_username',
            'requires_approval', 'minimum_trust_score',
            'is_active', 'created_at',
        ]


class GroupDetailSerializer(serializers.ModelSerializer):
    """Full group detail with member list and about section."""
    member_count = serializers.ReadOnlyField()
    is_full = serializers.ReadOnlyField()
    members = GroupMemberSerializer(many=True, read_only=True)
    wallet = GroupWalletSerializer(read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    created_by_finova_id = serializers.CharField(source='created_by.finova_id', read_only=True)

    class Meta:
        model = Group
        fields = [
            'id', 'finova_id', 'name', 'description', 'guidelines',
            'group_photo', 'risk_level', 'max_members', 'member_count',
            'is_full', 'requires_approval', 'minimum_trust_score', 'members', 'wallet', 'created_by', 'created_by_username',
            'created_by_finova_id', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'finova_id', 'created_by', 'created_at', 'updated_at']


class GroupUpdateSerializer(serializers.ModelSerializer):
    """Serializer for admins to update group settings."""

    class Meta:
        model = Group
        fields = [
            'name', 'description', 'guidelines', 'group_photo',
            'risk_level', 'max_members', 'requires_approval', 'minimum_trust_score',
        ]


# ──────────────────────── Message Serializers ────────────────────────

class GroupMessageSerializer(serializers.ModelSerializer):
    """Serializer for group chat messages."""
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    sender_finova_id = serializers.CharField(source='sender.finova_id', read_only=True)
    sender_profile_picture = serializers.ImageField(source='sender.profile_picture', read_only=True)

    class Meta:
        model = GroupMessage
        fields = [
            'id', 'group', 'sender', 'sender_username', 'sender_finova_id',
            'sender_profile_picture', 'content', 'message_type',
            'stock_symbol', 'reply_to', 'is_pinned',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'group', 'sender', 'message_type', 'stock_symbol',
            'created_at', 'updated_at',
        ]


class GroupMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for sending a message in a group."""

    class Meta:
        model = GroupMessage
        fields = ['content', 'reply_to']


# ──────────────────────── Discussion Serializers ────────────────────────

class DiscussionCommentSerializer(serializers.ModelSerializer):
    """Serializer for discussion comments."""
    author_username = serializers.CharField(source='author.username', read_only=True)
    author_finova_id = serializers.CharField(source='author.finova_id', read_only=True)

    class Meta:
        model = DiscussionComment
        fields = [
            'id', 'discussion', 'author', 'author_username',
            'author_finova_id', 'content', 'created_at',
        ]
        read_only_fields = ['id', 'discussion', 'author', 'created_at']


class DiscussionCreateSerializer(serializers.ModelSerializer):
    """Serializer for proposing a new stock discussion."""

    class Meta:
        model = Discussion
        fields = [
            'stock_symbol', 'stock_name', 'discussion_type', 'reasoning',
            'required_capital'
        ]


class DiscussionSerializer(serializers.ModelSerializer):
    """Full discussion detail with engagement tracking."""
    proposed_by_username = serializers.CharField(source='proposed_by.username', read_only=True)
    proposed_by_finova_id = serializers.CharField(source='proposed_by.finova_id', read_only=True)
    can_unlock_voting = serializers.ReadOnlyField()
    comments = DiscussionCommentSerializer(many=True, read_only=True)
    has_poll = serializers.SerializerMethodField()

    class Meta:
        model = Discussion
        fields = [
            'id', 'group', 'proposed_by', 'proposed_by_username',
            'proposed_by_finova_id', 'stock_symbol', 'stock_name',
            'discussion_type', 'reasoning', 'status',
            'required_capital', 'expires_at',
            'min_engagement_to_unlock_vote', 'engagement_count',
            'can_unlock_voting', 'has_poll', 'comments',
            'created_at', 'voting_unlocked_at',
        ]
        read_only_fields = [
            'id', 'group', 'proposed_by', 'status',
            'engagement_count', 'created_at', 'voting_unlocked_at', 'expires_at'
        ]

    def get_has_poll(self, obj):
        return hasattr(obj, 'poll') and obj.poll is not None


# ──────────────────────── Voting Serializers ────────────────────────

class VoteSerializer(serializers.ModelSerializer):
    """Serializer for casting a vote."""
    voter_username = serializers.CharField(source='voter.username', read_only=True)
    voter_finova_id = serializers.CharField(source='voter.finova_id', read_only=True)

    class Meta:
        model = Vote
        fields = ['id', 'poll', 'voter', 'voter_username', 'voter_finova_id', 'choice', 'cast_at']
        read_only_fields = ['id', 'poll', 'voter', 'cast_at']


class VoteCreateSerializer(serializers.Serializer):
    """Serializer for the vote action."""
    choice = serializers.ChoiceField(choices=['buy', 'sell', 'hold'])


class TradePollSerializer(serializers.ModelSerializer):
    """Full poll details with vote tallies and timer state."""
    total_votes = serializers.ReadOnlyField()
    total_eligible_voters = serializers.ReadOnlyField()
    quorum_met = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    discussion_stock_symbol = serializers.CharField(source='discussion.stock_symbol', read_only=True)
    discussion_type = serializers.CharField(source='discussion.discussion_type', read_only=True)
    polled_price = serializers.DecimalField(source='discussion.polled_price', max_digits=12, decimal_places=2, read_only=True)
    votes = VoteSerializer(many=True, read_only=True)
    voter_participation = serializers.ReadOnlyField(source='get_voter_participation')

    class Meta:
        model = TradePoll
        fields = [
            'id', 'discussion', 'discussion_stock_symbol', 'discussion_type',
            'quorum_percentage', 'voting_deadline', 'original_deadline',
            'reduced_deadline', 'turbo_reduction_applied', 'status',
            'result_buy_count', 'result_sell_count', 'result_hold_count',
            'total_votes', 'total_eligible_voters', 'quorum_met', 'is_expired',
            'votes', 'voter_participation', 'created_at', 'resolved_at',
        ]
        read_only_fields = (
            'id', 'discussion', 'discussion_stock_symbol', 'discussion_type',
            'quorum_percentage', 'voting_deadline', 'original_deadline',
            'reduced_deadline', 'turbo_reduction_applied', 'status',
            'result_buy_count', 'result_sell_count', 'result_hold_count',
            'total_votes', 'total_eligible_voters', 'quorum_met', 'is_expired',
            'votes', 'voter_participation', 'created_at', 'resolved_at',
        )
