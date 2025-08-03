import os
import datetime
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from jinja2 import BaseLoader, TemplateNotFound

# --- APP CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-final-polished-key-for-sixsec'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- INITIALIZE EXTENSIONS & HELPERS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

ICONS = {
    'home': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    'discover': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    'create': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>',
    'profile': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    'like': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    'comment': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    'repost': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
    'send': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>'
}
app.jinja_env.globals.update(ICONS=ICONS)


# --- TEMPLATES (stored as a dictionary) ---
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
            --bg-color: #0d1117;
            --primary-color: #161b22;
            --border-color: #30363d;
            --accent-color: #238636; /* A more subtle, modern green */
            --accent-hover: #2ea043;
            --text-color: #c9d1d9;
            --text-muted: #8b949e;
            --text-link: #58a6ff;
            --red-color: #f85149;
        }
        html { -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0; 
            background-color: var(--bg-color); 
            color: var(--text-color); 
            font-size: 16px;
            overscroll-behavior-y: contain; /* Prevents pull-to-refresh on scrollable bodies */
        }
        .container { max-width: 600px; margin: 0 auto; padding: 15px 15px 80px 15px; }
        a { color: var(--text-link); text-decoration: none; }
        
        .top-bar {
            position: sticky; top: 0; z-index: 1000;
            background: rgba(13, 17, 23, 0.7);
            backdrop-filter: blur(10px) saturate(180%);
            -webkit-backdrop-filter: blur(10px) saturate(180%);
            padding: 10px 15px;
            border-bottom: 1px solid var(--border-color);
            display: flex; justify-content: space-between; align-items: center;
        }
        .top-bar .logo { font-weight: bold; font-size: 1.8em; color: var(--text-color); }
        .bottom-nav { 
            position: fixed; bottom: 0; left: 0; right: 0;
            background: rgba(13, 17, 23, 0.7);
            backdrop-filter: blur(10px) saturate(180%); -webkit-backdrop-filter: blur(10px) saturate(180%);
            border-top: 1px solid var(--border-color);
            display: flex; justify-content: space-around; padding: 10px 0; z-index: 1000; 
        }
        .bottom-nav a { color: var(--text-muted); transition: color 0.2s ease, transform 0.2s ease; }
        .bottom-nav a.active { color: var(--text-color); transform: scale(1.1); }
        .bottom-nav a svg { width: 28px; height: 28px; }

        .card { background-color: transparent; border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 1px; }
        .post-card-content { padding: 12px; }
        .post-header { display: flex; align-items: center; margin-bottom: 8px; }
        .post-header .pfp { width: 40px; height: 40px; border-radius: 50%; margin-right: 12px; object-fit: cover; }
        .post-header .pfp-placeholder { display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 1.2rem; }
        .post-header .username { font-weight: bold; }
        .post-header .timestamp { font-size: 0.9em; color: var(--text-muted); margin-left: 8px; }
        .post-content p { white-space: pre-wrap; word-wrap: break-word; line-height: 1.5; font-size: 1.05rem; }
        
        .post-actions { display: flex; justify-content: space-around; }
        .post-actions button { background: none; border: none; cursor: pointer; color: var(--text-muted); display: flex; align-items: center; gap: 8px; font-size: 0.9em; padding: 12px; transition: color 0.2s ease; }
        .post-actions .liked, .post-actions .liked svg { color: var(--red-color); fill: var(--red-color); }
        .post-actions button:hover { background-color: rgba(255, 255, 255, 0.05); }

        .btn {
            background-color: var(--primary-color); color: var(--text-color); padding: 10px 18px;
            border: 1px solid var(--border-color); border-radius: 20px;
            cursor: pointer; text-decoration: none; display: inline-block; font-weight: bold;
            transition: background-color 0.2s ease;
        }
        .btn-primary { background-color: var(--accent-color); color: white; border: none; }
        .btn-primary:hover { background-color: var(--accent-hover); }
        .btn-danger { background-color: var(--red-color); color: white; border: none; }
        
        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: .5rem; color: var(--text-muted); }
        .form-group input, .form-group textarea {
            width: 100%; padding: 12px; border: 1px solid var(--border-color);
            border-radius: 6px; background: var(--bg-color); color: var(--text-color);
            box-sizing: border-box; font-size: 1rem;
        }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: var(--text-link); }

        {% block style_override %}{% endblock %}
    </style>
    {% block head %}{% endblock %}
</head>
<body {% if request.endpoint == 'home' and feed_type == 'sixs' %}style="overflow: hidden;"{% endif %}>
    
    {% if not (request.endpoint == 'home' and feed_type == 'sixs') %}
    <header class="top-bar">
        <h1 class="logo">{% block header_title %}Sixsec{% endblock %}</h1>
    </header>
    {% endif %}
    
    <main {% if not (request.endpoint == 'home' and feed_type == 'sixs') %}class="container"{% endif %}>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            <div style="padding: 0 15px;">
                {% for category, message in messages %}
                <div style="padding: 12px; border-radius: 6px; margin-bottom: 15px; background-color: {% if category == 'error' %}var(--red-color){% else %}var(--accent-color){% endif %}; color: white;">{{ message }}</div>
                {% endfor %}
            </div>
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>

    {% if current_user.is_authenticated and not (request.endpoint == 'home' and feed_type == 'sixs') %}
    <nav class="bottom-nav">
        <a href="{{ url_for('home') }}" class="{{ 'active' if request.endpoint == 'home' else '' }}">{{ ICONS.home|safe }}</a>
        <a href="{{ url_for('discover') }}" class="{{ 'active' if request.endpoint == 'discover' else '' }}">{{ ICONS.discover|safe }}</a>
        <a href="{{ url_for('create_post') }}" class="{{ 'active' if request.endpoint == 'create_post' else '' }}">{{ ICONS.create|safe }}</a>
        <a href="{{ url_for('profile', username=current_user.username) }}" class="{{ 'active' if request.endpoint == 'profile' else '' }}">{{ ICONS.profile|safe }}</a>
    </nav>
    {% endif %}
    
    <script>
    // API utilities, comment modal logic etc.
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
""",

"home.html": """
{% extends "layout.html" %}
{% block style_override %}
    {% if feed_type == 'sixs' %}
    /* TikTok UI Styles */
    #sixs-feed-container {
        height: 100vh;
        width: 100vw;
        overflow-y: scroll;
        scroll-snap-type: y mandatory;
        background-color: #000;
        position: fixed; top: 0; left: 0;
    }
    .six-video-slide {
        height: 100vh;
        width: 100vw;
        scroll-snap-align: start;
        position: relative;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .six-video-wrapper {
        position: relative;
        width: 100%;
        height: 100%;
        clip-path: circle(48% at 50% 50%);
    }
    .six-video {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    .six-ui-overlay {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        top: 0;
        color: white;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        padding: 15px;
        padding-bottom: 80px; /* Space for nav bar area */
        pointer-events: none;
        text-shadow: 1px 1px 3px rgba(0,0,0,0.7);
    }
    .six-info { pointer-events: auto; }
    .six-info .username { font-weight: bold; font-size: 1.1em; }
    .six-actions {
        display: flex;
        flex-direction: column;
        gap: 25px;
        pointer-events: auto;
    }
    .six-actions button {
        background: none; border: none; color: white;
        display: flex; flex-direction: column; align-items: center;
        gap: 5px; cursor: pointer;
    }
    .six-actions svg { width: 32px; height: 32px; }
    .six-actions .liked svg { fill: var(--red-color); stroke: var(--red-color); }
    .six-nav-overlay {
        position: fixed;
        bottom: 0; left: 0; right: 0;
        display: flex; justify-content: center;
        padding: 15px;
        gap: 50px;
        background: linear-gradient(to top, rgba(0,0,0,0.6), transparent);
    }
    .six-nav-overlay a { color: #aaa; font-weight: bold; font-size: 1.1em; }
    .six-nav-overlay a.active { color: white; }
    {% endif %}
{% endblock %}
{% block content %}
    {% if feed_type == 'text' %}
        <div class="feed-nav" style="padding: 0 15px; margin-bottom: 15px; display: flex; justify-content: space-around; border-bottom: 1px solid var(--border-color);">
            <a href="{{ url_for('home', feed_type='text') }}" style="flex:1; text-align:center; padding: 15px; color: var(--text-color); border-bottom: 2px solid var(--text-link);">Text</a>
            <a href="{{ url_for('home', feed_type='sixs') }}" style="flex:1; text-align:center; padding: 15px; color: var(--text-muted);">Sixs</a>
        </div>
        <div class="card-feed">
        {% for post in posts %}
            {% include 'post_card_text.html' %}
        {% else %}
            <div style="text-align:center; padding: 40px; color:var(--text-muted);">
                <h4>Your feed is empty.</h4>
                <p>Follow some accounts on the <a href="{{ url_for('discover') }}">Discover</a> page!</p>
            </div>
        {% endfor %}
        </div>

    {% elif feed_type == 'sixs' %}
        <div id="sixs-feed-container">
            {% for post in posts %}
            <section class="six-video-slide">
                <div class="six-video-wrapper">
                    <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop preload="auto"></video>
                </div>
                <div class="six-ui-overlay">
                    <div class="six-info">
                        <a href="{{ url_for('profile', username=post.author.username) }}" style="color:white;"><strong class="username">@{{ post.author.username }}</strong></a>
                        <p>{{ post.text_content }}</p>
                    </div>
                    <div class="six-actions">
                        <button id="like-btn-{{ post.id }}" onclick="handleLike(this, {{ post.id }})" class="{{ 'liked' if current_user in post.liked_by else '' }}">
                            {{ ICONS.like|safe }}
                            <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                        </button>
                        <button onclick="alert('Comments coming soon to this view!')">{{ ICONS.comment|safe }} <span>{{ post.comments.count() }}</span></button>
                        <form action="{{ url_for('repost', post_id=post.id) }}" method="POST" style="margin:0;"><button type="submit">{{ ICONS.repost|safe }}</button></form>
                    </div>
                </div>
            </section>
            {% else %}
            <section class="six-video-slide" style="flex-direction:column; text-align:center; color:white;">
                <h4>No Sixs to show!</h4>
                <p style="color:#aaa;">Follow more accounts or create your own.</p>
                <a href="{{ url_for('create_post') }}" class="btn btn-primary" style="margin-top:20px;">Create a Six</a>
            </section>
            {% endfor %}
        </div>
        <div class="six-nav-overlay">
            <a href="{{ url_for('home', feed_type='text') }}">Text</a>
            <a href="{{ url_for('home', feed_type='sixs') }}" class="active">Sixs</a>
        </div>
    {% endif %}
{% endblock %}
{% block scripts %}
{% if feed_type == 'sixs' %}
<script>
    const videos = document.querySelectorAll('.six-video');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.play();
            } else {
                entry.target.pause();
                entry.target.currentTime = 0;
            }
        });
    }, { threshold: 0.5 });

    videos.forEach(video => {
        observer.observe(video);
    });
    
    async function handleLike(button, postId) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        const likeCount = button.querySelector('span');
        likeCount.innerText = data.likes;
        button.classList.toggle('liked', data.liked);
    }
</script>
{% endif %}
{% endblock %}
""",

"post_card_text.html": """
<div class="card">
    <div class="post-card-content">
        <div class="post-header">
            {% if post.author.profile_pic and post.author.profile_pic != 'default.png' %}
                <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}" alt="pfp">
            {% else %}
                <div class="pfp pfp-placeholder" style="background: {{ post.author.pfp_gradient }};">{{ post.author.username[0]|upper }}</div>
            {% endif %}
            <div>
                <a href="{{ url_for('profile', username=post.author.username) }}" class="username">{{ post.author.username }}</a>
                <span class="timestamp">· {{ post.timestamp.strftime('%b %d') }}</span>
            </div>
        </div>
        <div class="post-content">
            <p>{{ post.text_content }}</p>
        </div>
    </div>
    <div class="post-actions">
        <button onclick="alert('Comments coming soon to this view!')">{{ ICONS.comment|safe }} <span>{{ post.comments.count() }}</span></button>
        <form action="{{ url_for('repost', post_id=post.id) }}" method="POST" style="margin:0;"><button type="submit">{{ ICONS.repost|safe }}</button></form>
        <button id="like-btn-{{ post.id }}" onclick="handleLikeText(this, {{ post.id }})" class="{{ 'liked' if current_user in post.liked_by else '' }}">
            {{ ICONS.like|safe }} <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
        </button>
    </div>
</div>
<script>
    async function handleLikeText(button, postId) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        const likeCount = button.querySelector('span');
        likeCount.innerText = data.likes;
        button.classList.toggle('liked', data.liked);
    }
</script>
""",
"create_post.html": """
{% extends "layout.html" %}
{% block header_title %}Create{% endblock %}
{% block content %}
    <div class="creator-tabs" style="display: flex; margin-bottom: 20px; border-radius: 8px; overflow:hidden; border: 1px solid var(--border-color);">
        <button id="tab-text" onclick="showTab('text')" class="active" style="flex: 1; padding: 12px; border: none; background: var(--primary-color); color: var(--text-color); font-weight: bold; cursor: pointer;">Text Post</button>
        <button id="tab-six" onclick="showTab('six')" style="flex: 1; padding: 12px; border: none; background: var(--bg-color); color: var(--text-muted); font-weight: bold; cursor: pointer;">Record a Six</button>
    </div>

    <div id="text-creator">
        <form method="POST">
            <input type="hidden" name="post_type" value="text">
            <div class="form-group">
                <textarea name="text_content" rows="5" maxlength="150" placeholder="What's happening?" required></textarea>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Post Text</button>
        </form>
    </div>

    <div id="six-creator" style="display: none; text-align: center;">
        <p id="recorder-status" style="color:var(--text-muted);">Allow camera access to start</p>
        <div style="width:100%; max-width: 400px; margin: 15px auto; aspect-ratio: 1/1; border-radius:50%; overflow:hidden; background:#000;">
            <video id="video-preview" autoplay muted playsinline style="width:100%; height:100%; object-fit:cover;"></video>
        </div>
        <button id="record-button" class="btn" disabled>Record</button>
        <form id="six-form-element" method="POST" enctype="multipart/form-data" style="display: none; margin-top: 20px;">
             <input type="hidden" name="post_type" value="six">
             <div class="form-group"> <input type="text" name="caption" maxlength="50" placeholder="Add a caption... (optional)"> </div>
             <button type="submit" class="btn btn-primary" style="width: 100%;">Post Six</button>
        </form>
    </div>
{% endblock %}
{% block scripts %}
<script>
    const textTabBtn = document.getElementById('tab-text');
    const sixTabBtn = document.getElementById('tab-six');
    let mediaRecorder; let recordedBlobs; let stream;
    const recordButton = document.getElementById('record-button');
    const preview = document.getElementById('video-preview');
    const sixForm = document.getElementById('six-form-element');
    const recorderStatus = document.getElementById('recorder-status');

    function showTab(tabName) {
        document.getElementById('text-creator').style.display = (tabName === 'text') ? 'block' : 'none';
        document.getElementById('six-creator').style.display = (tabName === 'six') ? 'block' : 'none';
        textTabBtn.style.background = (tabName === 'text') ? 'var(--primary-color)' : 'var(--bg-color)';
        textTabBtn.style.color = (tabName === 'text') ? 'var(--text-color)' : 'var(--text-muted)';
        sixTabBtn.style.background = (tabName === 'six') ? 'var(--primary-color)' : 'var(--bg-color)';
        sixTabBtn.style.color = (tabName === 'six') ? 'var(--text-color)' : 'var(--text-muted)';
        if (tabName === 'six' && !stream) { initCamera(); }
    }
    
    async function initCamera() {
        try {
            const constraints = { audio: true, video: { width: 480, height: 480, facingMode: "user" } };
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            preview.srcObject = stream;
            recorderStatus.textContent = "Ready to record a 6 second video.";
            recordButton.disabled = false;
        } catch (e) {
            recorderStatus.textContent = "Camera/Mic permission denied. Please allow in browser settings.";
            console.error('getUserMedia() error:', e);
        }
    }

    recordButton.addEventListener('click', () => {
        if (recordButton.textContent === 'Record') {
            startRecording();
        } else if (recordButton.textContent === 'Stop') {
            mediaRecorder.stop();
        } else if (recordButton.textContent === 'Re-record') {
            resetRecorder();
        }
    });

    function startRecording() {
        recordedBlobs = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
        mediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) recordedBlobs.push(e.data); };
        mediaRecorder.onstop = handleStop;
        mediaRecorder.start();
        recordButton.textContent = 'Stop';
        recordButton.classList.add('btn-danger');
        recorderStatus.textContent = 'Recording...';
        setTimeout(() => { if (mediaRecorder.state === "recording") mediaRecorder.stop(); }, 6000);
    }
    
    function handleStop() {
        recordButton.textContent = 'Re-record';
        recordButton.classList.remove('btn-danger');
        recorderStatus.textContent = 'Previewing...';
        const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
        preview.srcObject = null;
        preview.src = window.URL.createObjectURL(superBuffer);
        preview.muted = false;
        preview.controls = true;
        sixForm.style.display = 'block';
    }

    function resetRecorder() {
        sixForm.style.display = 'none';
        preview.srcObject = stream;
        preview.controls = false;
        preview.muted = true;
        recordButton.textContent = 'Record';
        recorderStatus.textContent = "Ready to record a 6 second video.";
    }

    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        formData.append('video_file', videoBlob, 'six-video.webm');
        sixForm.querySelector('button').disabled = true;
        sixForm.querySelector('button').textContent = "Uploading...";

        fetch("{{ url_for('create_post') }}", { method: 'POST', body: formData })
        .then(response => { if (response.redirected) window.location.href = response.url; })
        .catch(error => console.error('Error:', error));
    });
</script>
{% endblock %}
""",

"edit_profile.html": """
{% extends "layout.html" %}
{% block header_title %}Settings{% endblock %}
{% block content %}
    <h4>Edit Profile</h4>
    <form method="POST">
        <div class="form-group">
            <label for="bio">Bio</label>
            <textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea>
        </div>
        <button type="submit" class="btn btn-primary">Save Changes</button>
    </form>
    
    <hr style="border-color: var(--border-color); margin: 30px 0;">

    <h4>Account Actions</h4>
    <div style="border: 1px solid var(--red-color); border-radius: 8px; padding: 15px;">
        <h5 style="margin-top:0;">Delete Account</h5>
        <p style="color:var(--text-muted);">This action is permanent and cannot be undone. All your posts and data will be removed.</p>
        <form action="{{ url_for('delete_account') }}" method="POST">
             <div class="form-group">
                <label for="password">Confirm with your password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-danger" onclick="return confirm('Are you absolutely sure you want to delete your account? This is irreversible.')">Delete My Account</button>
        </form>
    </div>
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
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)
reposts = db.Table('reposts',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)
likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(150))
    profile_pic = db.Column(db.String(120), default='default.png')
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Post.user_id')
    reposts = db.relationship('Post', secondary=reposts, backref=db.backref('reposted_by', lazy='dynamic'), lazy='dynamic')
    followed = db.relationship('User', secondary=followers, primaryjoin=(followers.c.follower_id == id), secondaryjoin=(followers.c.followed_id == id), backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def follow(self, user):
        if not self.is_following(user): self.followed.append(user)
    def unfollow(self, user):
        if self.is_following(user): self.followed.remove(user)
    def is_following(self, user): return self.followed.filter(followers.c.followed_id == user.id).count() > 0
    def followed_posts(self, post_type=None):
        followed_ids = [u.id for u in self.followed]
        followed_ids.append(self.id)
        query = Post.query.filter(Post.user_id.in_(followed_ids))
        if post_type: query = query.filter_by(post_type=post_type)
        return query.order_by(Post.timestamp.desc()).all()
    
    @property
    def pfp_gradient(self):
        colors = [("#ef4444", "#fb923c"), ("#a855f7", "#ec4899"), ("#84cc16", "#22c55e"), ("#0ea5e9", "#6366f1")]
        c1, c2 = colors[hash(self.username) % len(colors)]
        return f"linear-gradient(45deg, {c1}, {c2})"

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(10), nullable=False)
    text_content = db.Column(db.String(150))
    video_filename = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    liked_by = db.relationship('User', secondary=likes, backref=db.backref('liked_posts', lazy='dynamic'), lazy='dynamic')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    user = db.relationship('User')

# --- ROUTES ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    posts = current_user.followed_posts(feed_type if feed_type == 'text' else 'six')
    # For simplicity, render home.html with logic to switch between text and sixs feed.
    for p in posts:
        p.liked_by_current_user = current_user in p.liked_by
    return render_template('home.html', posts=posts, feed_type=feed_type)

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
            caption = request.form.get('caption', '')
            if not video_file:
                flash('Video data not received.', 'error')
                return redirect(url_for('create_post'))
            filename = secure_filename(f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.webm")
            video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post = Post(post_type='six', text_content=caption, video_filename=filename, author=current_user)
        
        db.session.add(post)
        db.session.commit()
        flash('Post created!', 'success')
        return redirect(url_for('home'))

    return render_template('create_post.html')

@app.route('/profile/<username>')
@login_required
def profile(username):
    # This route and others like discover, auth etc. are largely unchanged functionally
    # and would use appropriately styled templates included in the dictionary.
    # For brevity, their logic remains, assuming the new templates handle the look.
    user = User.query.filter_by(username=username).first_or_404()
    # A simple combined feed for profile
    posts = user.posts.order_by(Post.timestamp.desc()).all()
    return render_template('profile.html', user=user, posts=posts)


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', current_user.bio)
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    password = request.form.get('password')
    if not current_user.check_password(password):
        flash('Incorrect password. Account not deleted.', 'error')
        return redirect(url_for('edit_profile'))
    
    # Manually delete related data for cascades
    Comment.query.filter_by(user_id=current_user.id).delete()
    db.session.query(likes).filter_by(user_id=current_user.id).delete()
    db.session.query(reposts).filter_by(user_id=current_user.id).delete()
    db.session.query(followers).filter((followers.c.follower_id == current_user.id) | (followers.c.followed_id == current_user.id)).delete()
    
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    flash('Your account has been permanently deleted.', 'success')
    return redirect(url_for('login'))

# Other routes like follow, like, repost, auth
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True)
            return redirect(url_for('home'))
        flash('Invalid username or password.', 'error')
    return render_template('auth_form.html', title="Login", form_type="login")

# Minimal set of remaining routes for a complete app
@app.route('/signup', methods=['GET', 'POST'])
def signup():
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
    return render_template('auth_form.html', title="Sign Up", form_type="signup")

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))
    
# These routes are simplified but functional for the demo
@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: current_user.follow(user); db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: current_user.unfollow(user); db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/repost/<int:post_id>', methods=['POST'])
@login_required
def repost(post_id):
    flash("Reposting is a premium feature... coming soon!", "info") # Placeholder
    return redirect(request.referrer or url_for('home'))
    
@app.route('/discover')
@login_required
def discover():
    # A simplified discover for brevity
    users = User.query.filter(User.id != current_user.id).order_by(db.func.random()).limit(10).all()
    return render_template('discover.html', users=users)

# For brevity, some templates are simplified or not included in the dictionary, but the structure is here.
# Add simplified discover and auth forms to the templates dictionary
templates['discover.html'] = """
{% extends "layout.html" %}
{% block header_title %}Discover{% endblock %}
{% block content %}
    {% for user in users %}
    <div class="card" style="padding:15px; display:flex; align-items:center; gap:15px; margin-bottom:10px;">
        <div class="pfp pfp-placeholder" style="width: 50px; height: 50px; background: {{ user.pfp_gradient }};">{{ user.username[0]|upper }}</div>
        <div style="flex-grow:1;">
            <a href="{{ url_for('profile', username=user.username) }}" class="username"><strong>{{ user.username }}</strong></a>
            <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ user.bio|truncate(50) if user.bio else 'No bio yet.' }}</p>
        </div>
        <div>{% if not current_user.is_following(user) %}<a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>{% endif %}</div>
    </div>
    {% endfor %}
{% endblock %}
"""
templates['auth_form.html'] = templates.get('auth_form.html', """
{% extends "layout.html" %}
{% block title %}{{ title }}{% endblock %}
{% block header_title %}{{ title }}{% endblock %}
{% block content %}
    <form method="POST">
        <div class="form-group"><label for="username">Username</label><input type="text" id="username" name="username" required></div>
        {% if form_type == 'signup' %}<div class="form-group"><label for="bio">Bio</label><textarea id="bio" name="bio" rows="3"></textarea></div>{% endif %}
        <div class="form-group"><label for="password">Password</label><input type="password" id="password" name="password" required></div>
        <button type="submit" class="btn btn-primary" style="width:100%;">{{ title }}</button>
    </form>
    <p style="text-align:center; margin-top:20px;">
        {% if form_type == 'login' %}
            Don't have an account? <a href="{{ url_for('signup') }}">Sign Up</a>
        {% else %}
            Already have an account? <a href="{{ url_for('login') }}">Login</a>
        {% endif %}
    </p>
{% endblock %}
""")
templates['profile.html'] = """
{% extends "layout.html" %}
{% block header_title %}{{ user.username }}{% endblock %}
{% block content %}
    <div style="padding: 15px; text-align: center;">
        <div class="pfp pfp-placeholder" style="width: 90px; height: 90px; margin: auto; font-size: 2.5rem; background: {{ user.pfp_gradient }};">{{ user.username[0]|upper }}</div>
        <h2 style="margin-bottom: 5px;">{{ user.username }}</h2>
        <p style="color: var(--text-muted); margin-top:0;">{{ user.bio or "No bio yet." }}</p>
        <div style="margin-top:15px;">
            {% if current_user != user %}
                {% if not current_user.is_following(user) %} <a href="{{ url_for('follow', username=user.username) }}" class="btn btn-primary">Follow</a>
                {% else %} <a href="{{ url_for('unfollow', username=user.username) }}" class="btn">Following</a> {% endif %}
            {% else %}
                 <a href="{{ url_for('edit_profile') }}" class="btn">Edit Profile</a>
            {% endif %}
        </div>
    </div>
    <div style="display: flex; justify-content: space-around; text-align: center; padding: 15px; border-top: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color);">
        <div><strong>{{ user.posts.count() }}</strong><br><span style="color:var(--text-muted);">Posts</span></div>
        <div><strong>{{ user.followers.count() }}</strong><br><span style="color:var(--text-muted);">Followers</span></div>
        <div><strong>{{ user.followed.count() }}</strong><br><span style="color:var(--text-muted);">Following</span></div>
    </div>
    {% for post in user.posts.order_by(Post.timestamp.desc()).all() %}
        {% include 'post_card_text.html' %}
    {% else %}
        <p style="text-align:center; color:var(--text-muted); padding:20px;">No posts yet.</p>
    {% endfor %}
{% endblock %}
"""


# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')):
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'))
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)