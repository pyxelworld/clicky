import os
import datetime
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required, logout_user
from jinja2 import BaseLoader, TemplateNotFound
from sqlalchemy.orm import joinedload

# --- APP CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-persistent-and-secure-key'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB limit

# --- INITIALIZE EXTENSIONS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.remember_cookie_duration = datetime.timedelta(days=30) # Persistent login for 30 days
login_manager.session_protection = "strong"

# --- SVG ICONS DICTIONARY ---
ICONS = {
    'home': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    'discover': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    'create': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>',
    'profile': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    'like': '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    'comment': '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    'repost': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
    'send': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>'
}
app.jinja_env.globals.update(ICONS=ICONS)


# --- TEMPLATES (v3 - Flat/Glassmorphism UI) ---
templates = {
"layout.html": """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, user-scalable=no">
    <title>{% block title %}Sixsec{% endblock %}</title>
    <style>
        :root {
            --bg-color: #000000;
            --card-color: #16181C;
            --primary-text: #E7E9EA;
            --secondary-text: #71767B;
            --accent: #00BA7C; /* A more subtle, modern teal */
            --border-color: #2F3336;
            --glass-bg: rgba(22, 24, 28, 0.85);
            --like-red: #f91880;
        }
        html { -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0; 
            background-color: var(--bg-color); 
            color: var(--primary-text); 
            font-size: 16px;
        }
        .container { max-width: 600px; margin: 0 auto; padding-top: 55px; padding-bottom: 70px; }
        a { color: var(--accent); text-decoration: none; }
        
        /* Glassmorphism Navigation */
        .glass-nav {
            position: fixed; z-index: 1000;
            background: var(--glass-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            width: 100%;
            max-width: 600px; /* Match container */
            left: 50%;
            transform: translateX(-50%);
        }
        .top-bar {
            top: 0;
            padding: 10px 15px;
            border-bottom: 1px solid var(--border-color);
            display: flex; justify-content: center; align-items: center; height: 53px; box-sizing: border-box;
        }
        .top-bar .logo {
            font-weight: bold; font-size: 1.8em; color: var(--primary-text);
        }
        .bottom-nav { 
            bottom: 0;
            border-top: 1px solid var(--border-color);
            display: flex; justify-content: space-around;
            padding: 10px 0;
        }
        .bottom-nav a { 
            color: var(--secondary-text); 
            transition: color 0.2s ease, transform 0.2s ease; 
        }
        .bottom-nav a.active { 
            color: var(--primary-text);
        }
        .bottom-nav a svg { width: 28px; height: 28px; }

        /* Flat Card Style (Twitter-like) */
        .post-card {
            border-bottom: 1px solid var(--border-color);
            padding: 15px;
            display: flex;
            gap: 12px;
        }
        .pfp-container { flex-shrink: 0; }
        .pfp { width: 45px; height: 45px; border-radius: 50%; object-fit: cover; background-color: var(--secondary-text); }
        .pfp-placeholder { display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 1.2rem; }
        .post-body { flex-grow: 1; }
        .post-header { display: flex; align-items: center; gap: 8px; }
        .post-header .username { font-weight: bold; }
        .post-header .timestamp { font-size: 0.9em; color: var(--secondary-text); }
        .post-content p { white-space: pre-wrap; word-wrap: break-word; line-height: 1.5; margin: 5px 0 12px 0; }
        
        .post-actions { display: flex; justify-content: space-between; max-width: 425px; }
        .post-actions button { background: none; border: none; cursor: pointer; color: var(--secondary-text); display: flex; align-items: center; gap: 8px; font-size: 0.85em; transition: color 0.2s ease; }
        .post-actions button:hover { color: var(--accent); }
        .post-actions .like-btn:hover { color: var(--like-red); }
        .post-actions .like-btn.liked { color: var(--like-red); fill: var(--like-red); }
        .post-actions svg { width: 18px; height: 18px; }

        /* Forms & Buttons */
        .btn {
            background-color: var(--primary-text); color: var(--bg-color);
            padding: 10px 20px; border: none; border-radius: 30px;
            cursor: pointer; font-weight: bold; font-size: 1rem;
            transition: background-color 0.2s ease;
        }
        .btn:hover { background-color: #d1d3d4; }
        .btn-danger { background-color: #cf2323; color: white; }
        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: .5rem; color: var(--secondary-text); }
        .form-group input, .form-group textarea {
            width: 100%; padding: 12px; border: 1px solid var(--border-color); border-radius: 8px;
            background: transparent; color: var(--primary-text); box-sizing: border-box; font-size: 1rem;
        }
        .form-group input:focus, .form-group textarea:focus { outline: 2px solid var(--accent); border-color: var(--accent); }
        
        /* Modal for Comments */
        .modal {
            display: none; position: fixed; z-index: 2000; left: 0; top: 0;
            width: 100%; height: 100%; overflow: auto; background-color: rgba(91, 112, 131, 0.4);
            align-items: flex-end;
        }
        .modal-content {
            background-color: var(--bg-color); margin: auto auto 0 auto; border-radius: 20px 20px 0 0;
            width: 100%; max-width: 600px; height: 75vh;
            display: flex; flex-direction: column; animation: slideUp 0.3s ease;
        }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        .modal-header { padding: 15px; border-bottom: 1px solid var(--border-color); text-align: center; position: relative; }
        .modal-header .close { position: absolute; left: 15px; top: 10px; font-size: 24px; font-weight: bold; cursor: pointer; color: var(--primary-text); }
        .modal-body { flex-grow: 1; overflow-y: auto; }
        .modal-footer { padding: 10px; border-top: 1px solid var(--border-color); }
        .comment-form { display: flex; gap: 10px; }

        /* General Feed styles */
        .feed-nav { display: flex; border-bottom: 1px solid var(--border-color); }
        .feed-nav a { flex: 1; text-align: center; padding: 15px; color: var(--secondary-text); font-weight: bold; position: relative; }
        .feed-nav a.active { color: var(--primary-text); }
        .feed-nav a.active::after { content: ''; position: absolute; bottom: 0; left: 50%; transform: translateX(-50%); width: 60px; height: 4px; background: var(--accent); border-radius: 2px; }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
    {% if not full_screen_mode %}
    <header class="glass-nav top-bar">
        <div class="logo">Sixsec</div>
    </header>
    {% endif %}
    
    <main class="{% if not full_screen_mode %}container{% endif %}">
        {% block content %}{% endblock %}
    </main>

    {% if current_user.is_authenticated and not full_screen_mode %}
    <nav class="glass-nav bottom-nav">
        <a href="{{ url_for('home') }}" class="{{ 'active' if request.endpoint == 'home' else '' }}">{{ ICONS.home|safe }}</a>
        <a href="{{ url_for('discover') }}" class="{{ 'active' if request.endpoint == 'discover' else '' }}">{{ ICONS.discover|safe }}</a>
        <a href="{{ url_for('create_post') }}" class="{{ 'active' if request.endpoint == 'create_post' else '' }}">{{ ICONS.create|safe }}</a>
        <a href="{{ url_for('profile', username=current_user.username) }}" class="{{ 'active' if request.endpoint == 'profile' else '' }}">{{ ICONS.profile|safe }}</a>
    </nav>
    {% endif %}

    <div id="commentModal" class="modal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="close" onclick="closeCommentModal()">×</span>
          <h4>Comments</h4>
        </div>
        <div class="modal-body" id="comment-list"></div>
        <div class="modal-footer">
          <form id="comment-form" class="comment-form" onsubmit="handleCommentSubmit(event)">
            <input type="text" id="comment-text-input" class="form-group" placeholder="Post your reply" required style="margin:0;">
            <input type="hidden" id="comment-post-id">
            <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
          </form>
        </div>
      </div>
    </div>
    
    <script>
    // JS functions for modals, likes, comments are placed here for single-file simplicity
    const commentModal = document.getElementById('commentModal');
    
    async function openCommentModal(postId) {
        document.getElementById('comment-post-id').value = postId;
        const commentList = document.getElementById('comment-list');
        commentList.innerHTML = '<p style="text-align:center; padding: 20px; color: var(--secondary-text);">Loading...</p>';
        commentModal.style.display = 'flex';
        
        const response = await fetch(`/post/${postId}/comments`);
        const comments = await response.json();
        
        commentList.innerHTML = '';
        if (comments.length === 0) {
            commentList.innerHTML = '<p style="text-align:center; padding: 20px; color: var(--secondary-text);">No comments yet. Be the first!</p>';
        } else {
            comments.forEach(comment => {
                const div = document.createElement('div');
                div.className = 'post-card';
                div.innerHTML = `<div class="pfp-container"><div class="pfp pfp-placeholder" style="background-color:${comment.user.pfp_bg};">${comment.user.initial}</div></div>
                                 <div class="post-body">
                                     <div class="post-header"><span class="username">${comment.user.username}</span><span class="timestamp">${comment.timestamp}</span></div>
                                     <div class="post-content"><p>${comment.text}</p></div>
                                 </div>`;
                commentList.appendChild(div);
            });
        }
    }

    function closeCommentModal() {
        commentModal.style.display = 'none';
    }

    async function handleCommentSubmit(e) {
        e.preventDefault();
        const postId = document.getElementById('comment-post-id').value;
        const textInput = document.getElementById('comment-text-input');
        
        const response = await fetch(`/post/${postId}/comment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: textInput.value })
        });
        
        if (response.ok) {
            textInput.value = '';
            openCommentModal(postId); // Refresh
        } else {
            alert('Failed to post comment.');
        }
    };

    async function handleLike(postId, context) {
        const url = `/like/${postId}`;
        const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const data = await response.json();
        
        const likeButtons = document.querySelectorAll(`.like-btn-${postId}`);
        const likeCounts = document.querySelectorAll(`.like-count-${postId}`);
        
        likeButtons.forEach(btn => btn.classList.toggle('liked', data.liked));
        likeCounts.forEach(count => count.innerText = data.likes);
    }
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
""",

"post_card.html": """
<div class="post-card" id="post-{{ post.id }}">
    <div class="pfp-container">
        <a href="{{ url_for('profile', username=post.author.username) }}">
            {% if post.author.profile_pic and post.author.profile_pic != 'default.png' %}
                <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}" alt="pfp">
            {% else %}
                <div class="pfp pfp-placeholder" style="background-color:{{ post.author.pfp_bg }};">{{ post.author.username[0]|upper }}</div>
            {% endif %}
        </a>
    </div>
    <div class="post-body">
        <div class="post-header">
            <a href="{{ url_for('profile', username=post.author.username) }}" class="username">{{ post.author.username }}</a>
            <span class="timestamp">· {{ post.timestamp.strftime('%b %d') }}</span>
        </div>
        <div class="post-content">
            <p>{{ post.text_content }}</p>
        </div>
        <div class="post-actions">
            <button onclick="openCommentModal({{ post.id }})">
                {{ ICONS.comment|safe }} <span>{{ post.comments.count() }}</span>
            </button>
            <button>
                {{ ICONS.repost|safe }} <span>0</span>
            </button>
            <button class="like-btn like-btn-{{ post.id }} {{ 'liked' if current_user in post.liked_by else '' }}" onclick="handleLike({{ post.id }})">
                {{ ICONS.like|safe }} <span class="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
            </button>
        </div>
    </div>
</div>
""",

"home.html": """
{% extends "layout.html" %}
{% block content %}
    <div class="feed-nav">
        <a href="{{ url_for('home', feed_type='text') }}" class="{{ 'active' if feed_type == 'text' }}">For You</a>
        <a href="{{ url_for('home', feed_type='sixs') }}" class="{{ 'active' if feed_type == 'sixs' }}">Sixs</a>
    </div>
    <div class="posts-container">
    {% for post in posts %}
        {% include 'post_card.html' %}
    {% else %}
        <div style="text-align:center; padding: 40px; color: var(--secondary-text);">
            <h3>Welcome to Sixsec!</h3>
            <p>Your feed is empty. Follow some accounts on the <a href="{{ url_for('discover') }}">Discover</a> page to get started.</p>
        </div>
    {% endfor %}
    </div>
{% endblock %}
""",

"sixs_feed.html": """
{% extends "layout.html" %}
{% block head %}
<style>
    body { overflow: hidden; } /* Prevent background scroll */
    .sixs-container {
        height: 100vh;
        width: 100vw;
        overflow-y: scroll;
        scroll-snap-type: y mandatory;
        position: relative;
    }
    .six-item {
        height: 100vh;
        width: 100vw;
        scroll-snap-align: start;
        position: relative;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .six-video-background {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        object-fit: cover;
        filter: blur(20px) brightness(0.4);
        transform: scale(1.1);
    }
    .six-video-circle {
        position: relative;
        width: 90vw; height: 90vw;
        max-width: 50vh; max-height: 50vh; /* Better for portrait screens */
        border-radius: 50%;
        overflow: hidden;
        border: 2px solid rgba(255,255,255,0.2);
    }
    .six-video-circle video { width: 100%; height: 100%; object-fit: cover; }

    .six-ui-overlay {
        position: absolute;
        bottom: 80px; /* Space for nav bar */
        left: 0;
        right: 0;
        padding: 20px;
        color: white;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }
    .six-info { flex-grow: 1; }
    .six-info .username { font-weight: bold; font-size: 1.1em; }
    .six-actions { display: flex; flex-direction: column; gap: 20px; align-items: center; }
    .six-actions button { background: none; border: none; color: white; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 5px; font-size: 0.9em; }
    .six-actions .like-btn.liked { color: var(--like-red); fill: var(--like-red); }
    .six-actions .pfp { width: 45px; height: 45px; border: 2px solid white; }
</style>
{% endblock %}
{% block content %}
<div class="sixs-container" id="sixs-container">
    {% for post in posts %}
    <div class="six-item" id="six-{{ post.id }}">
        <video class="six-video-background" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop muted playsinline></video>
        <div class="six-video-circle">
            <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop playsinline></video>
        </div>
        <div class="six-ui-overlay">
            <div class="six-info">
                <a href="{{ url_for('profile', username=post.author.username) }}" class="username">@{{ post.author.username }}</a>
                <p>{{ post.text_content }}</p>
            </div>
            <div class="six-actions">
                 <a href="{{ url_for('profile', username=post.author.username) }}">
                    {% if post.author.profile_pic and post.author.profile_pic != 'default.png' %}
                        <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}">
                    {% else %}
                        <div class="pfp pfp-placeholder" style="background-color:{{ post.author.pfp_bg }};">{{ post.author.username[0]|upper }}</div>
                    {% endif %}
                 </a>
                <button class="like-btn like-btn-{{ post.id }} {{ 'liked' if current_user in post.liked_by else '' }}" onclick="handleLike({{ post.id }})">
                    {{ ICONS.like|safe }}
                    <span class="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                </button>
                <button onclick="openCommentModal({{ post.id }})">
                    {{ ICONS.comment|safe }}
                    <span>{{ post.comments.count() }}</span>
                </button>
            </div>
        </div>
    </div>
    {% endfor %}
</div>
{% endblock %}
{% block scripts %}
<script>
    const container = document.getElementById('sixs-container');
    const videos = container.querySelectorAll('.six-video');
    const backgroundVideos = container.querySelectorAll('.six-video-background');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target.querySelector('.six-video');
            const bgVideo = entry.target.querySelector('.six-video-background');
            if (entry.isIntersecting) {
                video.play();
                bgVideo.play();
            } else {
                video.pause();
                bgVideo.pause();
                video.currentTime = 0;
                bgVideo.currentTime = 0;
            }
        });
    }, { threshold: 0.5 });

    document.querySelectorAll('.six-item').forEach(item => {
        observer.observe(item);
    });
</script>
{% endblock %}
""",

"create_post.html": """
{% extends "layout.html" %}
{% block content %}
    <h2 style="text-align: center;">Creator Studio</h2>
    <div class="feed-nav">
        <a href="#" id="tab-text" class="active" onclick="showTab('text', event)">Text</a>
        <a href="#" id="tab-six" onclick="showTab('six', event)">Six</a>
    </div>

    <div id="text-creator">
        <form method="POST">
            <input type="hidden" name="post_type" value="text">
            <div class="form-group">
                <textarea name="text_content" rows="5" maxlength="150" placeholder="What's happening?" required></textarea>
            </div>
            <button type="submit" class="btn" style="width: 100%;">Post</button>
        </form>
    </div>

    <div id="six-creator" style="display: none; text-align: center;">
        <p id="recorder-status" style="color:var(--secondary-text);">Ready to record a 6 second video.</p>
        <video id="video-preview" autoplay muted playsinline style="width: 80%; max-width: 300px; border-radius: 50%; aspect-ratio: 1/1; object-fit: cover; margin: 15px auto; background: #111;"></video>
        <button id="record-button" class="btn">Start Recording</button>
        
        <form id="six-form-element" method="POST" enctype="multipart/form-data" style="display: none; margin-top: 20px;">
             <input type="hidden" name="post_type" value="six">
             <div class="form-group">
                <input type="text" name="caption" maxlength="50" placeholder="Add a caption... (optional)">
             </div>
             <button type="submit" class="btn" style="width: 100%;">Post Six</button>
        </form>
    </div>
{% endblock %}
{% block scripts %}
<script>
    let mediaRecorder;
    let recordedBlobs;
    let stream;
    const recordButton = document.getElementById('record-button');
    const preview = document.getElementById('video-preview');
    const sixForm = document.getElementById('six-form-element');
    const recorderStatus = document.getElementById('recorder-status');

    function showTab(tabName, event) {
        event.preventDefault();
        const isText = tabName === 'text';
        document.getElementById('text-creator').style.display = isText ? 'block' : 'none';
        document.getElementById('six-creator').style.display = isText ? 'none' : 'block';
        document.getElementById('tab-text').classList.toggle('active', isText);
        document.getElementById('tab-six').classList.toggle('active', !isText);
        
        if (!isText) {
            initCamera();
        } else if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
    }

    async function initCamera() {
        if (stream) return; // Already initialized
        const constraints = { audio: true, video: { width: 480, height: 480, facingMode: "user" } };
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            recorderStatus.textContent = "Camera ready. Tap to record.";
            preview.srcObject = stream;
            recordButton.disabled = false;
        } catch (e) {
            recorderStatus.textContent = "Camera permission denied. Please enable it in your browser settings.";
            console.error('getUserMedia error:', e);
            recordButton.disabled = true;
        }
    }

    recordButton.addEventListener('click', () => {
        if (recordButton.textContent === 'Start Recording') {
            startRecording();
        } else {
            stopRecording();
        }
    });

    function startRecording() {
        if (!stream) {
            recorderStatus.textContent = "Camera not ready.";
            return;
        }
        recordedBlobs = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
        mediaRecorder.onstop = (event) => {
            const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
            preview.src = window.URL.createObjectURL(superBuffer);
            preview.srcObject = null;
            preview.controls = false;
            preview.muted = false;
            sixForm.style.display = 'block';
            recordButton.style.display = 'none';
            recorderStatus.textContent = 'Previewing...';
        };
        mediaRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                recordedBlobs.push(event.data);
            }
        };
        mediaRecorder.start();
        recordButton.textContent = 'Stop Recording';
        recorderStatus.textContent = 'Recording...';
        
        setTimeout(() => {
            if (mediaRecorder.state === "recording") {
                stopRecording();
            }
        }, 6000); // Max 6 seconds
    }

    function stopRecording() {
        if (mediaRecorder.state === "recording") {
            mediaRecorder.stop();
            recordButton.textContent = 'Start Recording';
        }
    }

    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, { type: 'video/webm' });
        formData.append('video_file', videoBlob, 'six-video.webm');
        
        const submitBtn = sixForm.querySelector('button');
        submitBtn.disabled = true;
        submitBtn.textContent = "Uploading...";

        fetch("{{ url_for('create_post') }}", { method: 'POST', body: formData })
        .then(response => {
            if (response.redirected) window.location.href = response.url;
            else {
                 submitBtn.disabled = false;
                 submitBtn.textContent = "Post Six";
                 alert("Upload failed. Please try again.");
            }
        }).catch(err => console.error(err));
    });
</script>
{% endblock %}
""",

"edit_profile.html": """
{% extends "layout.html" %}
{% block content %}
    <h2 style="text-align: center;">Edit Profile</h2>
    <div style="padding: 15px;">
        <form method="POST" action="{{ url_for('edit_profile') }}">
            <div class="form-group">
                <label for="bio">Bio</label>
                <textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea>
            </div>
            <button type="submit" class="btn" style="width: 100%;">Save Changes</button>
        </form>
    </div>

    <div style="border-top: 8px solid var(--border-color); padding: 20px;">
        <h3 style="color:var(--like-red);">Danger Zone</h3>
        <p style="color:var(--secondary-text);">Deleting your account is permanent and cannot be undone. All your posts and comments will be removed.</p>
        <form method="POST" action="{{ url_for('delete_account') }}" onsubmit="return confirm('Are you absolutely sure you want to delete your account? This action is irreversible.');">
            <div class="form-group">
                <label for="password">Enter Your Password to Confirm</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-danger" style="width: 100%;">Delete My Account</button>
        </form>
    </div>
{% endblock %}
""",

"auth_form.html": """
{% extends "layout.html" %}
{% block content %}
    <div style="padding: 30px 15px;">
        <h2 style="text-align: center;">{{ title }}</h2>
        <form method="POST">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn" style="width: 100%;">{{ title }}</button>
        </form>
        <p style="margin-top: 1.5rem; text-align:center; color: var(--secondary-text);">
            {% if form_type == 'login' %}
                Don't have an account? <a href="{{ url_for('signup') }}">Sign Up</a>
            {% else %}
                Already have an account? <a href="{{ url_for('login') }}">Login</a>
            {% endif %}
        </p>
    </div>
{% endblock %}
""",
# Other templates (profile, discover) are assumed to work with the updated post_card.html and layout.html
}

# --- JINJA2 CUSTOM LOADER ---
class DictLoader(BaseLoader):
    def __init__(self, templates_dict): self.templates = templates_dict
    def get_source(self, environment, template):
        if template in self.templates:
            return self.templates[template], None, lambda: True
        raise TemplateNotFound(template)
app.jinja_loader = DictLoader(templates)

# --- DATABASE MODELS ---
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(150))
    profile_pic = db.Column(db.String(120), default='default.png')
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='commenter', lazy='dynamic', cascade="all, delete-orphan")
    followed = db.relationship('User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def follow(self, user):
        if not self.is_following(user): self.followed.append(user)
    def unfollow(self, user):
        if self.is_following(user): self.followed.remove(user)
    def is_following(self, user): return self.followed.filter(followers.c.followed_id == user.id).count() > 0
    @property
    def pfp_bg(self):
        colors = ["#e57373", "#f06292", "#ba68c8", "#9575cd", "#7986cb", "#64b5f6", "#4fc3f7", "#4dd0e1", "#4db6ac", "#81c784"]
        return colors[hash(self.username) % len(colors)]

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(10), nullable=False)
    text_content = db.Column(db.String(150))
    video_filename = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    liked_by = db.relationship('User', secondary='likes', backref=db.backref('liked_posts', lazy='dynamic'), lazy='dynamic')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True)
)

# --- LOGIN MANAGER & ROUTES ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    
    query = Post.query.options(joinedload(Post.author), joinedload(Post.comments), joinedload(Post.liked_by)).filter(Post.user_id.in_(followed_ids))

    if feed_type == 'sixs':
        posts = query.filter_by(post_type='six').order_by(Post.timestamp.desc()).all()
        return render_template('sixs_feed.html', posts=posts, full_screen_mode=True)
    else: # Default to text
        posts = query.filter_by(post_type='text').order_by(Post.timestamp.desc()).all()
        return render_template('home.html', posts=posts, feed_type='text')

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form.get('post_type')
        if post_type == 'text':
            content = request.form.get('text_content')
            post = Post(post_type='text', text_content=content, author=current_user)
        elif post_type == 'six':
            video_file = request.files.get('video_file')
            filename = secure_filename(f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.webm")
            video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post = Post(post_type='six', text_content=request.form.get('caption', ''), video_filename=filename, author=current_user)
        else:
            flash('Invalid post type.', 'error')
            return redirect(url_for('create_post'))
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('create_post.html')

@app.route('/post/<int:post_id>/comments')
@login_required
def get_comments(post_id):
    comments = Comment.query.filter_by(post_id=post_id).order_by(Comment.timestamp.asc()).all()
    return jsonify([{
        'text': c.text, 'timestamp': c.timestamp.strftime('%b %d'),
        'user': {'username': c.commenter.username, 'pfp_bg': c.commenter.pfp_bg, 'initial': c.commenter.username[0].upper()}
    } for c in comments])

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    comment = Comment(text=request.json['text'], user_id=current_user.id, post_id=post_id)
    db.session.add(comment)
    db.session.commit()
    return jsonify({'success': True}), 201

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user in post.liked_by:
        post.liked_by.remove(current_user)
        liked = False
    else:
        post.liked_by.append(current_user)
        liked = True
    db.session.commit()
    return jsonify({'liked': liked, 'likes': len(post.liked_by)})

# --- AUTH & PROFILE ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True) # <-- Set persistent cookie
            return redirect(url_for('home'))
        flash('Invalid username or password.', 'error')
    return render_template('auth_form.html', title="Login", form_type="login")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already taken.', 'error')
            return redirect(url_for('signup'))
        new_user = User(username=request.form['username'])
        new_user.set_password(request.form['password'])
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth_form.html', title="Sign Up", form_type="signup")

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    # For simplicity, we just show all posts on profile
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).all()
    return render_template('home.html', posts=posts, feed_type='text') # Re-use home template for profile feed

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', current_user.bio)
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('edit_profile'))
    return render_template('edit_profile.html')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    if not current_user.check_password(request.form.get('password')):
        flash('Incorrect password. Account not deleted.', 'error')
        return redirect(url_for('edit_profile'))
    
    user_to_delete = User.query.get(current_user.id)
    logout_user()
    db.session.delete(user_to_delete)
    db.session.commit()
    flash('Your account has been permanently deleted.', 'success')
    return redirect(url_for('login'))

# Placeholder routes for other nav items
@app.route('/discover')
@login_required
def discover():
    # A simple discover: users you don't follow
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    users = User.query.filter(User.id.notin_(followed_ids)).order_by(db.func.random()).limit(15).all()
    return render_template('home.html', posts=[], users_to_discover=users) # Simplified for now

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)