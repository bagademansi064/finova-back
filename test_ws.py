import os
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from channels.testing import WebsocketCommunicator
from backend.asgi import application
from users.models import User
from chat.models import Conversation
from groups.models import Group, GroupMember
from rest_framework_simplejwt.tokens import RefreshToken
from asgiref.sync import sync_to_async

@sync_to_async
def setup_test_data():
    # Wipe previous test data
    User.objects.filter(finova_id__in=["AAA111", "BBB222", "CCC333"]).delete()

    user1 = User.objects.create_user(
        username="ws_user1", email="ws1@finova.com", password="pwd",
        finova_id="AAA111", is_verified=True
    )
    user2 = User.objects.create_user(
        username="ws_user2", email="ws2@finova.com", password="pwd",
        finova_id="BBB222", is_verified=True
    )
    user3 = User.objects.create_user(
        username="ws_user3", email="ws3@finova.com", password="pwd",
        finova_id="CCC333", is_verified=True
    )

    conv = Conversation.objects.create(
        participant_one=user1, participant_two=user2
    )

    group = Group.objects.create(
        name="Test WebSocket Group", created_by=user1
    )
    GroupMember.objects.create(group=group, user=user1, role="admin", is_active=True)
    GroupMember.objects.create(group=group, user=user2, role="member", is_active=True)
    # user3 is NOT in the group to test unauthorized connection
    
    return user1, user2, user3, conv, group

async def test_websocket():
    print("\n--- 1. Setting up Users and Conversation ---")
    
    user1, user2, user3, conv, group = await setup_test_data()
    
    print(f"Conversation defined: {conv.id}")
    print(f"Group defined: {group.id}")

    # Generate JWT Tokens
    token1 = str(RefreshToken.for_user(user1).access_token)
    token2 = str(RefreshToken.for_user(user2).access_token)
    token3 = str(RefreshToken.for_user(user3).access_token)

    print("\n--- 2. Establising WebSockets ---")
    # Connect user 1 to Conversation
    communicator1 = WebsocketCommunicator(
        application, 
        f"/ws/chat/{conv.id}/?token={token1}"
    )
    connected1, _ = await communicator1.connect()
    print(f"1:1 Chat - User 1 Connected: {connected1}")
    await communicator1.disconnect()
    
    # Check Unauthorized Group Connection (user 3 is not a member)
    communicator_unauth = WebsocketCommunicator(
        application, 
        f"/ws/groups/{group.id}/?token={token3}"
    )
    connected_unauth, _ = await communicator_unauth.connect()
    print(f"Group Chat - User 3 (Not Member) Connection Refused: {not connected_unauth}")
    
    # Connect user 1 and user 2 to Group Chat
    communicator_g1 = WebsocketCommunicator(
        application, 
        f"/ws/groups/{group.id}/?token={token1}"
    )
    await communicator_g1.connect()
    
    communicator_g2 = WebsocketCommunicator(
        application, 
        f"/ws/groups/{group.id}/?token={token2}"
    )
    await communicator_g2.connect()
    print("Group Chat - User 1 & 2 Connected Successfully")

    print("\n--- 3. Testing Real-Time Broadcast ---")
    data = {
        "content": "Hello Group, this is an Admin via WebSocket!",
        "reply_to": None,
        "message_type": "text"
    }
    await communicator_g1.send_json_to(data)
    print("Group Chat - User 1 sent message...")
    
    # Receive from User 2's socket
    response_for_g2 = await communicator_g2.receive_json_from()
    print("Group Chat - User 2 received broadcast payload:\n", response_for_g2)
    
    assert response_for_g2['content'] == data['content']
    assert response_for_g2['sender_username'] == "ws_user1"
    
    # Receive from User 1's socket (it broadcasts to the whole room)
    response_for_g1 = await communicator_g1.receive_json_from()
    
    await communicator_g1.disconnect()
    await communicator_g2.disconnect()
    
    print("\nALL WEBSOCKET TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_websocket())
