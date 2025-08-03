import os
import datetime
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from jinja2 import BaseLoader, TemplateNotFound
from datetime import timedelta

# --- APP CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-glass-ui-key'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_HTTPONLY'] = True

# --- INITIALIZE EXTENSIONS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- SETUP SQLITE PRAGMA FOR FOREIGN KEYS ---
if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
    def _fk_pragma_on_connect(dbapi_con, con_record):
        dbapi_con.execute('PRAGMA foreign_keys=ON')

    with app.app_context():
        event.listen(db.engine, 'connect', _fk_pragma_on_connect)

# --- SVG ICONS DICTIONARY ---
ICONS = {
    'home': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    'discover': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    'create': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>',
    'profile': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    'like': '<svg xmlns="http://www.w3.org/2000/svg" class="icon-like" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    'comment': '<svg xmlns="http://www.w3.org/2000/svg" class="icon-comment" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    'repost': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
    'send': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>',
    'follow': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-user-plus"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="17" y1="11" x2="23" y2="11"></line></svg>'
}
app.jinja_env.globals.update(ICONS=ICONS)


# --- TEMPLATES DICTIONARY ---
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
            --bg-color: #121212;
            --primary-color: #1e1e1e;
            --secondary-color: #2a2a2a;
            --accent-color: #00b7ff;
            --text-color: #e0e0e0;
            --text-muted: #8e8e8e;
            --border-color: #333333;
        }
        html { -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0; 
            background-color: var(--bg-color); 
            color: var(--text-color); 
            font-size: 16px;
            padding-bottom: 70px;
        }
        .container { max-width: 600px; margin: 0 auto; padding: 15px; }
        a { color: var(--accent-color); text-decoration: none; }
        
        .top-bar, .bottom-nav {
            background: rgba(20, 20, 20, 0.7);
            backdrop-filter: blur(15px) saturate(180%);
            -webkit-backdrop-filter: blur(15px) saturate(180%);
            z-index: 1000;
        }
        .top-bar { position: sticky; top: 0; padding: 10px 15px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }
        .top-bar .logo { font-weight: bold; font-size: 1.8em; color: var(--text-color); }
        .bottom-nav { position: fixed; bottom: 0; left: 0; right: 0; border-top: 1px solid var(--border-color); display: flex; justify-content: space-around; padding: 10px 0; }
        .bottom-nav a { color: var(--text-muted); transition: color 0.2s ease, transform 0.2s ease; }
        .bottom-nav a.active { color: var(--accent-color); transform: scale(1.1); }
        .bottom-nav a svg { width: 28px; height: 28px; }

        .card { background: var(--bg-color); border-bottom: 1px solid var(--border-color); padding: 15px; margin-bottom: 0px; }
        
        .post-header { display: flex; align-items: flex-start; margin-bottom: 8px; }
        .pfp { width: 45px; height: 45px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }
        .pfp-placeholder { display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 1.2rem; background-color: var(--secondary-color); color: var(--text-color); }
        .post-info { margin-left: 12px; }
        .post-info .username { font-weight: bold; }
        .post-info .timestamp { font-size: 0.9em; color: var(--text-muted); }
        .post-content p { white-space: pre-wrap; word-wrap: break-word; line-height: 1.5; margin: 0; }
        
        .text-post-actions { display: flex; justify-content: space-around; padding-top: 12px; margin-top: 12px; }
        .text-post-actions button { background: none; border: none; cursor: pointer; color: var(--text-muted); display: flex; align-items: center; gap: 8px; font-size: 0.9em; transition: color 0.2s ease; }
        .text-post-actions button:hover, .text-post-actions button.liked { color: var(--accent-color); }
        .text-post-actions button svg { stroke: var(--text-muted); transition: stroke 0.2s ease; }
        .text-post-actions button:hover svg, .text-post-actions button.liked svg { stroke: var(--accent-color); }
        .text-post-actions button.liked .icon-like { fill: var(--accent-color); }
        .text-post-actions svg { width: 20px; height: 20px; }

        .btn { background-color: var(--accent-color); color: #fff; padding: 10px 20px; border: none; border-radius: 30px; cursor: pointer; text-decoration: none; display: inline-block; font-weight: bold; transition: background-color 0.2s; }
        .btn:hover { background-color: #009dcf; }
        .btn-secondary { background-color: var(--secondary-color); color: var(--text-color); }
        .btn-danger { background-color: #d9534f; color: #fff; }

        .form-group input, .form-group textarea { width: 100%; padding: 12px; border: 1px solid var(--border-color); border-radius: 8px; background: var(--primary-color); color: var(--text-color); box-sizing: border-box; font-size: 1rem; }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
    {% if not immersive_page %}
    <header class="top-bar"><div class="logo">Sixsec</div></header>
    {% endif %}
    <main class="{% if not immersive_page %}container{% endif %}">
        {% block content %}{% endblock %}
    </main>
    {% if current_user.is_authenticated and not immersive_page %}
    <nav class="bottom-nav">
        <a href="{{ url_for('home') }}" class="{{ 'active' if request.endpoint == 'home' else '' }}">{{ ICONS.home|safe }}</a>
        <a href="{{ url_for('discover') }}" class="{{ 'active' if request.endpoint == 'discover' else '' }}">{{ ICONS.discover|safe }}</a>
        <a href="{{ url_for('create_post') }}" class="{{ 'active' if request.endpoint == 'create_post' else '' }}">{{ ICONS.create|safe }}</a>
        <a href="{{ url_for('profile', username=current_user.username) }}" class="{{ 'active' if request.endpoint == 'profile' else '' }}">{{ ICONS.profile|safe }}</a>
    </nav>
    {% endif %}
    {% block scripts %}{% endblock %}
</body>
</html>
""",
"home.html": """
{% extends "layout.html" %}
{% block head %}
<style>
    .feed-toggle {
        display: flex; justify-content: center; position: sticky; top: 57px; /* Below top-bar */
        background: rgba(18, 18, 18, 0.85); backdrop-filter: blur(10px);
        z-index: 900; padding: 10px 0;
    }
    .feed-toggle a {
        flex: 1; text-align: center; padding: 10px 0; color: var(--text-muted);
        font-weight: bold; border-bottom: 2px solid transparent;
    }
    .feed-toggle a.active {
        color: var(--text-color);
        border-bottom-color: var(--accent-color);
    }
    .feed-container { padding: 0; } /* Remove padding for edge-to-edge cards */
</style>
{% endblock %}
{% block content %}
    <div class="feed-toggle">
        <a href="{{ url_for('home', feed_type='text') }}" class="{{ 'active' if feed_type == 'text' }}">For You</a>
        <a href="{{ url_for('home', feed_type='sixs') }}" class="{{ 'active' if feed_type == 'sixs' }}">Sixs</a>
    </div>
    <div class="feed-container">
    {% for post in posts %}
        {% include 'text_post_card.html' %}
    {% else %}
        <div class="card" style="text-align:center; color:var(--text-muted); border-bottom:none;">
            <p style="margin-top:40px;">Your feed is empty.</p>
            <p>Follow some accounts on the <a href="{{ url_for('discover') }}">Discover</a> page!</p>
        </div>
    {% endfor %}
    </div>
{% endblock %}
""",
"sixs_feed.html": """
{% extends "layout.html" %}
{% block title %}Sixs{% endblock %}
{% block head %}
<style>
    html, body { overflow: hidden; height: 100%; } /* Crucial for full-screen scroll */
    main { padding: 0 !important; max-width: none !important; height: 100vh; }
    .sixs-container {
        width: 100%; height: 100%;
        scroll-snap-type: y mandatory;
        overflow-y: scroll;
    }
    .six-item {
        width: 100%; height: 100%;
        scroll-snap-align: start;
        position: relative;
        display: flex; align-items: center; justify-content: center;
        background-color: #000;
    }
    .circular-video-wrapper {
        width: 100vmin; height: 100vmin; /* Adjusted to fit better on different screens */
        max-width: 90vh; max-height: 90vh;
        min-width: 320px; min-height: 320px;
        position: relative;
        border-radius: 50%;
        overflow: hidden;
    }
    .six-video {
        width: 100%; height: 100%; object-fit: cover;
    }
    .six-overlay {
        position: absolute; bottom: 70px; left: 15px; color: #fff;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.7);
    }
    .six-overlay .username { font-weight: bold; font-size: 1.1em; }
    .six-actions {
        position: absolute; right: 15px; bottom: 70px;
        display: flex; flex-direction: column; align-items: center; gap: 20px;
    }
    .action-button { background: none; border: none; cursor: pointer; color: #fff; text-align: center; }
    .action-button .icon-like.liked { fill: #ff4141; stroke: #ff4141; }
    .action-button span { font-size: 0.9em; display: block; margin-top: 4px; }
    .pfp-follow { position: relative; }
    .pfp-follow .pfp { width: 45px; height: 45px; border: 2px solid #fff; }
    .follow-plus {
        position: absolute; bottom: -5px; left: 50%; transform: translateX(-50%);
        width: 20px; height: 20px; border-radius: 50%; background-color: var(--accent-color);
        color: #fff; display: flex; align-items: center; justify-content: center;
        font-size: 16px; font-weight: bold; line-height: 20px;
    }
    .back-arrow {
        position: fixed; top: 15px; left: 15px; z-index: 1100;
        color: white; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 50%;
    }
</style>
{% endblock %}
{% block content %}
    <a href="{{ url_for('home') }}" class="back-arrow">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
    </a>
    <div class="sixs-container" id="sixs-container">
        {% for post in posts %}
        <div class="six-item" data-post-id="{{ post.id }}">
            <div class="circular-video-wrapper">
                <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop preload="auto" playsinline></video>
            </div>
            <div class="six-overlay">
                <a href="{{ url_for('profile', username=post.author.username) }}"><strong class="username">@{{ post.author.username }}</strong></a>
                <p>{{ post.text_content }}</p>
            </div>
            <div class="six-actions">
                <div class="pfp-follow">
                    <a href="{{ url_for('profile', username=post.author.username) }}">
                        {% if post.author.profile_pic and post.author.profile_pic != 'default.png' %}
                            <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}">
                        {% else %}
                            <div class="pfp pfp-placeholder" style="background-color:{{ post.author.pfp_bg }};">{{ post.author.username[0]|upper }}</div>
                        {% endif %}
                    </a>
                    {% if not current_user.is_following(post.author) and current_user != post.author %}
                    <a href="{{ url_for('follow', username=post.author.username, next=request.path) }}" class="follow-plus">+</a>
                    {% endif %}
                </div>
                <button class="action-button" onclick="handleLike({{ post.id }}, this)">
                    {{ ICONS.like|safe }}
                    <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                </button>
                <button class="action-button">
                    {{ ICONS.comment|safe }}
                    <span>{{ post.comments.count() }}</span>
                </button>
            </div>
        </div>
        {% endfor %}
    </div>
{% endblock %}
{% block scripts %}
<script>
    document.addEventListener('DOMContentLoaded', () => {
        const videos = document.querySelectorAll('.six-video');
        if (videos.length === 0) return;

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.play().catch(e => console.error("Video play failed:", e));
                } else {
                    entry.target.pause();
                    entry.target.currentTime = 0;
                }
            });
        }, { threshold: 0.5 });

        videos.forEach(video => {
            observer.observe(video);
            video.parentElement.parentElement.addEventListener('click', (e) => {
                // Prevent click on action buttons from toggling play/pause
                if (e.target.closest('.six-actions') || e.target.closest('.six-overlay a')) return;
                
                if(video.paused) video.play().catch(e => console.error("Video play failed:", e));
                else video.pause();
            });
        });
    });

    async function handleLike(postId, buttonElement) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        
        const likeIcon = buttonElement.querySelector('.icon-like');
        const likeCount = buttonElement.querySelector('span');
        
        likeCount.textContent = data.likes;
        likeIcon.classList.toggle('liked', data.liked);
    }
</script>
{% endblock %}
""",
"text_post_card.html": """
<div class="card">
    <div class="post-header">
        <a href="{{ url_for('profile', username=post.author.username) }}">
        {% if post.author.profile_pic and post.author.profile_pic != 'default.png' %}
            <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}">
        {% else %}
            <div class="pfp pfp-placeholder" style="background-color:{{ post.author.pfp_bg }};">{{ post.author.username[0]|upper }}</div>
        {% endif %}
        </a>
        <div class="post-info">
            <a href="{{ url_for('profile', username=post.author.username) }}" class="username">{{ post.author.username }}</a>
            <div class="timestamp">{{ post.timestamp.strftime('%b %d') }}</div>
        </div>
    </div>
    <div class="post-content">
        <p>{{ post.text_content }}</p>
    </div>
    <div class="text-post-actions">
        <button id="like-btn-{{ post.id }}" onclick="handleTextLike({{ post.id }})" class="{{ 'liked' if current_user in post.liked_by else '' }}">
            <svg xmlns="http://www.w3.org/2000/svg" class="icon-like" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
            <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
        </button>
        <button>{{ ICONS.comment|safe }} <span>{{ post.comments.count() }}</span></button>
        <button disabled title="Reposts are disabled">{{ ICONS.repost|safe }}</button>
    </div>
</div>
<script>
    async function handleTextLike(postId) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        
        const likeButton = document.getElementById(`like-btn-${postId}`);
        const likeCount = document.getElementById(`like-count-${postId}`);
        
        likeCount.textContent = data.likes;
        likeButton.classList.toggle('liked', data.liked);
    }
</script>
""",
"create_post.html": """
{% extends "layout.html" %}
{% block title %}Create{% endblock %}
{% block content %}
    <div class="card" style="border-bottom:none;">
        <h2 style="text-align: center;">Create Post</h2>
        <form id="text-form-element" method="POST">
            <input type="hidden" name="post_type" value="text">
            <div class="form-group">
                <textarea name="text_content" rows="5" maxlength="150" placeholder="What's happening?" required style="font-size: 1.2rem;"></textarea>
            </div>
            <button type="submit" class="btn" style="width: 100%;">Post</button>
        </form>
    </div>
    <div class="card" style="border-bottom:none;">
        <h2 style="text-align: center; margin-top: 30px;">Record a Six</h2>
        <div id="six-recorder" style="text-align: center;">
            <p id="recorder-status">Grant camera permission to record</p>
            <video id="video-preview" autoplay muted playsinline style="width: 100%; max-width: 250px; border-radius: 50%; aspect-ratio: 1/1; object-fit: cover; margin: 15px auto; background: #000;"></video>
            <button id="record-button" class="btn" disabled>Record</button>
        </div>
        <form id="six-form-element" method="POST" enctype="multipart/form-data" style="display: none; margin-top: 20px;">
             <input type="hidden" name="post_type" value="sixs">
             <div class="form-group">
                <input type="text" name="caption" maxlength="50" placeholder="Add a caption... (optional)">
             </div>
             <button type="submit" class="btn" style="width: 100%;">Post Six</button>
        </form>
    </div>
{% endblock %}
{% block scripts %}
<script>
    const recordButton = document.getElementById('record-button');
    const preview = document.getElementById('video-preview');
    const sixForm = document.getElementById('six-form-element');
    const recorderStatus = document.getElementById('recorder-status');
    let mediaRecorder;
    let recordedBlobs;
    
    async function initCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: { width: 480, height: 480, facingMode: "user" } });
            recorderStatus.textContent = 'Ready to record!';
            recordButton.disabled = false;
            window.stream = stream; 
            preview.srcObject = stream;
        } catch (e) {
            recorderStatus.textContent = "Camera permission denied. Please enable it in your browser settings.";
        }
    }
    initCamera(); 

    recordButton.addEventListener('click', () => {
        if (recordButton.textContent === 'Record') startRecording();
        else stopRecording();
    });

    function startRecording() {
        if (!window.stream) { alert('Camera stream not available.'); return; }
        recordedBlobs = [];
        mediaRecorder = new MediaRecorder(window.stream, { mimeType: 'video/webm' });
        mediaRecorder.ondataavailable = event => { if (event.data && event.data.size > 0) recordedBlobs.push(event.data); };
        mediaRecorder.onstop = () => {
            recordButton.textContent = 'Record';
            recorderStatus.textContent = 'Previewing...';
            const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
            preview.srcObject = null;
            preview.src = window.URL.createObjectURL(superBuffer);
            preview.controls = false;
            preview.muted = false;
            sixForm.style.display = 'block';
        };
        mediaRecorder.start();
        recordButton.textContent = 'Stop';
        recorderStatus.textContent = 'Recording...';
        setTimeout(() => { if (mediaRecorder.state === "recording") stopRecording(); }, 6000);
    }
    
    function stopRecording() { if (mediaRecorder.state === "recording") mediaRecorder.stop(); }

    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        formData.append('video_file', videoBlob, 'six-video.webm');
        const submitBtn = sixForm.querySelector('button');
        submitBtn.disabled = true;
        submitBtn.textContent = "Uploading...";
        fetch("{{ url_for('create_post') }}", { method: 'POST', body: formData })
        .then(response => { if (response.redirected) window.location.href = response.url; })
        .catch(error => console.error('Error:', error));
    });
</script>
{% endblock %}
""",
"edit_profile.html": """
{% extends "layout.html" %}
{% block title %}Edit Profile{% endblock %}
{% block content %}
    <div class="card" style="border:none;">
        <h2 style="text-align: center;">Edit Profile</h2>
        <form method="POST">
            <div class="form-group">
                <label for="bio">Bio</label>
                <textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea>
            </div>
            <button type="submit" class="btn" style="width: 100%;">Save Changes</button>
        </form>
    </div>
    <div class="card" style="margin-top:20px; border:1px solid #d9534f; border-radius:10px;">
        <h3 style="color:#d9534f;">Danger Zone</h3>
        <p>Deleting your account is permanent and cannot be undone.</p>
        <form action="{{ url_for('delete_account') }}" method="POST" onsubmit="return confirm('Are you absolutely sure you want to delete your account? This action is irreversible.');">
            <button type="submit" class="btn btn-danger" style="width:100%;">Delete My Account</button>
        </form>
    </div>
{% endblock %}
""",
"profile.html": """
{% extends "layout.html" %}
{% block title %}{{ user.username }}{% endblock %}
{% block content %}
    <div class="card" style="border:none;">
        <div style="display: flex; flex-direction: column; align-items: center; text-align: center;">
             {% if user.profile_pic and user.profile_pic != 'default.png' %}
                <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + user.profile_pic) }}" style="width: 90px; height: 90px; margin-bottom: 15px;">
            {% else %}
                <div class="pfp pfp-placeholder" style="width: 90px; height: 90px; margin-bottom: 15px; font-size: 2.5rem; background-color:{{ user.pfp_bg }};">{{ user.username[0]|upper }}</div>
            {% endif %}
            
            <h2>{{ user.username }}</h2>
            <p style="color: var(--text-muted); margin-top: -10px; max-width: 80%;">{{ user.bio or "No bio yet." }}</p>

            {% if current_user != user %}
                <div style="margin-top: 15px;">
                {% if not current_user.is_following(user) %}
                    <a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>
                {% else %}
                    <a href="{{ url_for('unfollow', username=user.username) }}" class="btn btn-secondary">Unfollow</a>
                {% endif %}
                </div>
            {% else %}
                 <a href="{{ url_for('edit_profile') }}" class="btn btn-secondary" style="margin-top:15px;">Edit Profile</a>
            {% endif %}
        </div>
        <div style="display: flex; justify-content: space-around; text-align: center; margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-color);">
            <div><strong>{{ user.posts.count() }}</strong><br><span style="color:var(--text-muted);">Posts</span></div>
            <div><strong>{{ user.followers.count() }}</strong><br><span style="color:var(--text-muted);">Followers</span></div>
            <div><strong>{{ user.followed.count() }}</strong><br><span style="color:var(--text-muted);">Following</span></div>
        </div>
    </div>
    
    {% for post in posts %}
        {% if post.post_type == 'text' %}
            {% include 'text_post_card.html' %}
        {% else %}
             <div class="card"><i>Video post by {{user.username}} is visible in the Sixs feed.</i></div>
        {% endif %}
    {% else %}
        <div class="card" style="text-align:center; color:var(--text-muted);">
            <p>No posts yet.</p>
        </div>
    {% endfor %}
{% endblock %}
""",
"auth_form.html": """
{% extends "layout.html" %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
    <div class="card" style="margin-top: 2rem; border:none;">
        <h2 style="text-align: center;">{{ title }}</h2>
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <input type="text" id="username" name="username" required placeholder="Username">
            </div>
            {% if form_type == 'signup' %}
            <div class="form-group">
                <input type="text" id="bio" name="bio" maxlength="150" placeholder="Bio (optional)">
            </div>
            {% endif %}
            <div class="form-group">
                <input type="password" id="password" name="password" required placeholder="Password">
            </div>
            <button type="submit" class="btn" style="width: 100%;">{{ title }}</button>
        </form>
        <p style="margin-top: 1.5rem; text-align:center;">
            {% if form_type == 'login' %}
                Don't have an account? <a href="{{ url_for('signup') }}">Sign Up</a>
            {% else %}
                Already have an account? <a href="{{ url_for('login') }}">Login</a>
            {% endif %}
        </p>
    </div>
{% endblock %}
""",
"discover.html": """
{% extends "layout.html" %}
{% block title %}Discover{% endblock %}
{% block content %}
    <h2 style="text-align:center; padding-bottom:15px;">Discover</h2>
    {% for item in discover_items %}
        {% if item.type == 'post' and item.content.post_type == 'text' %}
            {% set post = item.content %}
            {% include 'text_post_card.html' %}
        {% elif item.type == 'user' %}
            {% set user = item.content %}
            <div class="card">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <a href="{{ url_for('profile', username=user.username) }}">
                    {% if user.profile_pic and user.profile_pic != 'default.png' %}
                        <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + user.profile_pic) }}">
                    {% else %}
                        <div class="pfp pfp-placeholder" style="background-color:{{ user.pfp_bg }};">{{ user.username[0]|upper }}</div>
                    {% endif %}
                    </a>
                    <div style="flex-grow: 1;">
                        <a href="{{ url_for('profile', username=user.username) }}" class="username"><strong>{{ user.username }}</strong></a>
                        <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ user.bio|truncate(50) if user.bio else '' }}</p>
                    </div>
                     <div>
                        {% if not current_user.is_following(user) %}
                        <a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>
                        {% endif %}
                     </div>
                </div>
            </div>
        {% endif %}
    {% else %}
        <div class="card" style="text-align:center; color: var(--text-muted);"><p>Nothing to discover right now.</p></div>
    {% endfor %}
{% endblock %}
"""
}


# --- JINJA2 CUSTOM LOADER ---
class DictLoader(BaseLoader):
    def __init__(self, templates_dict): self.templates = templates_dict
    def get_source(self, environment, template):
        if template in self.templates: return self.templates[template], None, lambda: True
        raise TemplateNotFound(template)
app.jinja_loader = DictLoader(templates)


# --- DATABASE MODELS ---
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
)
likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'))
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
    def followed_posts(self, post_type=None):
        followed_user_ids = [user.id for user in self.followed]
        followed_user_ids.append(self.id)
        query = Post.query.filter(Post.user_id.in_(followed_user_ids))
        if post_type: query = query.filter(Post.post_type == post_type)
        return query.order_by(Post.timestamp.desc()).all()
    @property
    def pfp_bg(self):
        colors = ["#e57373", "#f06292", "#ba68c8", "#9575cd", "#7986cb", "#64b5f6", "#4fc3f7", "#4dd0e1", "#4db6ac", "#81c784"]
        return colors[hash(self.username) % len(colors)]

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(10), nullable=False) # 'text' or 'sixs'
    text_content = db.Column(db.String(150))
    video_filename = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    liked_by = db.relationship('User', secondary=likes, backref=db.backref('liked_posts', lazy='dynamic'))

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id', ondelete='CASCADE'), nullable=False)


# --- ROUTES ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    if feed_type == 'sixs':
        posts = current_user.followed_posts('sixs')
        return render_template('sixs_feed.html', posts=posts, immersive_page=True)
    posts = current_user.followed_posts('text')
    return render_template('home.html', posts=posts, feed_type='text', immersive_page=False)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form.get('post_type')
        post = None
        if post_type == 'text':
            post = Post(post_type='text', text_content=request.form.get('text_content'), author=current_user)
        elif post_type == 'sixs':
            video_file = request.files.get('video_file')
            filename = secure_filename(f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.webm")
            video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post = Post(post_type='sixs', text_content=request.form.get('caption', ''), video_filename=filename, author=current_user)
        if post:
            db.session.add(post)
            db.session.commit()
        return redirect(url_for('home'))
    return render_template('create_post.html', immersive_page=False)

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user_to_delete = User.query.get(current_user.id)
    logout_user()
    db.session.delete(user_to_delete)
    db.session.commit()
    flash('Your account has been permanently deleted.', 'success')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True)
            return redirect(url_for('home'))
        flash('Invalid username or password.', 'error')
    return render_template('auth_form.html', title="Login", form_type="login", immersive_page=True)

@app.route('/discover')
@login_required
def discover():
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    recent_posts = Post.query.filter(Post.user_id.notin_(followed_ids)).order_by(Post.timestamp.desc()).limit(10).all()
    random_users = User.query.filter(User.id.notin_(followed_ids)).order_by(db.func.random()).limit(5).all()
    discover_items = [{'type': 'post', 'content': p} for p in recent_posts] + \
                     [{'type': 'user', 'content': u} for u in random_users]
    random.shuffle(discover_items)
    return render_template('discover.html', discover_items=discover_items, immersive_page=False)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = user.posts.order_by(Post.timestamp.desc()).all()
    return render_template('profile.html', user=user, posts=posts, immersive_page=False)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', current_user.bio)
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html', immersive_page=False)

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user:
        current_user.follow(user)
        db.session.commit()
    next_url = request.args.get('next') or request.referrer or url_for('home')
    return redirect(next_url)

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user:
        current_user.unfollow(user)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

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
    return jsonify({'liked': liked, 'likes': post.liked_by.count()})

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already taken.', 'error')
            return redirect(url_for('signup'))
        new_user = User(username=request.form['username'], bio=request.form.get('bio', ''))
        new_user.set_password(request.form['password'])
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth_form.html', title="Sign Up", form_type="signup", immersive_page=True)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')): os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'))
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)