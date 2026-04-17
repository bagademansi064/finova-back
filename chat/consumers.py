import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Conversation, DirectMessage
from users.models import User

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f"chat_{self.conversation_id.replace('-', '_')}"
        
        # User must be authenticated
        if not self.scope['user'].is_authenticated:
            await self.close(code=4001)
            return
            
        # Verify user is in conversation
        is_participant = await self.is_user_in_conversation(self.scope['user'], self.conversation_id)
        if not is_participant:
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
        content = text_data_json.get('content', '')
        reply_to_id = text_data_json.get('reply_to', None)
        
        if not content:
            return
            
        # Save message to database
        saved_msg = await self.save_message(self.scope['user'], self.conversation_id, content, reply_to_id)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'id': str(saved_msg.id),
                'content': saved_msg.content,
                'message_type': saved_msg.message_type,
                'stock_symbol': saved_msg.stock_symbol,
                'sender_finova_id': self.scope['user'].finova_id,
                'sender_username': self.scope['user'].username,
                'created_at': saved_msg.created_at.isoformat(),
                'reply_to': reply_to_id,
            }
        )

    # Receive message from room group
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def is_user_in_conversation(self, user, conversation_id):
        try:
            conv = Conversation.objects.get(id=conversation_id)
            return user == conv.participant_one or user == conv.participant_two
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, user, conversation_id, content, reply_to_id=None):
        conv = Conversation.objects.get(id=conversation_id)
        msg = DirectMessage.objects.create(
            conversation=conv,
            sender=user,
            content=content,
            reply_to_id=reply_to_id
        )
        
        # Bump the conversation updated_at
        conv.save(update_fields=['updated_at'])
        
        return msg
