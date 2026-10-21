from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.welcome, name='welcome'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('signup/', views.signup_view, name='signup'),
    path('signup/submit/', views.signup_submit, name='signup_submit'),

    # Home + Posts
    path('home/', views.home, name='home'),
    path('posts/add/', views.add_post_page, name='add_post'),
    path('posts/create/', views.create_post, name='create_post'),
    path('posts/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('posts/<int:post_id>/comment/', views.add_comment, name='add_comment'),

    # Profile — specific paths MUST come before the <username> catch-all
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/block/<str:username>/', views.toggle_block, name='toggle_block'),
    path('profile/<str:username>/', views.profile, name='profile'),

    # Friends
    path('friends/', views.friends, name='friends'),

    # Friend Requests
    path('friend-requests/', views.friend_requests, name='friend_requests'),
    path('friend-request/send/<str:username>/', views.send_friend_request, name='send_friend_request'),
    path('friend-request/accept/<int:request_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friend-request/reject/<int:request_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('profile/unfriend/<str:username>/', views.unfriend, name='unfriend'),

    # Notifications & Search
    path('notifications/', views.notifications, name='notifications'),
    path('search/', views.search, name='search'),

    # Messages
    path('messages/', views.messages_list, name='messages'),
    path('messages/new/', views.start_new_chat, name='start_new_chat'),
    path('messages/new-group/', views.create_group, name='create_group'),
    path('messages/<int:chat_id>/', views.chat_view, name='chat_view'),
    path('messages/<int:chat_id>/send/', views.send_message, name='send_message'),
    path('messages/<int:chat_id>/fetch/', views.fetch_messages, name='fetch_messages'),
    path('messages/<int:chat_id>/typing/', views.set_typing, name='set_typing'),
    path('messages/<int:chat_id>/typing-status/', views.get_typing, name='get_typing'),
    path('messages/<int:chat_id>/action/', views.chat_action, name='chat_action'),
    path('messages/<int:chat_id>/delete/', views.delete_chat, name='delete_chat'),
    path('messages/<int:chat_id>/unlock/', views.unlock_chat, name='unlock_chat'),
    path('stickers/upload/', views.upload_sticker, name='upload_sticker'),
    path('stickers/list/', views.list_stickers, name='list_stickers'),

    # Settings
    path('settings/', views.settings, name='settings'),
    path('settings/toggle-active/', views.toggle_active_status, name='toggle_active_status'),
    path('settings/support/', views.submit_support, name='submit_support'),
    path('settings/deactivate/', views.deactivate_account, name='deactivate_account'),
    path('settings/reactivate/', views.reactivate_account, name='reactivate_account'),
    path('settings/delete/', views.delete_account, name='delete_account'),
    path('settings/download-info/', views.download_account_info, name='download_account_info'),
    path('settings/download-chats/', views.download_chat_history, name='download_chat_history'),
]