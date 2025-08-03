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
app.config['SECRET_KEY'] = 'a-very-secret-modern-key-for-sixsec'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
# Limit upload size to prevent large video uploads (e.g., 16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- INITIALIZE EXTENSIONS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- SVG ICONS DICTIONARY ---
ICONS = {
    'home': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    'discover': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    'create': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"></path><path d="M5 12h14"></path></svg>',
    'profile': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    'like': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    'comment': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    'repost': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
    'send': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>'
}
app.jinja_env.globals.update(ICONS=ICONS)


# --- TEMPLATES (as a dictionary) ---
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
            --bg-color: #1a1a1d;
            --primary-color: #27272b;
            --secondary-color: #4e4e50;
            --accent-color: #66fcf1;
            --text-color: #c5c6c7;
            --text-muted: #8a8d93;
            --shadow-light: #2c2c31;
            --shadow-dark: #0e0e10;
        }
        html { -webkit-tap-highlight-color: transparent; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0; 
            background-color: var(--bg-color); 
            color: var(--text-color); 
            font-size: 16px;
            padding-bottom: 70px; /* Space for bottom nav */
        }
        .container { max-width: 600px; margin: 0 auto; padding: 15px; }
        a { color: var(--accent-color); text-decoration: none; }
        
        /* Glassmorphism Top Bar */
        .top-bar {
            position: sticky; top: 0; z-index: 1000;
            background: rgba(26, 26, 29, 0.7);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            padding: 10px 15px;
            border-bottom: 1px solid var(--primary-color);
            display: flex; justify-content: space-between; align-items: center;
        }
        .top-bar .logo {
            font-weight: bold; font-size: 1.8em; color: var(--accent-color);
            text-shadow: 0 0 5px rgba(102, 252, 241, 0.5);
        }

        /* Mobile Bottom Nav Bar */
        .bottom-nav { 
            position: fixed; bottom: 0; left: 0; right: 0;
            background: rgba(26, 26, 29, 0.8);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border-top: 1px solid var(--primary-color);
            display: flex; justify-content: space-around;
            padding: 10px 0; z-index: 1000; 
        }
        .bottom-nav a { 
            color: var(--text-muted); 
            transition: color 0.2s ease, transform 0.2s ease; 
        }
        .bottom-nav a.active { 
            color: var(--accent-color);
            transform: scale(1.1);
        }
        .bottom-nav a svg { width: 28px; height: 28px; }

        /* Neomorphism Card Style */
        .card {
            background: var(--primary-color);
            border-radius: 15px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 5px 5px 10px var(--shadow-dark), -5px -5px 10px var(--shadow-light);
        }
        
        /* Post Styling */
        .post-header { display: flex; align-items: center; margin-bottom: 12px; }
        .post-header .pfp { width: 45px; height: 45px; border-radius: 50%; margin-right: 12px; object-fit: cover; }
        .post-header .pfp-placeholder { display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 1.2rem; background-color: var(--secondary-color); }
        .post-header .username { font-weight: bold; }
        .post-header .timestamp { font-size: 0.8em; color: var(--text-muted); }
        .post-content p { white-space: pre-wrap; word-wrap: break-word; line-height: 1.5; }
        .post-actions { display: flex; justify-content: space-around; padding-top: 12px; margin-top: 12px; border-top: 1px solid var(--secondary-color); }
        .post-actions button { background: none; border: none; cursor: pointer; color: var(--text-muted); display: flex; align-items: center; gap: 8px; font-size: 0.9em; transition: color 0.2s ease; }
        .post-actions button:hover, .post-actions button.liked, .post-actions button.reposted { color: var(--accent-color); }
        .post-actions svg { width: 20px; height: 20px; }
        
        /* Circle Videos */
        .six-video-container {
            width: 100%;
            padding-top: 100%; /* 1:1 Aspect Ratio */
            position: relative;
            margin: 15px 0;
            border-radius: 50%;
            overflow: hidden;
            background: #000;
            box-shadow: inset 0 0 15px rgba(0,0,0,0.5);
        }
        .six-video {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            object-fit: cover;
        }

        /* Forms & Buttons */
        .btn {
            background: var(--primary-color);
            color: var(--accent-color);
            padding: 12px 20px;
            border: 1px solid var(--secondary-color);
            border-radius: 30px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            font-weight: bold;
            box-shadow: 3px 3px 6px var(--shadow-dark), -3px -3px 6px var(--shadow-light);
            transition: all 0.2s ease-in-out;
        }
        .btn:active {
             box-shadow: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light);
             transform: translateY(1px);
        }
        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: .5rem; color: var(--text-muted); }
        .form-group input, .form-group textarea {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            background: var(--primary-color);
            color: var(--text-color);
            box-shadow: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light);
            box-sizing: border-box;
            font-size: 1rem;
        }
        .form-group input:focus, .form-group textarea:focus { outline: 1px solid var(--accent-color); }

        /* Modal for Comments */
        .modal {
            display: none; position: fixed; z-index: 2000; left: 0; top: 0;
            width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.7);
            align-items: flex-end;
        }
        .modal-content {
            background-color: var(--bg-color);
            margin: auto auto 0 auto;
            border-radius: 20px 20px 0 0;
            width: 100%; max-width: 600px;
            height: 75vh;
            display: flex; flex-direction: column;
            animation: slideUp 0.3s ease;
        }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        .modal-header { padding: 15px; border-bottom: 1px solid var(--primary-color); text-align: center; position: relative; }
        .modal-header .close { position: absolute; left: 15px; top: 10px; font-size: 24px; font-weight: bold; cursor: pointer; }
        .modal-body { flex-grow: 1; padding: 15px; overflow-y: auto; }
        .modal-footer { padding: 10px; border-top: 1px solid var(--primary-color); }
        .comment-form { display: flex; gap: 10px; }
        #comment-text-input { flex-grow: 1; }
        
        /* Page specific styles */
        .feed-nav { display: flex; justify-content: center; margin-bottom: 20px; gap: 15px; }
        .feed-nav a { padding: 8px 18px; border-radius: 20px; background: var(--primary-color); color: var(--text-muted); font-weight: bold; box-shadow: 3px 3px 6px var(--shadow-dark), -3px -3px 6px var(--shadow-light); }
        .feed-nav a.active { background: var(--accent-color); color: var(--bg-color); box-shadow: none; }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
    <div class="top-bar">
        <div class="logo">Sixsec</div>
    </div>
    
    <main class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="card" style="background-color: {% if category == 'error' %}#8c3b3b{% else %}#3b8c5a{% endif %};">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>

    {% if current_user.is_authenticated %}
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
        <div class="modal-body" id="comment-list">
            <!-- Comments will be loaded here -->
        </div>
        <div class="modal-footer">
          <form id="comment-form" class="comment-form">
            <input type="text" id="comment-text-input" class="form-group" placeholder="Add a comment..." required>
            <input type="hidden" id="comment-post-id">
            <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
          </form>
        </div>
      </div>
    </div>
    
    <script>
    const commentModal = document.getElementById('commentModal');
    const commentList = document.getElementById('comment-list');
    const commentForm = document.getElementById('comment-form');
    const commentPostIdInput = document.getElementById('comment-post-id');
    const commentTextInput = document.getElementById('comment-text-input');

    async function openCommentModal(postId) {
        commentPostIdInput.value = postId;
        commentList.innerHTML = '<p>Loading comments...</p>';
        commentModal.style.display = 'flex';
        
        const response = await fetch(`/post/${postId}/comments`);
        const comments = await response.json();
        
        commentList.innerHTML = '';
        if (comments.length === 0) {
            commentList.innerHTML = '<p style="text-align:center; color: var(--text-muted);">No comments yet.</p>';
        } else {
            comments.forEach(comment => {
                const div = document.createElement('div');
                div.className = 'card'; // Re-use card style for comments
                div.innerHTML = `<div class="post-header">
                                     <div class="pfp pfp-placeholder" style="width:35px; height:35px; background-color:${comment.user.pfp_bg};">${comment.user.initial}</div>
                                     <div>
                                         <span class="username">${comment.user.username}</span>
                                         <div class="timestamp">${comment.timestamp}</div>
                                     </div>
                                 </div>
                                 <p>${comment.text}</p>`;
                commentList.appendChild(div);
            });
        }
    }

    function closeCommentModal() {
        commentModal.style.display = 'none';
    }

    commentForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const postId = commentPostIdInput.value;
        const text = commentTextInput.value;
        
        if (!text.trim()) return;

        const response = await fetch(`/post/${postId}/comment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        
        if (response.ok) {
            commentTextInput.value = '';
            openCommentModal(postId); // Refresh comments
        } else {
            alert('Failed to post comment.');
        }
    });

    window.onclick = function(event) {
        if (event.target == commentModal) {
            closeCommentModal();
        }
    }
    
    // Generic API call function for likes, reposts etc.
    async function postAction(url) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        return await response.json();
    }

    async function handleLike(postId) {
        const data = await postAction(`/like/${postId}`);
        const likeButton = document.getElementById(`like-btn-${postId}`);
        const likeCount = document.getElementById(`like-count-${postId}`);
        likeCount.innerText = data.likes;
        likeButton.classList.toggle('liked', data.liked);
    }
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
""",
"post_card.html": """
<div class="card post-card" id="post-{{ post.id }}">
    <div class="post-header">
        {% if post.author.profile_pic and post.author.profile_pic != 'default.png' %}
            <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}" alt="pfp">
        {% else %}
            <div class="pfp pfp-placeholder" style="background-color:{{ post.author.pfp_bg }};">{{ post.author.username[0]|upper }}</div>
        {% endif %}
        <div>
            <a href="{{ url_for('profile', username=post.author.username) }}" class="username">{{ post.author.username }}</a>
            <div class="timestamp">{{ post.timestamp.strftime('%b %d, %Y') }}</div>
        </div>
    </div>
    <div class="post-content">
        <p>{{ post.text_content }}</p>
        {% if post.post_type == 'six' and post.video_filename %}
            <div class="six-video-container">
                <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop muted playsinline controls></video>
            </div>
        {% endif %}
    </div>
    <div class="post-actions">
        <button id="like-btn-{{ post.id }}" onclick="handleLike({{ post.id }})" class="{{ 'liked' if current_user in post.liked_by else '' }}">
            {{ ICONS.like|safe }} <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
        </button>
        <button onclick="openCommentModal({{ post.id }})">
            {{ ICONS.comment|safe }} <span>{{ post.comments.count() }}</span>
        </button>
        <form action="{{ url_for('repost', post_id=post.id) }}" method="POST" style="margin:0; padding:0;">
             <button type="submit">{{ ICONS.repost|safe }}</button>
        </form>
    </div>
</div>
""",
"create_post.html": """
{% extends "layout.html" %}
{% block title %}Create - Sixsec{% endblock %}
{% block head %}
<style>
    .creator-tabs { display: flex; margin-bottom: 20px; background: var(--primary-color); border-radius: 12px; padding: 5px; box-shadow: inset 3px 3px 6px var(--shadow-dark), inset -3px -3px 6px var(--shadow-light); }
    .creator-tabs button { flex: 1; padding: 10px; border: none; background: transparent; color: var(--text-muted); font-weight: bold; font-size: 1rem; cursor: pointer; border-radius: 8px; transition: all 0.3s ease; }
    .creator-tabs button.active { background: var(--secondary-color); color: var(--accent-color); }
    #six-recorder { text-align: center; }
    #video-preview { width: 100%; max-width: 300px; border-radius: 50%; aspect-ratio: 1/1; object-fit: cover; margin: 15px auto; background: #000; }
    .record-btn {
        width: 70px; height: 70px; border-radius: 50%; border: 4px solid white; background-color: #f04d4d;
        cursor: pointer; position: relative;
    }
    .record-btn.recording::after {
        content: ''; position: absolute;
        top: 50%; left: 50%; transform: translate(-50%, -50%);
        width: 20px; height: 20px; background-color: white; border-radius: 4px;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .progress-ring {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-90deg);
        width: 80px; height: 80px;
    }
    .progress-ring__circle {
        transition: 0.35s stroke-dashoffset; stroke: var(--accent-color); stroke-width: 4; fill: transparent;
    }
</style>
{% endblock %}
{% block content %}
    <h2 style="text-align: center;">Creator Studio</h2>
    
    <div class="creator-tabs">
        <button id="tab-text" onclick="showTab('text')" class="active">Text Post</button>
        <button id="tab-six" onclick="showTab('six')">Record a Six</button>
    </div>

    <div id="text-creator" class="card">
        <form id="text-form-element" method="POST">
            <input type="hidden" name="post_type" value="text">
            <div class="form-group">
                <textarea name="text_content" rows="5" maxlength="150" placeholder="What's happening?" required></textarea>
            </div>
            <button type="submit" class="btn" style="width: 100%;">Post Text</button>
        </form>
    </div>

    <div id="six-creator" class="card" style="display: none;">
        <div id="six-recorder">
            <p id="recorder-status">Tap to record a 6 second video</p>
            <video id="video-preview" autoplay muted playsinline></video>
            <div style="position: relative; width: 80px; height: 80px; margin: auto;">
                <button id="record-button" class="record-btn"></button>
                <svg class="progress-ring" id="progress-svg">
                    <circle class="progress-ring__circle" r="38" cx="40" cy="40"/>
                </svg>
            </div>
        </div>
        
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
    function showTab(tabName) {
        document.getElementById('text-creator').style.display = (tabName === 'text') ? 'block' : 'none';
        document.getElementById('six-creator').style.display = (tabName === 'six') ? 'block' : 'none';
        document.getElementById('tab-text').classList.toggle('active', tabName === 'text');
        document.getElementById('tab-six').classList.toggle('active', tabName === 'six');
    }

    const recordButton = document.getElementById('record-button');
    const preview = document.getElementById('video-preview');
    const sixForm = document.getElementById('six-form-element');
    const recorderStatus = document.getElementById('recorder-status');
    const progressCircle = document.querySelector('.progress-ring__circle');
    const radius = progressCircle.r.baseVal.value;
    const circumference = radius * 2 * Math.PI;
    progressCircle.style.strokeDasharray = `${circumference} ${circumference}`;
    progressCircle.style.strokeDashoffset = circumference;
    
    let mediaRecorder;
    let recordedBlobs;

    function setProgress(percent) {
        const offset = circumference - percent / 100 * circumference;
        progressCircle.style.strokeDashoffset = offset;
    }

    recordButton.addEventListener('click', async () => {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
            return;
        }

        const constraints = { audio: true, video: { width: 480, height: 480, facingMode: "user" } };
        try {
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            preview.srcObject = stream;
            
            recordedBlobs = [];
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
            mediaRecorder.ondataavailable = event => {
                if (event.data && event.data.size > 0) {
                    recordedBlobs.push(event.data);
                }
            };
            mediaRecorder.onstart = () => {
                recordButton.classList.add('recording');
                recorderStatus.textContent = 'Recording...';
                let timeLeft = 6;
                const timer = setInterval(() => {
                    timeLeft -= 0.1;
                    setProgress((6 - timeLeft) / 6 * 100);
                    if (timeLeft <= 0) {
                        clearInterval(timer);
                        if(mediaRecorder.state === "recording") mediaRecorder.stop();
                    }
                }, 100);
                setTimeout(() => {
                    if (mediaRecorder.state === "recording") mediaRecorder.stop();
                }, 6000);
            };
            mediaRecorder.onstop = () => {
                recordButton.classList.remove('recording');
                recorderStatus.textContent = 'Previewing... Tap to re-record.';
                setProgress(0);
                preview.srcObject = null;
                const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
                preview.src = window.URL.createObjectURL(superBuffer);
                preview.controls = true;
                preview.muted = false;
                sixForm.style.display = 'block';
                stream.getTracks().forEach(track => track.stop());
            };
            mediaRecorder.start();
        } catch (e) {
            console.error('getUserMedia() error:', e);
            recorderStatus.textContent = "Could not access camera. Please grant permission.";
        }
    });

    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        formData.append('video_file', videoBlob, 'six-video.webm');
        
        // Disable button to prevent multiple submissions
        sixForm.querySelector('button').disabled = true;
        sixForm.querySelector('button').textContent = "Uploading...";

        fetch("{{ url_for('create_post') }}", {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (response.redirected) {
                window.location.href = response.url;
            } else {
                 sixForm.querySelector('button').disabled = false;
                 sixForm.querySelector('button').textContent = "Post Six";
                 alert("Something went wrong!");
            }
        })
        .catch(error => console.error('Error:', error));
    });

</script>
{% endblock %}
""",
# Other templates like profile.html, auth_form.html, discover.html would follow a similar pattern
# of updating class names and structure to match the new dark/neomorphic theme.
# I will update them all to maintain consistency.
"profile.html": """
{% extends "layout.html" %}
{% block title %}{{ user.username }}'s Profile{% endblock %}
{% block content %}
    <div class="card">
        <div style="display: flex; flex-direction: column; align-items: center; text-align: center;">
            {% if user.profile_pic and user.profile_pic != 'default.png' %}
                <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + user.profile_pic) }}" alt="pfp" style="width: 90px; height: 90px; margin-bottom: 15px;">
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
                    <a href="{{ url_for('unfollow', username=user.username) }}" class="btn" style="background:var(--secondary-color); color:var(--text-muted);">Unfollow</a>
                {% endif %}
                </div>
            {% else %}
                 <a href="{{ url_for('edit_profile') }}" class="btn" style="margin-top:15px;">Edit Profile</a>
            {% endif %}
        </div>
        <div style="display: flex; justify-content: space-around; text-align: center; margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--secondary-color);">
            <div><strong>{{ user.posts.count() }}</strong><br><span style="color:var(--text-muted);">Posts</span></div>
            <div><strong>{{ user.followers.count() }}</strong><br><span style="color:var(--text-muted);">Followers</span></div>
            <div><strong>{{ user.followed.count() }}</strong><br><span style="color:var(--text-muted);">Following</span></div>
        </div>
    </div>
    
    <div class="feed-nav">
        <a href="{{ url_for('profile', username=user.username, feed='all') }}" class="{{ 'active' if feed_type == 'all' }}">All</a>
        <a href="{{ url_for('profile', username=user.username, feed='texts') }}" class="{{ 'active' if feed_type == 'texts' }}">Texts</a>
        <a href="{{ url_for('profile', username=user.username, feed='sixs') }}" class="{{ 'active' if feed_type == 'sixs' }}">Sixs</a>
    </div>

    <div>
        {% for post in posts %}
            {% include 'post_card.html' %}
        {% else %}
            <div class="card" style="text-align:center; color:var(--text-muted);">
                <p>No posts yet.</p>
            </div>
        {% endfor %}
    </div>
{% endblock %}
""",
"auth_form.html": """
{% extends "layout.html" %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
    <div class="card" style="margin-top: 2rem;">
        <h2 style="text-align: center; color: var(--accent-color);">{{ title }}</h2>
        <form method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
            </div>
            {% if form_type == 'signup' %}
            <div class="form-group">
                <label for="bio">Bio (150 chars max)</label>
                <textarea id="bio" name="bio" rows="3" maxlength="150"></textarea>
            </div>
            {% endif %}
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
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
{% block title %}Discover - Sixsec{% endblock %}
{% block content %}
    <h2 style="text-align:center;">Discover</h2>
    <p style="text-align:center; color:var(--text-muted); margin-top:-10px; margin-bottom: 25px;">Find new accounts and content to follow.</p>
    {% for item in discover_items %}
        {% if item.type == 'post' %}
            {% set post = item.content %}
            {% include 'post_card.html' %}
        {% elif item.type == 'user' %}
            {% set user = item.content %}
            <div class="card">
                <div style="display: flex; align-items: center; gap: 15px;">
                    {% if user.profile_pic and user.profile_pic != 'default.png' %}
                        <img class="pfp" src="{{ url_for('static', filename='uploads/profiles/' + user.profile_pic) }}" alt="pfp" style="width: 50px; height: 50px;">
                    {% else %}
                        <div class="pfp pfp-placeholder" style="width: 50px; height: 50px; background-color:{{ user.pfp_bg }};">{{ user.username[0]|upper }}</div>
                    {% endif %}
                    <div style="flex-grow: 1;">
                        <a href="{{ url_for('profile', username=user.username) }}" class="username"><strong>{{ user.username }}</strong></a>
                        <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ user.bio|truncate(50) if user.bio else 'No bio yet.' }}</p>
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
        <div class="card" style="text-align:center; color: var(--text-muted);">
            <p>Nothing to discover right now.</p>
        </div>
    {% endfor %}
{% endblock %}
""",
"home.html": """
{% extends "layout.html" %}
{% block content %}
    <div class="feed-nav">
        <a href="{{ url_for('home', feed_type='text') }}" class="{{ 'active' if feed_type == 'text' }}">Text</a>
        <a href="{{ url_for('home', feed_type='sixs') }}" class="{{ 'active' if feed_type == 'sixs' }}">Sixs</a>
    </div>
    {% for post in posts %}
        {% include 'post_card.html' %}
    {% else %}
        <div class="card" style="text-align:center; color: var(--text-muted);">
            <p>Your feed is empty.</p>
            <p>Follow some accounts on the <a href="{{ url_for('discover') }}">Discover</a> page!</p>
        </div>
    {% endfor %}
{% endblock %}
"""
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
    posts = db.relationship('Post', backref='author', lazy='dynamic', foreign_keys='Post.user_id')
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
        # Generate a consistent background color for the placeholder based on username
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
    user = db.relationship('User')

# --- LOGIN MANAGER & ROUTES ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    posts = current_user.followed_posts(feed_type)
    return render_template('home.html', posts=posts, feed_type=feed_type)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form.get('post_type')
        if post_type == 'text':
            content = request.form.get('text_content')
            if not content or len(content) > 150:
                flash('Invalid text content.', 'error')
                return redirect(url_for('create_post'))
            post = Post(post_type='text', text_content=content, author=current_user)
        elif post_type == 'six':
            video_file = request.files.get('video_file')
            caption = request.form.get('caption', '')
            if not video_file:
                flash('Video data not received.', 'error')
                return redirect(url_for('create_post'))
            
            filename = secure_filename(f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.webm")
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            video_file.save(video_path)
            post = Post(post_type='six', text_content=caption, video_filename=filename, author=current_user)
        else:
            flash('Invalid post type.', 'error')
            return redirect(url_for('create_post'))
        
        db.session.add(post)
        db.session.commit()
        flash('Post created successfully!', 'success')
        return redirect(url_for('home'))

    return render_template('create_post.html')

@app.route('/post/<int:post_id>/comments')
@login_required
def get_comments(post_id):
    post = Post.query.get_or_404(post_id)
    comments_data = []
    for comment in post.comments.order_by(Comment.timestamp.asc()).all():
        comments_data.append({
            'text': comment.text,
            'timestamp': comment.timestamp.strftime('%b %d, %H:%M'),
            'user': {
                'username': comment.user.username,
                'pfp_bg': comment.user.pfp_bg,
                'initial': comment.user.username[0].upper()
            }
        })
    return jsonify(comments_data)

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({'error': 'Comment text is required'}), 400
    
    comment = Comment(text=data['text'], user_id=current_user.id, post_id=post.id)
    db.session.add(comment)
    db.session.commit()
    return jsonify({'success': True}), 201

# All other routes (profile, discover, auth, actions) are very similar to before,
# with minor adjustments for redirects or flashes if needed. I will include them
# for completeness.

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
    return render_template('discover.html', discover_items=discover_items)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    feed_type = request.args.get('feed', 'all')
    if feed_type == 'texts':
        posts = user.posts.filter_by(post_type='text').order_by(Post.timestamp.desc()).all()
    elif feed_type == 'sixs':
        posts = user.posts.filter_by(post_type='six').order_by(Post.timestamp.desc()).all()
    else: # 'all'
        posts = user.posts.order_by(Post.timestamp.desc()).all()
    return render_template('profile.html', user=user, posts=posts, feed_type=feed_type)
    
@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', current_user.bio)
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('auth_form.html', title="Edit Profile", form_type='signup')

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user:
        current_user.follow(user)
        db.session.commit()
        flash(f'You are now following {username}!', 'success')
    return redirect(request.referrer or url_for('home'))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user:
        current_user.unfollow(user)
        db.session.commit()
        flash(f'You have unfollowed {username}.', 'success')
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

@app.route('/repost/<int:post_id>', methods=['POST'])
@login_required
def repost(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user and post not in current_user.reposts:
        current_user.reposts.append(post)
        db.session.commit()
        flash("Post reposted!", "success")
    else:
        flash("Cannot repost this.", "error")
    return redirect(request.referrer or url_for('home'))

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
    return render_template('auth_form.html', title="Sign Up", form_type="signup")

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')):
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'))
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)