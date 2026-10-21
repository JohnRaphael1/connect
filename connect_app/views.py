import io
import json
import re
from datetime import date, timedelta

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from .models import (
    User, Post, Like, Comment, BlockList, Notification, Friendship,
    Chat, ChatMember, Message, MessageReaction, TypingStatus, Sticker,
    SupportTicket,
)


# ============================================================
# WELCOME / SPLASH
# ============================================================
def welcome(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'welcome.html')


# ============================================================
# AUTH — LOGIN / LOGOUT
# ============================================================
def user_login(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        identifier = (request.POST.get('identifier') or '').strip()
        password = request.POST.get('password') or ''

        if not identifier or not password:
            messages.error(request, "Please fill in both fields.")
            return render(request, 'auth/login.html', status=400)

        user_obj = (
            User.objects.filter(username__iexact=identifier).first()
            or User.objects.filter(email__iexact=identifier).first()
            or User.objects.filter(phone=identifier).first()
        )

        if user_obj is not None:
            if user_obj.is_deactivated:
                request.session['pending_reactivation_user'] = user_obj.id
                messages.warning(request, "Your account is temporarily deactivated. Please reactivate below.")
                return redirect('reactivate_account')

            authenticated = authenticate(request, username=user_obj.username, password=password)
            if authenticated is not None:
                login(request, authenticated)
                messages.success(request, f"Welcome back, {authenticated.full_name or authenticated.username}!")
                return redirect('home')

        messages.error(request, "Invalid credentials. Please try again.")
        return render(request, 'auth/login.html', status=400)

    return render(request, 'auth/login.html')


@login_required
def user_logout(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('login')


# ============================================================
# AUTH — SIGNUP
# ============================================================
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'auth/signup.html')


@csrf_exempt
def signup_submit(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed.'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Invalid request format.'}, status=400)

    full_name = (data.get('full_name') or '').strip()
    email     = (data.get('email') or '').strip().lower()
    phone     = (data.get('phone') or '').strip()
    dob_str   = (data.get('dob') or '').strip()
    gender    = (data.get('gender') or '').strip()
    password  = data.get('password') or ''
    username  = (data.get('username') or '').strip()

    errors = {}

    if not full_name: errors['full_name'] = 'Full name is required.'
    elif len(full_name) < 2: errors['full_name'] = 'Name is too short.'

    if not email and not phone: errors['contact'] = 'Provide an email or phone number.'

    if email:
        try: validate_email(email)
        except ValidationError: errors['email'] = 'Invalid email address.'

    if not username:
        base = (email.split('@')[0] if email else phone) or 'user'
        base = re.sub(r'[^\w.\-]', '', base) or 'user'
        username = base
        i = 1
        while User.objects.filter(username__iexact=username).exists():
            username = f"{base}{i}"
            i += 1

    if len(username) < 3: errors['username'] = 'Username must be at least 3 characters.'
    if len(username) > 30: errors['username'] = 'Username must be at most 30 characters.'

    dob = None
    if not dob_str: errors['dob'] = 'Date of birth is required.'
    else:
        try: dob = date.fromisoformat(dob_str)
        except ValueError: errors['dob'] = 'Invalid date.'
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 13: errors['dob'] = 'You must be at least 13 years old.'
            elif age > 120: errors['dob'] = 'Please enter a valid date of birth.'

    if gender not in ('M', 'F', 'O'): errors['gender'] = 'Please select a gender.'
    if len(password) < 8: errors['password'] = 'Password must be at least 8 characters.'

    if errors:
        return JsonResponse({'ok': False, 'errors': errors}, status=400)

    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({'ok': False, 'errors': {'username': 'Username already taken.'}}, status=400)
    if email and User.objects.filter(email__iexact=email).exists():
        return JsonResponse({'ok': False, 'errors': {'email': 'This email is already registered.'}}, status=400)
    if phone and User.objects.filter(phone=phone).exists():
        return JsonResponse({'ok': False, 'errors': {'phone': 'This phone number is already registered.'}}, status=400)

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, email=email or None, password=password,
                full_name=full_name, phone=phone or None, dob=dob, gender=gender,
            )
    except IntegrityError:
        return JsonResponse({'ok': False, 'error': 'Could not create account.'}, status=400)

    login(request, user)
    return JsonResponse({'ok': True, 'redirect': '/home/', 'username': user.username})


# ============================================================
# HOME & FEED
# ============================================================
@login_required
def home(request):
    blocked_ids = BlockList.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
    blocked_by_ids = BlockList.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
    excluded = set(blocked_ids) | set(blocked_by_ids)

    # Compute friend_ids FIRST so the posts filter can use it
    friend_relations = Friendship.objects.filter(
        Q(user=request.user, status='accepted') | Q(friend=request.user, status='accepted')
    )
    friend_ids = [f.friend_id if f.user_id == request.user.id else f.user_id for f in friend_relations]

    posts = (
        Post.objects.select_related('user')
        .prefetch_related('likes', 'comments__user')
        .exclude(user_id__in=excluded)
        .order_by('-created_at')
    )

    # Hide posts from private accounts unless they're friends
    posts = posts.exclude(
        Q(user__is_private=True) & ~Q(user_id__in=friend_ids)
    )

    friends_online = User.objects.filter(id__in=friend_ids, active_status=True)[:10]
    pending_requests = Friendship.objects.filter(friend=request.user, status='pending').select_related('user')[:3]

    unread_messages = Message.objects.filter(receiver=request.user, is_read=False).count()
    unread_notifs = Notification.objects.filter(user=request.user, is_read=False).count()

    recent_posts = (
        Post.objects.exclude(user=request.user)
        .filter(created_at__gte=timezone.now() - timedelta(hours=24))
        .exclude(user_id__in=excluded)
        .exists()
    )

    return render(request, 'home.html', {
        'nav_active': 'home',
        'posts': posts,
        'friends_online': friends_online,
        'pending_requests': pending_requests,
        'total_friends': len(friend_ids),
        'unread_messages': unread_messages,
        'unread_notifs': unread_notifs,
        'has_new_posts': recent_posts,
    })

    
@login_required
def add_post_page(request):
    if request.method == 'POST':
        text = (request.POST.get('text') or '').strip()
        image = request.FILES.get('image')
        video = request.FILES.get('video')

        if text or image or video:
            Post.objects.create(user=request.user, text=text or None, image=image, video=video)
            messages.success(request, "Post published successfully!")
            return redirect('home')
        messages.error(request, "Post cannot be empty.")

    return render(request, 'add_post.html', {'nav_active': 'add_post'})


@login_required
@require_POST
def create_post(request):
    text = (request.POST.get('text') or '').strip()
    image = request.FILES.get('image')
    video = request.FILES.get('video')

    if not text and not image and not video:
        return JsonResponse({'ok': False, 'error': 'Post cannot be empty.'}, status=400)

    post = Post.objects.create(user=request.user, text=text or None, image=image, video=video)
    html = render_to_string('partials/_post_card.html', {'post': post, 'user': request.user}, request=request)
    return JsonResponse({'ok': True, 'id': post.id, 'html': html})


@login_required
@require_POST
def toggle_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    like = Like.objects.filter(user=request.user, post=post).first()
    if like:
        like.delete()
        liked = False
    else:
        Like.objects.create(user=request.user, post=post)
        liked = True
        if post.user_id != request.user.id:
            Notification.objects.create(user=post.user, sender=request.user, notif_type='like')
    return JsonResponse({'ok': True, 'liked': liked, 'count': post.likes.count()})


@login_required
@require_POST
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid request.'}, status=400)

    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Empty.'}, status=400)

    comment = Comment.objects.create(user=request.user, post=post, text=text)
    if post.user_id != request.user.id:
        Notification.objects.create(user=post.user, sender=request.user, notif_type='comment')

    html = render_to_string('partials/_comment.html', {'comment': comment}, request=request)
    return JsonResponse({'ok': True, 'html': html, 'total': post.comments.count()})


@login_required
def profile(request, username):
    profile_user = get_object_or_404(User, username__iexact=username)

    i_blocked_them = BlockList.objects.filter(blocker=request.user, blocked=profile_user).exists()
    they_blocked_me = BlockList.objects.filter(blocker=profile_user, blocked=request.user).exists()
    is_blocked = i_blocked_them or they_blocked_me

    friendship = Friendship.objects.filter(
        Q(user=request.user, friend=profile_user) |
        Q(user=profile_user, friend=request.user)
    ).first()

    is_friend = friendship is not None and friendship.status == 'accepted'
    is_self = request.user == profile_user

    # Private account logic
    can_see_posts = is_self or is_friend or (not profile_user.is_private)

    if is_blocked or not can_see_posts:
        posts = Post.objects.none()
    else:
        posts = Post.objects.filter(user=profile_user).order_by('-created_at')

    photo_posts = posts.filter(image__isnull=False).exclude(image='')
    video_posts = posts.filter(video__isnull=False).exclude(video='')

    friend_relations = Friendship.objects.filter(
        Q(user=profile_user, status='accepted') | Q(friend=profile_user, status='accepted')
    ).select_related('user', 'friend')
    friends_list = [rel.friend if rel.user == profile_user else rel.user for rel in friend_relations]

    return render(request, 'profile.html', {
        'nav_active': 'profile',
        'profile_user': profile_user,
        'posts': posts,
        'photo_posts': photo_posts,
        'video_posts': video_posts,
        'friends': friends_list,
        'friend_count': len(friends_list),
        'friendship': friendship,
        'is_friend': is_friend,
        'is_own_profile': is_self,
        'is_blocked': is_blocked,
        'i_blocked_them': i_blocked_them,
        'they_blocked_me': they_blocked_me,
        'can_see_posts': can_see_posts,
    })


@login_required
@require_POST
def unfriend(request, username):
    """Remove friendship. Does NOT block. Posts remain visible."""
    target = get_object_or_404(User, username__iexact=username)

    if target == request.user:
        return JsonResponse({'ok': False, 'error': 'Invalid.'}, status=400)

    deleted_count, _ = Friendship.objects.filter(
        Q(user=request.user, friend=target) | Q(user=target, friend=request.user)
    ).delete()

    if deleted_count == 0:
        return JsonResponse({'ok': False, 'error': 'Not friends.'}, status=400)

    return JsonResponse({'ok': True})


@login_required
def edit_profile(request):
    if request.method == 'POST':
        u = request.user
        u.full_name = request.POST.get('full_name', u.full_name)
        u.email = request.POST.get('email', u.email)
        u.phone = request.POST.get('phone', u.phone)
        u.gender = request.POST.get('gender', u.gender)
        u.is_private = request.POST.get('is_private') == 'on'

        dob_str = request.POST.get('dob')
        if dob_str:
            try:
                u.dob = date.fromisoformat(dob_str)
            except ValueError:
                pass

        if 'profile_pic' in request.FILES:
            u.profile_pic = request.FILES['profile_pic']
        if 'banner' in request.FILES:
            u.banner = request.FILES['banner']

        u.save()
        messages.success(request, "Profile updated successfully!")
        return redirect('profile', username=u.username)

    return render(request, 'edit_profile.html', {'nav_active': 'profile'})


@login_required
@require_POST
def toggle_block(request, username):
    target = get_object_or_404(User, username__iexact=username)

    if target == request.user:
        return JsonResponse({'ok': False, 'error': 'You cannot block yourself.'}, status=400)

    existing = BlockList.objects.filter(blocker=request.user, blocked=target).first()

    if existing:
        existing.delete()
        return JsonResponse({'ok': True, 'blocked': False, 'message': 'User unblocked.'})
    else:
        BlockList.objects.create(blocker=request.user, blocked=target)
        Friendship.objects.filter(
            Q(user=request.user, friend=target) | Q(user=target, friend=request.user)
        ).delete()
        return JsonResponse({'ok': True, 'blocked': True, 'message': 'User blocked.'})


# ============================================================
# FRIENDS & REQUESTS
# ============================================================
@login_required
def friends(request):
    relations = Friendship.objects.filter(
        Q(user=request.user, status='accepted') | Q(friend=request.user, status='accepted')
    ).select_related('user', 'friend')

    all_friends = [rel.friend if rel.user == request.user else rel.user for rel in relations]
    all_friends.sort(key=lambda u: (u.full_name or u.username).lower())

    online_friends = [f for f in all_friends if f.active_status]
    offline_friends = [f for f in all_friends if not f.active_status]

    blocked_users = BlockList.objects.filter(blocker=request.user).select_related('blocked')
    blocked_list = [b.blocked for b in blocked_users]

    return render(request, 'friends.html', {
        'nav_active': 'friends',
        'all_friends': all_friends,
        'online_friends': online_friends,
        'offline_friends': offline_friends,
        'blocked_users': blocked_list,
        'total_friends': len(all_friends),
        'online_count': len(online_friends),
        'offline_count': len(offline_friends),
        'blocked_count': len(blocked_list),
    })


@login_required
def friend_requests(request):
    incoming = Friendship.objects.filter(friend=request.user, status='pending').select_related('user')
    outgoing = Friendship.objects.filter(user=request.user, status='pending').select_related('friend')
    return render(request, 'friend_requests.html', {
        'nav_active': 'requests',
        'incoming': incoming,
        'outgoing': outgoing,
    })


@login_required
@require_POST
def send_friend_request(request, username):
    target = get_object_or_404(User, username__iexact=username)

    if target == request.user:
        return JsonResponse({'ok': False, 'error': 'You cannot add yourself.'}, status=400)

    if BlockList.objects.filter(
        Q(blocker=request.user, blocked=target) | Q(blocker=target, blocked=request.user)
    ).exists():
        return JsonResponse({'ok': False, 'error': 'This user is blocked.'}, status=400)

    existing = Friendship.objects.filter(
        Q(user=request.user, friend=target) | Q(user=target, friend=request.user)
    ).first()

    if existing:
        if existing.status == 'accepted':
            return JsonResponse({'ok': False, 'error': 'Already friends.'}, status=400)
        return JsonResponse({'ok': False, 'error': 'Request already exists.'}, status=400)

    Friendship.objects.create(user=request.user, friend=target, status='pending')
    Notification.objects.create(user=target, sender=request.user, notif_type='friend_req')
    return JsonResponse({'ok': True})


@login_required
@require_POST
def accept_friend_request(request, request_id):
    friendship = get_object_or_404(Friendship, id=request_id, friend=request.user, status='pending')
    friendship.status = 'accepted'
    friendship.save()

    Notification.objects.create(user=friendship.user, sender=request.user, notif_type='friend_accept')
    return JsonResponse({'ok': True})


@login_required
@require_POST
def reject_friend_request(request, request_id):
    friendship = get_object_or_404(Friendship, id=request_id, friend=request.user, status='pending')
    friendship.delete()
    return JsonResponse({'ok': True})


# ============================================================
# NOTIFICATIONS & SEARCH
# ============================================================
@login_required
def notifications(request):
    notifs = Notification.objects.filter(user=request.user).select_related('sender').order_by('-created_at')

    unread_ids = list(notifs.filter(is_read=False).values_list('id', flat=True))
    if unread_ids:
        Notification.objects.filter(id__in=unread_ids).update(is_read=True)

    for n in notifs:
        if n.notif_type == 'friend_req':
            n.target_url = reverse('friend_requests'); n.message = "sent you a friend request."
        elif n.notif_type == 'friend_accept':
            n.target_url = reverse('profile', kwargs={'username': n.sender.username}); n.message = "accepted your friend request."
        elif n.notif_type == 'like':
            n.target_url = reverse('profile', kwargs={'username': n.sender.username}) + "?tab=posts"; n.message = "liked your post."
        elif n.notif_type == 'comment':
            n.target_url = reverse('profile', kwargs={'username': n.sender.username}) + "?tab=posts"; n.message = "commented on your post."
        elif n.notif_type == 'message':
            n.target_url = reverse('messages'); n.message = "sent you a message."
        else:
            n.target_url = '#'; n.message = "did something."

    return render(request, 'notifications.html', {
        'nav_active': 'notifications',
        'notifications': notifs,
        'unread_ids': unread_ids,
    })


@login_required
def search(request):
    q = (request.GET.get('q') or '').strip()
    results = []

    if q:
        blocked_ids = BlockList.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
        blocked_by_ids = BlockList.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
        excluded = set(blocked_ids) | set(blocked_by_ids)

        matches = (
            User.objects
            .filter(Q(username__icontains=q) | Q(full_name__icontains=q))
            .exclude(id=request.user.id)
            .exclude(id__in=excluded)
            .order_by('full_name', 'username')[:30]
        )

        my_friend_ids = set()
        for f in Friendship.objects.filter(
            Q(user=request.user, status='accepted') | Q(friend=request.user, status='accepted')
        ):
            my_friend_ids.add(f.friend_id if f.user_id == request.user.id else f.user_id)

        sent_pending = set(
            Friendship.objects.filter(user=request.user, status='pending').values_list('friend_id', flat=True)
        )

        for u in matches:
            if u.id in my_friend_ids:
                status = 'friend'
            elif u.id in sent_pending:
                status = 'pending'
            else:
                status = 'none'
            results.append({'user': u, 'status': status})

    return render(request, 'search.html', {
        'nav_active': 'search',
        'query': q,
        'results': results,
        'result_count': len(results),
    })


# ============================================================
# MESSAGES
# ============================================================
@login_required
def messages_list(request):
    memberships = ChatMember.objects.filter(user=request.user).select_related('chat').order_by('-is_pinned', '-joined_at')

    chats_data = []
    for m in memberships:
        chat = m.chat
        last_msg = chat.messages.filter(deleted=False).last()
        unread = chat.messages.filter(is_read=False).exclude(sender=request.user).count()

        if chat.chat_type == 'direct':
            other = ChatMember.objects.filter(chat=chat).exclude(user=request.user).select_related('user').first()
            display_name = other.user.full_name if other and other.user.full_name else (other.user.username if other else 'Unknown')
            other_user = other.user if other else None
            avatar_url = other_user.profile_pic.url if (other_user and other_user.profile_pic and other_user.profile_pic.name != 'profiles/default.png') else None
            initial = other_user.username[0].upper() if other_user else '?'
            online = other_user.active_status if other_user else False
        else:
            display_name = chat.name or 'Group'
            other_user = None
            avatar_url = chat.avatar.url if chat.avatar else None
            initial = (chat.name or 'G')[0].upper()
            online = False

        chats_data.append({
            'id': chat.id, 'name': display_name, 'initial': initial, 'avatar_url': avatar_url,
            'online': online,
            'last_message': last_msg.text[:40] if last_msg and last_msg.text else (f"[{last_msg.message_type}]" if last_msg else 'No messages yet'),
            'last_time': last_msg.timestamp if last_msg else chat.created_at,
            'unread': unread, 'is_muted': m.is_muted, 'is_pinned': m.is_pinned,
            'is_archived': m.is_archived, 'is_favourite': m.is_favourite,
            'is_locked': m.is_locked, 'is_group': chat.chat_type == 'group',
        })

    friendships = Friendship.objects.filter(
        Q(user=request.user, status='accepted') | Q(friend=request.user, status='accepted')
    ).select_related('user', 'friend')
    friends_for_chat = [f.friend if f.user == request.user else f.user for f in friendships]
    friends_for_chat.sort(key=lambda u: (u.full_name or u.username).lower())

    online_friends = [f for f in friends_for_chat if f.active_status][:15]

    return render(request, 'messages.html', {
        'nav_active': 'messages',
        'chats': chats_data,
        'online_friends': online_friends,
        'friends_for_chat': friends_for_chat,
        'active_chat_id': None,
    })


@login_required
def chat_view(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    membership = ChatMember.objects.filter(chat=chat, user=request.user).first()
    if not membership:
        return HttpResponseForbidden("You are not a member of this chat.")

    memberships = ChatMember.objects.filter(user=request.user).select_related('chat').order_by('-is_pinned', '-joined_at')
    chats_data = []
    for m in memberships:
        c = m.chat
        last_msg = c.messages.filter(deleted=False).last()
        unread = c.messages.filter(is_read=False).exclude(sender=request.user).count()
        if c.chat_type == 'direct':
            other = ChatMember.objects.filter(chat=c).exclude(user=request.user).select_related('user').first()
            dn = other.user.full_name if other and other.user.full_name else (other.user.username if other else 'Unknown')
            ou = other.user if other else None
            av = ou.profile_pic.url if (ou and ou.profile_pic and ou.profile_pic.name != 'profiles/default.png') else None
            ini = ou.username[0].upper() if ou else '?'
            on = ou.active_status if ou else False
        else:
            dn = c.name or 'Group'; ou = None
            av = c.avatar.url if c.avatar else None
            ini = (c.name or 'G')[0].upper(); on = False
        chats_data.append({
            'id': c.id, 'name': dn, 'initial': ini, 'avatar_url': av, 'online': on,
            'last_message': last_msg.text[:40] if last_msg and last_msg.text else (f"[{last_msg.message_type}]" if last_msg else 'No messages yet'),
            'last_time': last_msg.timestamp if last_msg else c.created_at,
            'unread': unread, 'is_muted': m.is_muted, 'is_pinned': m.is_pinned,
            'is_archived': m.is_archived, 'is_favourite': m.is_favourite,
            'is_locked': m.is_locked, 'is_group': c.chat_type == 'group',
        })

    if chat.chat_type == 'direct':
        other = ChatMember.objects.filter(chat=chat).exclude(user=request.user).select_related('user').first()
        other_user = other.user if other else None
        header_name = other_user.full_name if other_user and other_user.full_name else (other_user.username if other_user else 'Unknown')
        header_avatar = other_user.profile_pic.url if (other_user and other_user.profile_pic and other_user.profile_pic.name != 'profiles/default.png') else None
        header_initial = other_user.username[0].upper() if other_user else '?'
        header_online = other_user.active_status if other_user else False
        header_id = other_user.id if other_user else None
    else:
        header_name = chat.name or 'Group'
        header_avatar = chat.avatar.url if chat.avatar else None
        header_initial = (chat.name or 'G')[0].upper()
        header_online = False
        header_id = None

    msgs_qs = chat.messages.filter(deleted=False).select_related('sender').prefetch_related('reactions')
    if membership.cleared_at:
        msgs_qs = msgs_qs.filter(timestamp__gt=membership.cleared_at)
    msgs = list(msgs_qs)

    chat.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    friendships = Friendship.objects.filter(
        Q(user=request.user, status='accepted') | Q(friend=request.user, status='accepted')
    ).select_related('user', 'friend')
    friends_for_chat = [f.friend if f.user == request.user else f.user for f in friendships]
    friends_for_chat.sort(key=lambda u: (u.full_name or u.username).lower())

    return render(request, 'chat.html', {
        'nav_active': 'messages',
        'chats': chats_data,
        'chat': chat,
        'membership': membership,
        'messages': msgs,
        'header_name': header_name,
        'header_avatar': header_avatar,
        'header_initial': header_initial,
        'header_online': header_online,
        'header_id': header_id,
        'active_chat_id': chat.id,
        'friends_for_chat': friends_for_chat,
    })


@login_required
@require_POST
def start_new_chat(request):
    username = request.POST.get('username', '').strip()
    if not username:
        return JsonResponse({'ok': False, 'error': 'No user provided.'}, status=400)

    target = User.objects.filter(username__iexact=username).first()
    if not target or target == request.user:
        return JsonResponse({'ok': False, 'error': 'User not found.'}, status=400)

    if BlockList.objects.filter(Q(blocker=request.user, blocked=target) | Q(blocker=target, blocked=request.user)).exists():
        return JsonResponse({'ok': False, 'error': 'This user is blocked.'}, status=400)

    my_chats = ChatMember.objects.filter(user=request.user).values_list('chat_id', flat=True)
    existing = ChatMember.objects.filter(user=target, chat_id__in=my_chats, chat__chat_type='direct').first()
    if existing:
        return JsonResponse({'ok': True, 'chat_id': existing.chat_id})

    chat = Chat.objects.create(chat_type='direct', created_by=request.user)
    ChatMember.objects.create(chat=chat, user=request.user)
    ChatMember.objects.create(chat=chat, user=target)
    return JsonResponse({'ok': True, 'chat_id': chat.id})


@login_required
@require_POST
def create_group(request):
    name = request.POST.get('name', '').strip()
    usernames = request.POST.getlist('members[]')
    avatar = request.FILES.get('avatar')

    if not name:
        return JsonResponse({'ok': False, 'error': 'Group name required.'}, status=400)
    if not usernames:
        return JsonResponse({'ok': False, 'error': 'Add at least one member.'}, status=400)

    chat = Chat.objects.create(chat_type='group', name=name, avatar=avatar, created_by=request.user)
    ChatMember.objects.create(chat=chat, user=request.user, is_admin=True)

    added = 0
    for uname in usernames:
        u = User.objects.filter(username__iexact=uname).first()
        if u and u != request.user:
            ChatMember.objects.get_or_create(chat=chat, user=u)
            added += 1

    if added == 0:
        chat.delete()
        return JsonResponse({'ok': False, 'error': 'No valid members.'}, status=400)

    return JsonResponse({'ok': True, 'chat_id': chat.id})


@login_required
@require_POST
def send_message(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    if not ChatMember.objects.filter(chat=chat, user=request.user).exists():
        return HttpResponseForbidden()

    text = (request.POST.get('text') or '').strip()
    msg_type = request.POST.get('type', 'text')
    file = request.FILES.get('file')

    if not text and not file and msg_type != 'sticker':
        return JsonResponse({'ok': False, 'error': 'Empty message.'}, status=400)

    msg = Message.objects.create(
        chat=chat, sender=request.user,
        text=text or None,
        message_type=msg_type,
        attachment=file if file else None,
    )

    TypingStatus.objects.filter(chat=chat, user=request.user).delete()

    for member in ChatMember.objects.filter(chat=chat).exclude(user=request.user):
        Notification.objects.create(user=member.user, sender=request.user, notif_type='message')

    return JsonResponse({
        'ok': True,
        'message_id': msg.id,
        'html': render_to_string('partials/_message_bubble.html', {'msg': msg}, request=request),
    })


@login_required
@require_GET
def fetch_messages(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    if not ChatMember.objects.filter(chat=chat, user=request.user).exists():
        return HttpResponseForbidden()

    since = request.GET.get('since')
    qs = chat.messages.filter(deleted=False).select_related('sender').prefetch_related('reactions')
    if since:
        try:
            since_dt = parse_datetime(since)
            if since_dt:
                qs = qs.filter(timestamp__gt=since_dt)
        except Exception:
            pass

    out = []
    for m in qs:
        out.append({
            'id': m.id,
            'html': render_to_string('partials/_message_bubble.html', {'msg': m}, request=request),
        })

    chat.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    return JsonResponse({'ok': True, 'messages': out})


@login_required
@require_POST
def set_typing(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    if not ChatMember.objects.filter(chat=chat, user=request.user).exists():
        return HttpResponseForbidden()
    TypingStatus.objects.update_or_create(chat=chat, user=request.user)
    return JsonResponse({'ok': True})


@login_required
@require_GET
def get_typing(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    cutoff = timezone.now() - timedelta(seconds=5)
    typers = TypingStatus.objects.filter(chat=chat, updated_at__gte=cutoff).exclude(user=request.user).select_related('user')
    names = [t.user.full_name or t.user.username for t in typers]
    return JsonResponse({'ok': True, 'typing': names})


@login_required
@require_POST
def chat_action(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    membership = ChatMember.objects.filter(chat=chat, user=request.user).first()
    if not membership:
        return HttpResponseForbidden()

    action = request.POST.get('action')
    code = request.POST.get('code', '')

    if action == 'mute': membership.is_muted = not membership.is_muted
    elif action == 'pin': membership.is_pinned = not membership.is_pinned
    elif action == 'archive': membership.is_archived = not membership.is_archived
    elif action == 'favourite': membership.is_favourite = not membership.is_favourite
    elif action == 'lock':
        if membership.is_locked:
            membership.is_locked = False
            membership.lock_code = ''
        else:
            if not code:
                return JsonResponse({'ok': False, 'error': 'Set a lock code.'}, status=400)
            membership.is_locked = True
            membership.lock_code = code
    else:
        return JsonResponse({'ok': False, 'error': 'Unknown action.'}, status=400)

    membership.save()
    return JsonResponse({'ok': True, 'state': {
        'is_muted': membership.is_muted, 'is_pinned': membership.is_pinned,
        'is_archived': membership.is_archived, 'is_favourite': membership.is_favourite,
        'is_locked': membership.is_locked,
    }})


@login_required
@require_POST
def delete_chat(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    membership = ChatMember.objects.filter(chat=chat, user=request.user).first()
    if not membership:
        return HttpResponseForbidden()
    membership.cleared_at = timezone.now()
    membership.save()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def unlock_chat(request, chat_id):
    chat = get_object_or_404(Chat, id=chat_id)
    membership = ChatMember.objects.filter(chat=chat, user=request.user).first()
    if not membership:
        return HttpResponseForbidden()
    code = request.POST.get('code', '')
    if code == membership.lock_code:
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False, 'error': 'Wrong code.'}, status=400)


@login_required
@require_POST
def upload_sticker(request):
    img = request.FILES.get('image')
    if not img:
        return JsonResponse({'ok': False, 'error': 'No image.'}, status=400)
    s = Sticker.objects.create(user=request.user, image=img, name=request.POST.get('name', ''))
    return JsonResponse({'ok': True, 'url': s.image.url, 'id': s.id})


@login_required
@require_GET
def list_stickers(request):
    stickers = Sticker.objects.filter(user=request.user)
    return JsonResponse({'ok': True, 'stickers': [{'id': s.id, 'url': s.image.url, 'name': s.name} for s in stickers]})


# ============================================================
# SETTINGS
# ============================================================
@login_required
def settings(request):
    blocked = BlockList.objects.filter(blocker=request.user).select_related('blocked')
    return render(request, 'settings.html', {
        'nav_active': 'settings',
        'blocked_users': [b.blocked for b in blocked],
    })


@login_required
@require_POST
def toggle_active_status(request):
    request.user.active_status = not request.user.active_status
    request.user.save()
    return JsonResponse({'ok': True, 'active_status': request.user.active_status})


@login_required
@require_POST
def submit_support(request):
    subject = (request.POST.get('subject') or '').strip()
    message = (request.POST.get('message') or '').strip()

    if not subject or not message:
        return JsonResponse({'ok': False, 'error': 'Both fields are required.'}, status=400)

    SupportTicket.objects.create(user=request.user, subject=subject, message=message)
    return JsonResponse({'ok': True, 'message': 'Ticket submitted. We will get back to you shortly.'})


@login_required
@require_POST
def deactivate_account(request):
    request.user.is_deactivated = True
    request.user.deactivated_at = timezone.now()
    request.user.active_status = False
    request.user.save()
    logout(request)
    messages.success(request, "Your account has been deactivated. Log in again to reactivate.")
    return redirect('login')


def reactivate_account(request):
    user_id = request.session.get('pending_reactivation_user')
    if not user_id:
        return redirect('login')
    try:
        u = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    if request.method == 'POST' and request.POST.get('password'):
        if u.check_password(request.POST['password']):
            u.is_deactivated = False
            u.deactivated_at = None
            u.save()
            login(request, u)
            request.session.pop('pending_reactivation_user', None)
            messages.success(request, "Account reactivated. Welcome back!")
            return redirect('home')
        messages.error(request, "Wrong password.")

    return render(request, 'auth/reactivate.html', {'pending_user': u})


@login_required
@require_POST
def delete_account(request):
    password = request.POST.get('password', '')
    if not request.user.check_password(password):
        messages.error(request, "Incorrect password. Account not deleted.")
        return redirect('settings')

    user = request.user
    logout(request)
    user.delete()
    messages.success(request, "Your account has been permanently deleted.")
    return redirect('login')


# ============================================================
# PDF DOWNLOADS
# ============================================================
@login_required
def download_account_info(request):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    c.setFont('Helvetica-Bold', 18)
    c.drawString(2 * cm, y, "Connect — Account Information")
    y -= cm
    c.setFont('Helvetica', 10)
    c.drawString(2 * cm, y, f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
    y -= cm

    u = request.user
    fields = [
        ('Username', u.username),
        ('Full Name', u.full_name or '—'),
        ('Email', u.email or '—'),
        ('Phone', u.phone or '—'),
        ('Gender', u.get_gender_display() if u.gender else '—'),
        ('Date of Birth', u.dob.strftime('%Y-%m-%d') if u.dob else '—'),
        ('Private Account', 'Yes' if u.is_private else 'No'),
        ('Active Status', 'On' if u.active_status else 'Off'),
        ('Date Joined', u.date_joined.strftime('%Y-%m-%d')),
        ('Posts', Post.objects.filter(user=u).count()),
        ('Friends', Friendship.objects.filter(Q(user=u, status='accepted') | Q(friend=u, status='accepted')).count()),
        ('Messages Sent', Message.objects.filter(sender=u).count()),
    ]

    c.setFont('Helvetica-Bold', 12)
    c.drawString(2 * cm, y, "Profile")
    y -= 0.6 * cm
    c.setFont('Helvetica', 11)
    for label, value in fields:
        c.drawString(2 * cm, y, f"{label}:")
        c.drawString(6 * cm, y, str(value))
        y -= 0.55 * cm
        if y < 3 * cm:
            c.showPage()
            y = height - 2 * cm

    c.save()
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="connect_account_{u.username}.pdf"'
    return response


@login_required
def download_chat_history(request):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 2 * cm

    c.setFont('Helvetica-Bold', 18)
    c.drawString(2 * cm, y, "Connect — Chat History")
    y -= cm
    c.setFont('Helvetica', 10)
    c.drawString(2 * cm, y, f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
    y -= cm

    memberships = ChatMember.objects.filter(user=request.user).select_related('chat')
    any_message = False

    for m in memberships:
        chat = m.chat
        messages = chat.messages.filter(deleted=False).select_related('sender').order_by('timestamp')
        if not messages.exists():
            continue
        any_message = True

        if chat.chat_type == 'direct':
            other = ChatMember.objects.filter(chat=chat).exclude(user=request.user).select_related('user').first()
            header = f"Chat with {other.user.full_name or other.user.username}" if other else "Direct Chat"
        else:
            header = f"Group: {chat.name or 'Untitled'}"

        c.setFont('Helvetica-Bold', 12)
        c.drawString(2 * cm, y, header)
        y -= 0.5 * cm
        c.setFont('Helvetica', 9)
        c.drawString(2 * cm, y, f"Chat ID: {chat.id}")
        y -= 0.7 * cm

        c.setFont('Helvetica', 10)
        for msg in messages:
            prefix = "Me" if msg.sender == request.user else msg.sender.username
            time_str = msg.timestamp.strftime('%Y-%m-%d %H:%M')
            text = msg.text or f"[{msg.message_type}]"
            line = f"[{time_str}] {prefix}: {text}"

            while len(line) > 95:
                c.drawString(2 * cm, y, line[:95])
                line = line[95:]
                y -= 0.45 * cm
                if y < 3 * cm:
                    c.showPage(); y = height - 2 * cm
            c.drawString(2 * cm, y, line)
            y -= 0.45 * cm
            if y < 3 * cm:
                c.showPage(); y = height - 2 * cm

        y -= 0.5 * cm
        if y < 3 * cm:
            c.showPage(); y = height - 2 * cm

    if not any_message:
        c.setFont('Helvetica-Oblique', 11)
        c.drawString(2 * cm, y, "No messages found.")

    c.save()
    buf.seek(0)
    response = HttpResponse(buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="connect_chats_{request.user.username}.pdf"'
    return response
