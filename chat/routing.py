from django.urls import re_path
from . import consumers as chat_consumers
from groups import consumers as group_consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<conversation_id>[0-9a-f-]+)/$', chat_consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/groups/(?P<group_id>[0-9a-f-]+)/$', group_consumers.GroupChatConsumer.as_asgi()),
]
