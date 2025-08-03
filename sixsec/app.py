import os
import datetime
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required,- \
    confirm_login, fresh_login_required
from jinja2 import BaseLoader, TemplateNotFound

# --- APP CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secure_and_persistent_sixsec_key'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=30) # Keep users logged in for 30 days
app.config['REMEMBER_COOKIE_SECURE'] = True # Ensures cookie is only sent over HTTPS
app.config['REMEMBER_COOKIE_HTTPONLY'] = True

# --- INITIALIZE EXTENSIONS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.refresh_view = 'login'
login_manager.needs_refresh_message = u"Please re-authenticate to access this page."

# --- SVG ICONS DICTIONARY ---
ICONS = {
    'home': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    'discover': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    'create': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>',
    'profile': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    'like': '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    'comment': '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    'repost': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
    'send': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>',
    'back': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>'
}
app.jinja_env.globals.update(ICONS=ICONS)

# --- TEMPLATES DICTIONARY ---
templates = {
"layout.html": """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, user-scalable=no, viewport-fit=cover">
    <title>{% block title %}Sixsec{% endblock %}</title>
    <style>
        :root {
            --bg-color: #0d0d0d;
            --card-color: #1a1a1a;
            --glass-color: rgba(26, 26, 26, 0.6);
            --border-color: #2c2c2c;
            --accent-color: #00bfff; /* Deep sky blue */
            --text-color: #e0e0e0;
            --text-muted: #888888;
        }
        html { -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0; background-color: var(--bg-color); color: var(--text-color); 
            font-size: 16px; padding-top: 60px; padding-bottom: 70px;
        }
        .container { max-width: 600px; margin: 0 auto; padding: 0 15px; }
        a { color: var(--accent-color); text-decoration: none; }
        
        .top-bar {
            position: fixed; top: 0; left: 0; right: 0;
            z-index: 1000;
            background: var(--glass-color);
            backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            padding: 10px 15px; border-bottom: 1px solid var(--border-color);
            display: flex; align-items: center; height: 40px;
        }
        .top-bar .logo {
            font-weight: bold; font-size: 1.8em; color: var(--text-color); letter-spacing: -1px;
            position: absolute; left: 50%; transform: translateX(-50%);
        }
        .top-bar-back { position: absolute; left: 15px; }

        .bottom-nav { 
            position: fixed; bottom: 0; left: 0; right: 0;
            background: var(--glass-color); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
            border-top: 1px solid var(--border-color);
            display: flex; justify-content: space-around; padding: 10px 0;
            padding-bottom: env(safe-area-inset-bottom, 10px); z-index: 1000; 
        }
        .bottom-nav a { color: var(--text-muted); transition: color 0.2s ease, transform 0.2s ease; }
        .bottom-nav a.active { color: var(--text-color); transform: scale(1.1); }
        .bottom-nav a svg { width: 28px; height: 28px; }

        .card {
            background: var(--card-color);
            border: 1px solid var(--border-color);
            border-radius: 12px; padding: 15px; margin-bottom: 15px;
        }
        
        .btn {
            background-color: var(--accent-color); color: #fff; padding: 12px 20px;
            border: none; border-radius: 30px; cursor: pointer;
            font-weight: bold; transition: background-color 0.2s ease;
        }
        .btn:hover { background-color: #009acd; }
        .btn-secondary { background: var(--border-color); color: var(--text-color); }
        .btn-danger { background: #d9534f; }

        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: .5rem; color: var(--text-muted); }
        .form-group input, .form-group textarea {
            width: 100%; padding: 12px; border: 1px solid var(--border-color); border-radius: 8px;
            background: var(--bg-color); color: var(--text-color);
            box-sizing: border-box; font-size: 1rem;
        }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: var(--accent-color); }
        
        .modal {
            display: none; position: fixed; z-index: 2000; left: 0; top: 0;
            width: 100%; height: 100%; background-color: rgba(0,0,0,0.7);
            align-items: flex-end;
        }
        .modal-content {
            background-color: var(--card-color); border-radius: 20px 20px 0 0;
            width: 100%; max-width: 600px; height: 75vh;
            display: flex; flex-direction: column; animation: slideUp 0.3s ease;
        }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        .modal-header { padding: 15px; border-bottom: 1px solid var(--border-color); text-align: center; position: relative; }
        .modal-header .close { position: absolute; left: 15px; top: 10px; font-size: 24px; cursor: pointer; color: var(--text-muted); }
        .modal-body { flex-grow: 1; padding: 15px; overflow-y: auto; }
        .modal-footer { padding: 10px; border-top: 1px solid var(--border-color); }
        .comment-form { display: flex; gap: 10px; }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
    {% if not immersive %}
    <header class="top-bar">
        {% if back_url %}
        <a href="{{ back_url }}" class="top-bar-back">{{ ICONS.back|safe }}</a>
        {% endif %}
        <div class="logo">{% block header_title %}Sixsec{% endblock %}</div>
    </header>
    {% endif %}
    
    <main class="{% if not immersive %}container{% endif %}">
        {% block content %}{% endblock %}
    </main>

    {% if current_user.is_authenticated and not immersive %}
    <nav class="bottom-nav">
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
          <form id="comment-form" class="comment-form">
            <input type="text" id="comment-text-input" class="form-group" placeholder="Add a comment..." required style="margin:0;">
            <input type="hidden" id="comment-post-id">
            <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
          </form>
        </div>
      </div>
    </div>
    
    <script>
    const commentModal = document.getElementById('commentModal');
    // JS for comments, etc. remains the same, but it's good practice to keep it here.
    async function openCommentModal(postId) {
        commentModal.style.display = 'flex';
        // ... (rest of the comment JS as in previous version)
    }
    function closeCommentModal() { commentModal.style.display = 'none'; }
    // Add event listeners for form submission and closing modal on background click
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
""",

"home_text.html": """
{% extends "layout.html" %}
{% block head %}
<style>
    .feed-switcher { padding: 15px 0; text-align: center; }
</style>
{% endblock %}
{% block content %}
    <div class="feed-switcher">
        <a href="{{ url_for('home', feed_type='sixs') }}" style="color:var(--text-muted); font-weight: bold;">Switch to Sixs</a>
    </div>
    {% for post in posts %}
        {% include 'post_card_text.html' %}
    {% else %}
        <div class="card" style="text-align:center; color:var(--text-muted);">
            <p>Your feed is empty.</p>
            <p>Follow some accounts on the <a href="{{ url_for('discover') }}">Discover</a> page!</p>
        </div>
    {% endfor %}
{% endblock %}
""",

"post_card_text.html": """
<div class="card">
    <div style="display: flex; align-items: flex-start; gap: 12px;">
        {% if post.author.profile_pic and post.author.profile_pic != 'default.png' %}
            <img src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}" alt="pfp" style="width:40px; height:40px; border-radius:50%;">
        {% else %}
            <div style="width:40px; height:40px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold; background-color:{{ post.author.pfp_bg }}; flex-shrink:0;">{{ post.author.username[0]|upper }}</div>
        {% endif %}
        <div style="flex-grow:1;">
            <div style="display:flex; gap: 8px; align-items:center;">
                <a href="{{ url_for('profile', username=post.author.username) }}" style="font-weight:bold; color:var(--text-color);">{{ post.author.username }}</a>
                <span style="color:var(--text-muted);">· {{ post.timestamp.strftime('%b %d') }}</span>
            </div>
            <p style="margin-top:5px; line-height:1.4;">{{ post.text_content }}</p>
            <div style="display:flex; justify-content:space-between; margin-top:15px; max-width: 300px; color:var(--text-muted);">
                <button onclick="openCommentModal({{ post.id }})" style="background:none; border:none; color:inherit; cursor:pointer; display:flex; align-items:center; gap:8px;">
                    {{ ICONS.comment|safe }} <span>{{ post.comments.count() }}</span>
                </button>
                <form action="{{ url_for('repost', post_id=post.id) }}" method="POST" style="margin:0; padding:0;">
                     <button type="submit" style="background:none; border:none; color:inherit; cursor:pointer; display:flex; align-items:center; gap:8px;">{{ ICONS.repost|safe }}</button>
                </form>
                <button onclick="handleLike({{ post.id }})" id="like-btn-{{ post.id }}" class="{{ 'liked' if current_user in post.liked_by else '' }}" style="background:none; border:none; color:inherit; cursor:pointer; display:flex; align-items:center; gap:8px;">
                    {{ ICONS.like|safe }} <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                </button>
            </div>
        </div>
    </div>
</div>
""",

"home_sixs.html": """
{% extends "layout.html" %}
{% set immersive = True %}
{% block head %}
<style>
    body { background: #000; padding: 0; }
    .sixs-container { height: 100vh; scroll-snap-type: y mandatory; overflow-y: scroll; }
    .six-item {
        height: 100vh; width: 100vw;
        scroll-snap-align: start;
        position: relative;
        display: flex; align-items: center; justify-content: center;
    }
    .video-wrapper {
        position: relative;
        width: 100vw; height: 100vw; max-width: 600px; max-height: 600px; /* Desktop constraint */
    }
    .six-video {
        width: 100%; height: 100%; object-fit: cover;
        border-radius: 50%;
    }
    .six-overlay {
        position: absolute; bottom: 80px; left: 15px;
        color: white; text-shadow: 1px 1px 3px rgba(0,0,0,0.7);
    }
    .six-actions {
        position: absolute; right: 10px; bottom: 80px;
        display: flex; flex-direction: column; align-items: center; gap: 20px;
    }
    .six-actions button {
        background: none; border: none; color: white; cursor: pointer;
        display: flex; flex-direction: column; align-items: center; text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
    }
    .six-actions .liked svg { fill: #ff4040; stroke: #ff4040; }
    .top-feed-switcher {
        position: fixed; top: 15px; left: 50%; transform: translateX(-50%);
        z-index: 100;
        background: rgba(0,0,0,0.3); padding: 5px 15px; border-radius: 20px;
    }
</style>
{% endblock %}
{% block content %}
    <div class="top-feed-switcher">
        <a href="{{ url_for('home', feed_type='text') }}" style="color:var(--text-muted); font-weight:bold;">Texts</a> | 
        <span style="color:var(--text-color); font-weight:bold;">Sixs</span>
    </div>
    <div class="sixs-container" id="sixs-container">
    {% for post in posts %}
        <div class="six-item">
            <div class="video-wrapper">
                <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop playsinline data-post-id="{{ post.id }}"></video>
            </div>
            <div class="six-overlay">
                <a href="{{ url_for('profile', username=post.author.username) }}" style="font-weight:bold; color:white;">@{{ post.author.username }}</a>
                <p>{{ post.text_content }}</p>
            </div>
            <div class="six-actions">
                <button id="like-btn-{{ post.id }}" onclick="handleLike({{ post.id }})" class="{{ 'liked' if current_user in post.liked_by else '' }}">
                    {{ ICONS.like|safe }}
                    <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                </button>
                <button onclick="openCommentModal({{ post.id }})">
                    {{ ICONS.comment|safe }}
                    <span>{{ post.comments.count() }}</span>
                </button>
            </div>
        </div>
    {% else %}
        <div class="six-item" style="flex-direction:column; text-align:center;">
            <p>No Sixs to watch.</p>
            <a href="{{ url_for('create_post') }}" class="btn">Create one now</a>
        </div>
    {% endfor %}
    </div>
{% endblock %}
{% block scripts %}
<script>
    document.addEventListener('DOMContentLoaded', () => {
        const videos = document.querySelectorAll('.six-video');
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.play().catch(e => console.error("Autoplay failed:", e));
                } else {
                    entry.target.pause();
                }
            });
        }, { threshold: 0.5 });

        videos.forEach(video => {
            observer.observe(video);
        });
    });
</script>
{% endblock %}
""",

"create_post.html": """
{% extends "layout.html" %}
{% set back_url = url_for('home') %}
{% block header_title %}Create{% endblock %}
{% block content %}
    <div class="card">
        <form id="text-form-element" method="POST">
            <input type="hidden" name="post_type" value="text">
            <div class="form-group">
                <textarea name="text_content" rows="5" maxlength="150" placeholder="What's happening?" required></textarea>
            </div>
            <button type="submit" class="btn" style="width: 100%;">Post Text</button>
        </form>
    </div>
    <div style="text-align:center; margin: 20px 0; color:var(--text-muted);">OR</div>
    <div class="card">
         <a href="{{ url_for('create_six') }}" class="btn" style="width: 100%; text-align:center; display:block; box-sizing: border-box;">Record a Six</a>
    </div>
{% endblock %}
""",

"create_six.html": """
{% extends "layout.html" %}
{% set immersive = True %}
{% block content %}
<div id="recorder-ui" style="height:100vh; width:100vw; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#000; position:relative;">
    <a href="{{ url_for('create_post') }}" style="position:absolute; top:20px; left:20px; color:white; z-index:10;">{{ ICONS.back|safe }}</a>
    <p id="recorder-status" style="color:white; position:absolute; top:60px;">Tap to Record</p>
    <video id="video-preview" style="width:90vw; height:90vw; max-width:500px; max-height:500px; border-radius:50%; object-fit:cover;"></video>
    <div id="controls" style="position:absolute; bottom:50px; text-align:center;">
        <button id="record-button" style="width:70px; height:70px; border-radius:50%; border:4px solid white; background-color: #f04d4d; cursor:pointer;"></button>
    </div>
</div>
<div id="preview-ui" style="display:none; height:100vh; width:100vw; background:#000; display:flex; flex-direction:column; align-items:center; justify-content:center;">
    <video id="final-video" controls style="width:90vw; height:90vw; max-width:500px; max-height:500px; border-radius:50%; object-fit:cover;"></video>
    <form id="six-form-element" method="POST" enctype="multipart/form-data" style="margin-top:20px; width:90%; max-width:500px;">
         <input type="hidden" name="post_type" value="six">
         <div class="form-group">
            <input type="text" name="caption" maxlength="50" placeholder="Add a caption..." style="text-align:center;">
         </div>
         <button type="submit" class="btn" style="width: 100%;">Post</button>
         <button type="button" onclick="retakeVideo()" class="btn btn-secondary" style="width:100%; margin-top:10px;">Retake</button>
    </form>
</div>
{% endblock %}
{% block scripts %}
<script>
    const recorderUI = document.getElementById('recorder-ui');
    const previewUI = document.getElementById('preview-ui');
    const recordButton = document.getElementById('record-button');
    const videoPreview = document.getElementById('video-preview');
    const finalVideo = document.getElementById('final-video');
    const sixForm = document.getElementById('six-form-element');
    const recorderStatus = document.getElementById('recorder-status');

    let mediaRecorder;
    let recordedBlobs;
    let stream;
    
    async function startCamera() {
        const constraints = { audio: true, video: { width: 480, height: 480, facingMode: "user" } };
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            videoPreview.srcObject = stream;
            videoPreview.play();
        } catch (e) {
            recorderStatus.textContent = "Camera permission denied.";
        }
    }

    function stopCamera() {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
    }

    recordButton.addEventListener('click', () => {
        if (!mediaRecorder || mediaRecorder.state === "inactive") {
            startRecording();
        } else {
            stopRecording();
        }
    });

    function startRecording() {
        if (!stream) return;
        recordedBlobs = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
        mediaRecorder.onstop = handleStop;
        mediaRecorder.ondataavailable = handleDataAvailable;
        mediaRecorder.start();
        recorderStatus.textContent = "Recording...";
        recordButton.style.backgroundColor = "#4caf50";
        setTimeout(stopRecording, 6000);
    }
    
    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
        }
    }

    function handleDataAvailable(event) {
        if (event.data && event.data.size > 0) {
            recordedBlobs.push(event.data);
        }
    }

    function handleStop() {
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        finalVideo.src = window.URL.createObjectURL(videoBlob);
        recorderUI.style.display = 'none';
        previewUI.style.display = 'flex';
        stopCamera();
    }
    
    function retakeVideo() {
        previewUI.style.display = 'none';
        recorderUI.style.display = 'flex';
        startCamera();
    }

    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        formData.append('video_file', videoBlob, 'six-video.webm');
        
        const submitBtn = sixForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = "Uploading...";

        fetch("{{ url_for('create_six_post') }}", { method: 'POST', body: formData })
        .then(response => {
            if (response.redirected) {
                window.location.href = response.url;
            } else {
                 submitBtn.disabled = false;
                 submitBtn.textContent = "Post";
                 alert("Something went wrong!");
            }
        })
        .catch(error => console.error('Error:', error));
    });

    startCamera(); // Immediately ask for camera on page load
</script>
{% endblock %}
""",

"edit_profile.html": """
{% extends "layout.html" %}
{% set back_url = url_for('profile', username=current_user.username) %}
{% block header_title %}Edit Profile{% endblock %}
{% block content %}
<div class="card">
    <form method="POST">
        <div class="form-group">
            <label for="bio">Bio</label>
            <textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea>
        </div>
        <button type="submit" class="btn" style="width:100%;">Save Changes</button>
    </form>
</div>
<div class="card">
    <h4>Account Actions</h4>
    <form method="POST" action="{{ url_for('delete_account') }}" onsubmit="return confirm('Are you absolutely sure? This will permanently delete your account, posts, and comments. This action cannot be undone.');">
        <button type="submit" class="btn btn-danger" style="width:100%;">Delete Account</button>
    </form>
</div>
{% endblock %}
"""
} # Add other templates like discover, profile, auth_form following the new design

# --- JINJA2 CUSTOM LOADER ---
class DictLoader(BaseLoader):
    def __init__(self, templates_dict): self.templates = templates_dict
    def get_source(self, environment, template):
        if template in self.templates: return self.templates[template], None, lambda: True
        raise TemplateNotFound(template)
app.jinja_loader = DictLoader(templates)

# --- DATABASE MODELS ---
# Models for User, Post, Comment and relationship tables (followers, likes, reposts)
# ... (Models are identical to previous version, I'll put them here for completeness)
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
    posts = db.relationship('Post', backref='author', lazy='dynamic', foreign_keys='Post.user_id', cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='commenter', lazy='dynamic', cascade="all, delete-orphan")
    reposts = db.relationship('Post', secondary=reposts, backref=db.backref('reposted_by', lazy='dynamic'), lazy='dynamic')
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
        followed_ids = [u.id for u in self.followed]
        followed_ids.append(self.id)
        query = Post.query.filter(Post.user_id.in_(followed_ids))
        if post_type: query = query.filter_by(post_type=post_type)
        return query.order_by(Post.timestamp.desc()).all()
    
    @property
    def pfp_bg(self):
        colors = ["#e57373", "#f06292", "#ba68c8", "#9575cd", "#7986cb", "#64b5f6", "#4fc3f7", "#4dd0e1", "#4db6ac", "#81c784", "#aed581", "#ff8a65", "#d4e157", "#ffd54f", "#ffb74d"]
        return colors[hash(self.username) % len(colors)]

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

# --- ROUTES ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    # Users can choose a default feed in settings later, for now default to 'sixs'
    feed_type = request.args.get('feed_type', 'sixs')
    if feed_type == 'text':
        posts = current_user.followed_posts('text')
        return render_template('home_text.html', posts=posts)
    else: # 'sixs'
        posts = current_user.followed_posts('six')
        return render_template('home_sixs.html', posts=posts)

@app.route('/create')
@login_required
def create_post():
    return render_template('create_post.html')

@app.route('/create/six')
@login_required
def create_six():
    return render_template('create_six.html')

@app.route('/create/text_post', methods=['POST'])
@login_required
def create_text_post():
    content = request.form.get('text_content')
    if not content or len(content) > 150:
        flash('Invalid text content.', 'error')
        return redirect(url_for('create_post'))
    post = Post(post_type='text', text_content=content, author=current_user)
    db.session.add(post)
    db.session.commit()
    flash('Post created!', 'success')
    return redirect(url_for('home', feed_type='text'))

@app.route('/create/six_post', methods=['POST'])
@login_required
def create_six_post():
    video_file = request.files.get('video_file')
    caption = request.form.get('caption', '')
    if not video_file:
        flash('Video data not received.', 'error')
        return redirect(url_for('create_six'))
    
    filename = secure_filename(f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.webm")
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    video_file.save(video_path)
    post = Post(post_type='six', text_content=caption, video_filename=filename, author=current_user)
    db.session.add(post)
    db.session.commit()
    return redirect(url_for('home', feed_type='sixs'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            # Use remember=True to set the persistent cookie
            login_user(user, remember=True)
            return redirect(url_for('home'))
        flash('Invalid username or password.', 'error')
    return render_template('auth_form.html') # A simplified generic auth form might be better

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
@fresh_login_required # Make sure user recently logged in
def delete_account():
    # Cascading deletes in the User model will handle posts and comments
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    flash('Your account has been permanently deleted.', 'success')
    return redirect(url_for('home'))

# Other routes like signup, profile, discover, like, follow, etc.
# These would be largely the same as the previous version, adapted for the new templates.
# ...

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        # A simple way to add templates that are not directly rendered but included
        app.jinja_loader.templates['auth_form.html'] = templates['layout.html'].replace('{% block content %}', '...auth form content...').replace('{% endblock %}', '')
        
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')):
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'))
        db.create_all()
    # Note: For production, use a proper WSGI server instead of app.run()
    # For local testing with HTTPS (needed for camera), you can use `ssl_context='adhoc'`
    # but cloudflared is a better approach.
    app.run(debug=True, host='0.0.0.0', port=8000)