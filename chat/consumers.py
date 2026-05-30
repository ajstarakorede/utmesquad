"""
WebSocket consumers for real-time chat functionality.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class ChatConsumer(AsyncWebsocketConsumer):
    """Consumer handling real-time chat messages."""
    
    async def connect(self):
        """Handle WebSocket connection — reject unauthenticated users."""
        self.user_type = self.scope['url_route']['kwargs'].get('user_type', 'anonymous')
        self.user_id = self.scope['url_route']['kwargs'].get('user_id', 'anonymous')

        # Auth guard: verify the session matches the claimed identity
        session = self.scope.get('session', {})
        admin_ok = self.user_type == 'admin' and session.get('admin_logged_in')
        candidate_ok = self.user_type == 'candidate' and str(session.get('candidate_id', '')) == self.user_id

        if not admin_ok and not candidate_ok:
            await self.close(code=4001)  # 4001 = Unauthorized
            return

        # Create a personal room for this user
        self.personal_room = f"user_{self.user_type}_{self.user_id}"

        await self.channel_layer.group_add(self.personal_room, self.channel_name)
        await self.channel_layer.group_add("group_utme_squad", self.channel_name)

        await self.accept()
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'message': 'Connected to UTME SQUAD chat server',
            'user_type': self.user_type,
            'user_id': self.user_id,
        }))
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave rooms
        if hasattr(self, 'personal_room'):
            await self.channel_layer.group_discard(
                self.personal_room,
                self.channel_name
            )
        
        await self.channel_layer.group_discard(
            "group_utme_squad",
            self.channel_name
        )
    
    async def receive(self, text_data):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'message')
            
            if message_type == 'private_message':
                await self.handle_private_message(data)
            elif message_type == 'group_message':
                await self.handle_group_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'read_receipt':
                await self.handle_read_receipt(data)
            elif message_type == 'join_group':
                await self.handle_join_group(data)
            elif message_type == 'voice_message':
                await self.handle_voice_message(data)
            
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    async def handle_private_message(self, data):
        """Handle a private message."""
        receiver_id = data.get('receiver_id')
        content = data.get('content')
        sender_name = data.get('sender_name', 'Unknown')
        
        # Send to receiver's personal room
        receiver_room = f"user_candidate_{receiver_id}"
        
        await self.channel_layer.group_send(
            receiver_room,
            {
                'type': 'chat_message',
                'message_type': 'private',
                'sender_type': self.user_type,
                'sender_id': self.user_id,
                'sender_name': sender_name,
                'content': content,
                'timestamp': data.get('timestamp'),
            }
        )
        
        # Send confirmation to sender
        await self.send(text_data=json.dumps({
            'type': 'message_sent',
            'message_type': 'private',
            'receiver_id': receiver_id,
        }))
    
    async def handle_group_message(self, data):
        """Handle a group message."""
        group_id = data.get('group_id')
        content = data.get('content')
        sender_name = data.get('sender_name', 'Unknown')
        group_name = data.get('group_name', 'Unknown Group')
        
        # Broadcast to all users in the group
        group_room = f"group_{group_name.lower().replace(' ', '_')}"
        
        await self.channel_layer.group_send(
            group_room,
            {
                'type': 'group_chat_message',
                'message_type': 'group',
                'group_id': group_id,
                'group_name': group_name,
                'sender_type': self.user_type,
                'sender_id': self.user_id,
                'sender_name': sender_name,
                'content': content,
                'timestamp': data.get('timestamp'),
            }
        )
    
    async def handle_typing(self, data):
        """Handle typing indicator."""
        receiver_id = data.get('receiver_id')
        is_typing = data.get('is_typing', False)
        
        receiver_room = f"user_candidate_{receiver_id}"
        
        await self.channel_layer.group_send(
            receiver_room,
            {
                'type': 'typing_indicator',
                'sender_id': self.user_id,
                'sender_type': self.user_type,
                'is_typing': is_typing,
            }
        )
    
    async def handle_read_receipt(self, data):
        """Handle read receipt."""
        message_id = data.get('message_id')
        sender_id = data.get('sender_id')
        
        sender_room = f"user_{sender_id}"
        
        await self.channel_layer.group_send(
            sender_room,
            {
                'type': 'read_receipt',
                'message_id': message_id,
                'read_by': self.user_id,
            }
        )
    
    async def handle_join_group(self, data):
        """Handle user joining a group."""
        group_name = data.get('group_name')
        group_room = f"group_{group_name.lower().replace(' ', '_')}"
        
        await self.channel_layer.group_add(
            group_room,
            self.channel_name
        )
        
        await self.send(text_data=json.dumps({
            'type': 'joined_group',
            'group': group_name,
        }))
    
    async def handle_voice_message(self, data):
        """Handle voice message notification."""
        receiver_id = data.get('receiver_id')
        voice_url = data.get('voice_url')
        duration = data.get('duration', 0)
        sender_name = data.get('sender_name', 'Unknown')
        
        receiver_room = f"user_candidate_{receiver_id}"
        
        await self.channel_layer.group_send(
            receiver_room,
            {
                'type': 'voice_message_notification',
                'sender_type': self.user_type,
                'sender_id': self.user_id,
                'sender_name': sender_name,
                'voice_url': voice_url,
                'duration': duration,
            }
        )
    
    # ============== RECEIVERS ==============
    
    async def chat_message(self, event):
        """Send private chat message to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'private_message',
            'sender_type': event['sender_type'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'content': event['content'],
            'timestamp': event.get('timestamp'),
        }))
    
    async def group_chat_message(self, event):
        """Send group chat message to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'group_message',
            'group_id': event['group_id'],
            'group_name': event['group_name'],
            'sender_type': event['sender_type'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'content': event['content'],
            'timestamp': event.get('timestamp'),
        }))
    
    async def typing_indicator(self, event):
        """Send typing indicator to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'sender_id': event['sender_id'],
            'sender_type': event['sender_type'],
            'is_typing': event['is_typing'],
        }))
    
    async def read_receipt(self, event):
        """Send read receipt to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'read_receipt',
            'message_id': event['message_id'],
            'read_by': event['read_by'],
        }))
    
    async def voice_message_notification(self, event):
        """Send voice message notification to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'voice_message',
            'sender_type': event['sender_type'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'voice_url': event['voice_url'],
            'duration': event['duration'],
        }))


class NotificationConsumer(AsyncWebsocketConsumer):
    """Consumer handling real-time notifications."""
    
    async def connect(self):
        """Handle WebSocket connection for notifications."""
        self.user_type = self.scope['url_route']['kwargs'].get('user_type', 'anonymous')
        self.user_id = self.scope['url_route']['kwargs'].get('user_id', 'anonymous')
        
        self.notification_room = f"notifications_{self.user_type}_{self.user_id}"
        
        await self.channel_layer.group_add(
            self.notification_room,
            self.channel_name
        )
        
        await self.accept()
        
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'message': 'Connected to notification server',
        }))
    
    async def disconnect(self, close_code):
        """Handle disconnection."""
        if hasattr(self, 'notification_room'):
            await self.channel_layer.group_discard(
                self.notification_room,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle incoming notification requests."""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'mark_read':
                notification_id = data.get('notification_id')
                await self.send(text_data=json.dumps({
                    'type': 'notification_read',
                    'notification_id': notification_id,
                }))
        
        except json.JSONDecodeError:
            pass
    
    async def notification_message(self, event):
        """Send notification to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification_type': event.get('notification_type', 'general'),
            'message': event['message'],
            'link': event.get('link', ''),
            'timestamp': event.get('timestamp'),
        }))
