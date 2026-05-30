from django.urls import path
from django.shortcuts import render

urlpatterns = [
    # Chat room page - for direct access
    path('room/<str:room_type>/<str:room_id>/', lambda request, room_type, room_id: 
         render(request, 'chat/room.html', {'room_type': room_type, 'room_id': room_id})),
]
