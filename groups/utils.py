import re
import string
import random


def generate_group_finova_id():
    """Generate a unique Finova ID for groups (e.g. GRP-A4F821)"""
    from .models import Group
    chars = string.ascii_uppercase + string.digits
    while True:
        fid = 'GRP-' + ''.join(random.choices(chars, k=6))
        if not Group.objects.filter(finova_id=fid).exists():
            return fid


# def generate_community_finova_id():
#     """Generate a unique Finova ID for communities (e.g. COM-B7X912)"""
#     from communities.models import Community
#     chars = string.ascii_uppercase + string.digits
#     while True:
#         fid = 'COM-' + ''.join(random.choices(chars, k=6))
#         if not Community.objects.filter(finova_id=fid).exists():
#             return fid


def parse_stock_template(content):
    """
    Parse /stocks "SYMBOL" templates from message content.
    
    Examples:
        /stocks "AAPL"         -> ["AAPL"]
        /stocks "RELIANCE"     -> ["RELIANCE"]
        Check /stocks "TSLA"   -> ["TSLA"]
    
    Returns list of stock symbols found, or empty list.
    """
    pattern = r'/stocks\s+"([^"]+)"'
    matches = re.findall(pattern, content, re.IGNORECASE)
    return [m.upper().strip() for m in matches]


def parse_news_template(content):
    """
    Parse /news "topic" templates from message content.
    
    Returns list of news topics found, or empty list.
    """
    pattern = r'/news\s+"([^"]+)"'
    matches = re.findall(pattern, content, re.IGNORECASE)
    return [m.strip() for m in matches]


from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def broadcast_group_message(group_id, message_data):
    """
    Broadcast a message to a group's WebSocket room from outside a consumer.
    message_data should be a dict formatted for the group_message_broadcast handler.
    """
    channel_layer = get_channel_layer()
    if not channel_layer: return
    
    room_group_name = f"group_{str(group_id).replace('-', '_')}"
    
    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'group_message_broadcast',
            **message_data
        }
    )

def detect_message_type(content):
    """
    Auto-detect message type based on content templates.
    Returns tuple of (message_type, stock_symbol_or_none).
    
    Supported formats:
      /stock "SYMBOL"           -> stock_card
      /stock SYMBOL             -> stock_card
      /stock SYMBOL discuss     -> stock_card
      /stock SYMBOL poll buy    -> stock_card
      /stock SYMBOL poll sell   -> stock_card
      /stocks "SYMBOL"          -> stock_card  (legacy)
      /news "topic"             -> news_card
    """
    # New format: /stock SYMBOL [discuss|poll buy|poll sell|poll]
    new_pattern = r'/stock\s+["\']?([A-Za-z0-9._-]+)["\']?(?:\s+(?:discuss|poll(?:\s+(?:buy|sell))?))?'
    match = re.match(new_pattern, content.strip(), re.IGNORECASE)
    if match:
        return 'stock_card', match.group(1).upper()
    
    # Legacy format: /stocks "SYMBOL"
    stocks = parse_stock_template(content)
    if stocks:
        return 'stock_card', stocks[0]
    
    news = parse_news_template(content)
    if news:
        return 'news_card', None
    
    return 'text', None

