from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model
import jwt
from django.conf import settings

User = get_user_model()

@database_sync_to_async
def get_user_from_token(token_string):
    try:
        # Validate token using simplejwt
        UntypedToken(token_string)
        # Decode the token manually to get user_id
        decoded_data = jwt.decode(token_string, settings.SECRET_KEY, algorithms=["HS256"])
        user = User.objects.get(id=decoded_data['user_id'])
        return user
    except (InvalidToken, TokenError, User.DoesNotExist, jwt.DecodeError):
        return AnonymousUser()

class TokenAuthMiddleware:
    """
    Custom middleware that takes a token from the query string and authenticates via SimpleJWT.
    Usage: ws://localhost:8001/ws/chat/<uuid>/?token=<token>
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        query_params = parse_qs(query_string)
        
        token = query_params.get('token', [None])[0]
        
        if token:
            scope['user'] = await get_user_from_token(token)
        else:
            scope['user'] = AnonymousUser()
            
        return await self.inner(scope, receive, send)
