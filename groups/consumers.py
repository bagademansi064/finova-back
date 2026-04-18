import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Group, GroupMessage, GroupMember
from users.models import User

class GroupChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_id = self.scope['url_route']['kwargs']['group_id']
        self.room_group_name = f"group_{self.group_id.replace('-', '_')}"
        
        # User must be authenticated via JWT middleware
        if not self.scope['user'].is_authenticated:
            await self.close(code=4001)
            return
            
        # Verify user is an active member of the group
        is_member = await self.is_user_in_group(self.scope['user'], self.group_id)
        if not is_member:
            await self.close(code=4003)
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        msg_type = text_data_json.get('type', 'message') # 'message' or 'typing'
        
        if msg_type == 'typing':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_user_typing',
                    'sender_finova_id': self.scope['user'].finova_id,
                    'sender_username': self.scope['user'].username,
                    'is_typing': text_data_json.get('is_typing', True)
                }
            )
            return

        content = text_data_json.get('content', '')
        reply_to_id = text_data_json.get('reply_to', None)
        message_type = text_data_json.get('message_type', 'text')
        stock_symbol = text_data_json.get('stock_symbol', None)
        
        if not content:
            return
            
        # Save message to database
        saved_msg = await self.save_message(
            self.scope['user'], self.group_id, content, reply_to_id, message_type, stock_symbol
        )
        
        sender_username = self.scope['user'].username
        sender_finova_id = self.scope['user'].finova_id
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_message_broadcast',
                'id': str(saved_msg.id),
                'content': saved_msg.content,
                'message_type': saved_msg.message_type,
                'stock_symbol': saved_msg.stock_symbol,
                'sender_finova_id': sender_finova_id,
                'sender_username': sender_username,
                'is_pinned': saved_msg.is_pinned,
                'created_at': saved_msg.created_at.isoformat(),
                'reply_to': reply_to_id,
            }
        )

    # Receive message from room group
    async def group_message_broadcast(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event))

    async def group_user_typing(self, event):
        # Send typing notification to WebSocket
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def is_user_in_group(self, user, group_id):
        try:
            return GroupMember.objects.filter(
                group_id=group_id, 
                user=user, 
                is_active=True
            ).exists()
        except Group.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, user, group_id, content, reply_to_id=None, message_type='text', stock_symbol=None):
        group = Group.objects.get(id=group_id)
        msg = GroupMessage.objects.create(
            group=group,
            sender=user,
            content=content,
            message_type=message_type,
            stock_symbol=stock_symbol,
            reply_to_id=reply_to_id
        )
        
        # Update the group's updated_at timestamp to bubble it up
        group.updated_at = msg.created_at
        group.save(update_fields=['updated_at'])
        
        return msg
