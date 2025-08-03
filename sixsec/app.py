import os
import datetime
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from jinja2 import BaseLoader, TemplateNotFound
from sqlalchemy import or_

# --- APP CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'the-final-complete-polished-key-for-sixsec-v2'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['PFP_FOLDER'] = os.path.join(basedir, 'static/uploads/pfp')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB

# --- INITIALIZE EXTENSIONS & HELPERS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

ICONS = {
    'home': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    'discover': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    'create': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M12 5v14m-7-7h14" stroke="var(--bg-color)" stroke-width="2" stroke-linecap="round"/></svg>',
    'profile': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    'like': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    'comment': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    'repost': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
    'send': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>',
    'settings': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
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
            --bg-color: #000000;
            --primary-color: #151515;
            --border-color: #2f2f2f;
            --accent-color: #1d9bf0;
            --text-color: #e7e9ea;
            --text-muted: #71767b;
            --red-color: #f91880;
            --green-color: #00ba7c;
        }
        html { -webkit-tap-highlight-color: transparent; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            background-color: var(--bg-color);
            color: var(--text-color);
            font-size: 15px;
            overscroll-behavior-y: contain;
        }
        .container { max-width: 600px; margin: 0 auto; }
        a { color: var(--accent-color); text-decoration: none; }
        .top-bar {
            position: sticky; top: 0; z-index: 1000;
            background: rgba(0, 0, 0, 0.65);
            backdrop-filter: blur(12px) saturate(180%);
            -webkit-backdrop-filter: blur(12px) saturate(180%);
            padding: 0 16px; height: 53px;
            border-bottom: 1px solid var(--border-color);
            display: flex; justify-content: space-between; align-items: center;
        }
        .top-bar .logo { font-weight: bold; font-size: 1.7em; }
        .bottom-nav {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: rgba(0, 0, 0, 0.65);
            backdrop-filter: blur(12px) saturate(180%); -webkit-backdrop-filter: blur(12px) saturate(180%);
            border-top: 1px solid var(--border-color);
            display: flex; justify-content: space-around; height: 53px;
            z-index: 1000;
        }
        .bottom-nav a { color: var(--text-color); display:flex; align-items:center; transition: transform 0.1s ease; }
        .bottom-nav a.active svg { stroke-width: 2.5; }
        .bottom-nav a.active { transform: scale(1.1); }
        .bottom-nav a svg { width: 26px; height: 26px; }
        .bottom-nav .create-btn {
             background: var(--accent-color); border-radius: 50%; width: 50px; height: 50px;
             display: flex; align-items: center; justify-content: center;
             transform: translateY(-15px); border: 4px solid var(--bg-color);
        }
        .bottom-nav .create-btn svg { color: white; width: 28px; height: 28px; }
        .btn {
            background-color: var(--text-color); color: var(--bg-color); padding: 8px 16px;
            border-radius: 20px; border: none;
            cursor: pointer; font-weight: bold; font-size: 15px;
            transition: opacity 0.2s ease;
        }
        .btn:hover { opacity: 0.9; }
        .btn-outline { background: transparent; border: 1px solid var(--text-muted); color: var(--text-color); }
        .btn-danger { background-color: var(--red-color); color: white; }
        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: .5rem; color: var(--text-muted); }
        .form-group input, .form-group textarea {
            width: 100%; padding: 12px; border: 1px solid var(--border-color);
            border-radius: 6px; background: transparent; color: var(--text-color);
            box-sizing: border-box; font-size: 1rem;
        }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: var(--accent-color); }
        .modal {
            display: none; position: fixed; z-index: 2000; left: 0; top: 0;
            width: 100%; height: 100%; overflow: auto; background-color: rgba(91, 112, 131, 0.4);
            align-items: center; justify-content: center;
        }
        .modal-content {
            background-color: var(--bg-color);
            border-radius: 16px; width: 90%; max-width: 500px;
            max-height: 80vh; display: flex; flex-direction: column;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
        .modal-header { padding: 12px 16px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; }
        .modal-header .close { font-size: 24px; font-weight: bold; cursor: pointer; padding: 0 8px; }
        .modal-body { flex-grow: 1; padding: 16px; overflow-y: auto; }
        .modal-footer { padding: 8px 16px; border-top: 1px solid var(--border-color); }
        .feed-nav {
            display: flex; border-bottom: 1px solid var(--border-color);
            background: rgba(0, 0, 0, 0.65);
            backdrop-filter: blur(12px) saturate(180%); -webkit-backdrop-filter: blur(12px) saturate(180%);
            position: sticky; top: 53px; z-index: 999;
        }
        .feed-nav-link { flex:1; text-align:center; padding: 15px; font-weight:bold; position:relative; }
        .feed-nav-link.active { color: var(--text-color); }
        .feed-nav-link:not(.active) { color: var(--text-muted); }
        .feed-nav-link.active::after { content: ''; position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px; }

        .pfp-image { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
        .pfp-initials { width: 100%; height: 100%; border-radius: 50%; display:flex; align-items:center; justify-content:center; font-weight:bold; }
        {% block style_override %}{% endblock %}
    </style>
</head>
<body {% if request.endpoint == 'home' and feed_type == 'sixs' %}style="overflow: hidden;"{% endif %}>

    {% if not (request.endpoint == 'home' and feed_type == 'sixs') %}
    <header class="top-bar">
        <h1 class="logo">{% block header_title %}Home{% endblock %}</h1>
        {% if request.endpoint == 'profile' and current_user == user %}
        <a href="{{ url_for('edit_profile') }}">{{ ICONS.settings|safe }}</a>
        {% endif %}
    </header>
    {% endif %}

    <main {% if not (request.endpoint == 'home' and feed_type == 'sixs') %}class="container"{% endif %}>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            <div style="position:fixed; top:60px; left:50%; transform:translateX(-50%); z-index: 9999;">
                {% for category, message in messages %}
                <div style="padding: 12px 16px; border-radius: 8px; margin-bottom: 15px; background-color: var(--accent-color); color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">{{ message }}</div>
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
        <a href="{{ url_for('create_post') }}" class="create-btn">{{ ICONS.create|safe }}</a>
        <a href="{{ url_for('profile', username=current_user.username) }}" class="{{ 'active' if request.endpoint == 'profile' else '' }}">{{ ICONS.profile|safe }}</a>
    </nav>
    {% endif %}

    <!-- Global Modals -->
    <div id="commentModal" class="modal"><div class="modal-content" id="commentModalContent"></div></div>
    <div id="repostModal" class="modal"><div class="modal-content" id="repostModalContent"></div></div>
    <div id="userListModal" class="modal"><div class="modal-content" id="userListModalContent"></div></div>

    <script>
    function closeModal(modalId) { document.getElementById(modalId).style.display = 'none'; }
    window.onclick = (event) => {
        if (event.target.classList.contains('modal')) event.target.style.display = 'none';
    };

    async function openCommentModal(postId) {
        const modal = document.getElementById('commentModal');
        const content = document.getElementById('commentModalContent');
        content.innerHTML = '<p style="padding: 20px; text-align: center;">Loading...</p>';
        modal.style.display = 'flex';
        const response = await fetch(`/post/${postId}/comments_modal`);
        content.innerHTML = await response.text();
    }

    async function submitComment(form, event) {
        event.preventDefault();
        const formData = new FormData(form);
        const response = await fetch(form.action, { method: 'POST', body: formData });
        const data = await response.json();
        if (data.success) {
            openCommentModal(data.postId);
            const countEl = document.querySelector(`#comment-count-${data.postId}`);
            if(countEl) countEl.innerText = parseInt(countEl.innerText) + 1;
        }
    }

    async function openRepostModal(postId) {
        const modal = document.getElementById('repostModal');
        const content = document.getElementById('repostModalContent');
        content.innerHTML = '<p style="padding: 20px; text-align: center;">Loading...</p>';
        modal.style.display = 'flex';
        const response = await fetch(`/repost/${postId}/modal`);
        content.innerHTML = await response.text();
    }

    async function openUserListModal(url) {
        const modal = document.getElementById('userListModal');
        const content = document.getElementById('userListModalContent');
        content.innerHTML = '<p style="padding: 20px; text-align: center;">Loading...</p>';
        modal.style.display = 'flex';
        const response = await fetch(url);
        content.innerHTML = await response.text();
    }
    
    function flashMessage(message, isError = false) {
        let flashDiv = document.createElement('div');
        flashDiv.textContent = message;
        flashDiv.style.cssText = `position:fixed; bottom:80px; left:50%; transform:translateX(-50%); padding:12px 20px; border-radius:20px; background:${isError ? 'var(--red-color)' : 'var(--accent-color)'}; color:white; z-index:9999; box-shadow:0 4px 10px rgba(0,0,0,0.3);`;
        document.body.appendChild(flashDiv);
        setTimeout(() => flashDiv.remove(), 3000);
    }
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
""",

"home.html": """
{% extends "layout.html" %}
{% block style_override %}
    {% if feed_type == 'sixs' %}
    #sixs-feed-container {
        height: 100dvh; width: 100vw; overflow-y: scroll;
        scroll-snap-type: y mandatory; background-color: #000;
        position: fixed; top: 0; left: 0;
    }
    .six-video-slide {
        height: 100dvh; width: 100vw; scroll-snap-align: start;
        position: relative; display: flex; justify-content: center; align-items: center;
    }
    .six-video-wrapper {
        position: relative;
        width: 100vw; height: 100vw;
        max-width: 100dvh; max-height: 100dvh;
        clip-path: circle(50% at 50% 50%);
    }
    .six-video { width: 100%; height: 100%; object-fit: cover; }
    .six-ui-overlay {
        position: absolute; bottom: 0; left: 0; right: 0; top: 0;
        color: white; display: flex; justify-content: space-between; align-items: flex-end;
        padding: 16px; padding-bottom: 70px;
        pointer-events: none;
        background: linear-gradient(to top, rgba(0,0,0,0.4), transparent 40%);
        text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
    }
    .six-info { pointer-events: auto; }
    .six-info .username { font-weight: bold; font-size: 1.1em; }
    .six-actions {
        display: flex; flex-direction: column; gap: 20px;
        pointer-events: auto; align-items: center;
    }
    .six-actions button {
        background: none; border: none; color: white;
        display: flex; flex-direction: column; align-items: center;
        gap: 5px; cursor: pointer; font-size: 13px; padding: 0;
    }
    .six-actions svg { width: 32px; height: 32px; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5)); }
    .six-actions .liked svg { fill: var(--red-color); stroke: var(--red-color); }
    .six-actions .reposted svg { stroke: var(--green-color); }
    {% endif %}
{% endblock %}
{% block content %}
    <div class="feed-nav">
        <a href="{{ url_for('home', feed_type='text') }}" class="feed-nav-link {{ 'active' if feed_type == 'text' else '' }}">Text</a>
        <a href="{{ url_for('home', feed_type='sixs') }}" class="feed-nav-link {{ 'active' if feed_type == 'sixs' else '' }}">Sixs</a>
    </div>

    {% if feed_type == 'text' %}
        {% for post in posts %}
            {% include 'post_card_text.html' %}
        {% else %}
            <div style="text-align:center; padding: 40px; color:var(--text-muted);">
                <h4>Your feed is empty.</h4>
                <p>Follow accounts on the <a href="{{ url_for('discover') }}">Discover</a> page!</p>
            </div>
        {% endfor %}

    {% elif feed_type == 'sixs' %}
        <div id="sixs-feed-container">
            {% for post in posts %}
            <section class="six-video-slide" data-post-id="{{ post.id }}">
                <div class="six-video-wrapper">
                    <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop preload="auto" playsinline muted></video>
                </div>
                <div class="six-ui-overlay">
                    <div class="six-info">
                        <a href="{{ url_for('profile', username=post.author.username) }}" style="color:white;"><strong class="username">@{{ post.author.username }}</strong></a>
                        <p>{{ post.text_content }}</p>
                    </div>
                    <div class="six-actions">
                        <button onclick="handleLike(this, {{ post.id }})" class="{{ 'liked' if post.liked_by_current_user else '' }}">
                            {{ ICONS.like|safe }}
                            <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                        </button>
                        <button onclick="openCommentModal({{ post.id }})">{{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span></button>
                        <button onclick="handleRepost(this, {{ post.id }})" class="{{ 'reposted' if post.is_reposted_by_current_user else '' }}">{{ ICONS.repost|safe }} <span id="repost-count-{{ post.id }}">{{ post.reposted_by|length }}</span></button>
                    </div>
                </div>
            </section>
            {% else %}
            <section class="six-video-slide" style="flex-direction:column; text-align:center; color:white;">
                <h4>No Sixs to show!</h4>
                <p style="color:#aaa;">Follow accounts or create your own.</p>
                <a href="{{ url_for('create_post') }}" class="btn" style="margin-top:20px;">Create a Six</a>
            </section>
            {% endfor %}
        </div>
        <nav class="bottom-nav" style="position:fixed; z-index:1001; bottom:0; left:0; right:0;">
            <a href="{{ url_for('home') }}" class="{{ 'active' if request.endpoint == 'home' else '' }}">{{ ICONS.home|safe }}</a>
            <a href="{{ url_for('discover') }}" class="{{ 'active' if request.endpoint == 'discover' else '' }}">{{ ICONS.discover|safe }}</a>
            <a href="{{ url_for('create_post') }}" class="create-btn">{{ ICONS.create|safe }}</a>
            <a href="{{ url_for('profile', username=current_user.username) }}">{{ ICONS.profile|safe }}</a>
        </nav>
    {% endif %}
{% endblock %}
{% block scripts %}
<script>
    async function handleLike(button, postId) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        button.querySelector('span').innerText = data.likes;
        button.classList.toggle('liked', data.liked);
        const icon = button.querySelector('svg');
        const isSixFeed = document.body.style.overflow === 'hidden';
        if (data.liked) {
            icon.style.fill = 'var(--red-color)';
            icon.style.stroke = 'var(--red-color)';
            if (!isSixFeed) button.style.color = 'var(--red-color)';
        } else {
            icon.style.fill = 'none';
            icon.style.stroke = isSixFeed ? 'white' : 'currentColor';
            if (!isSixFeed) button.style.color = 'var(--text-muted)';
        }
    }

    async function handleRepost(button, postId) {
        if (button.classList.contains('reposted')) {
             const response = await fetch(`/unrepost/${postId}`, { method: 'POST' });
             const data = await response.json();
             if (data.success) {
                button.classList.remove('reposted');
                const icon = button.querySelector('svg');
                const isSixFeed = document.body.style.overflow === 'hidden';
                icon.style.stroke = isSixFeed ? 'white' : 'currentColor';
                if (!isSixFeed) button.style.color = 'var(--text-muted)';
                const countEl = document.getElementById(`repost-count-${postId}`);
                countEl.innerText = parseInt(countEl.innerText) - 1;
                flashMessage('Repost removed.');
             }
        } else {
            openRepostModal(postId);
        }
    }

    async function submitRepost(form, event) {
        event.preventDefault();
        const formData = new FormData(form);
        const response = await fetch(form.action, { method: 'POST', body: formData });
        const data = await response.json();
        if (data.success) {
            closeModal('repostModal');
            flashMessage('Post reposted!');
            setTimeout(() => window.location.reload(), 1500);
        } else {
            alert(data.message);
        }
    }
</script>
{% if feed_type == 'sixs' %}
<script>
    const videos = document.querySelectorAll('.six-video');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target;
            if (entry.isIntersecting) {
                video.play().catch(e => {});
                video.muted = video.dataset.muted === 'true' || typeof video.dataset.muted === 'undefined';
            } else {
                video.pause();
                video.currentTime = 0;
            }
        });
    }, { threshold: 0.5 });
    videos.forEach(video => {
        observer.observe(video);
        video.addEventListener('click', () => {
             video.muted = !video.muted;
             video.dataset.muted = video.muted;
        });
    });
</script>
{% endif %}
{% endblock %}
""",

"post_card_text.html": """
<article style="border-bottom: 1px solid var(--border-color); padding: 12px 16px; display:flex; gap:12px;">
    <div style="width:40px; flex-shrink:0;">
        <a href="{{ url_for('profile', username=post.author.username) }}">
            <div style="width:40px; height:40px; border-radius:50%; background:{{ post.author.pfp_gradient }}; font-size:1.4rem;">
                {% if post.author.pfp_filename %}
                    <img src="{{ url_for('static', filename='uploads/pfp/' + post.author.pfp_filename) }}" class="pfp-image" alt="{{ post.author.username }}'s profile picture">
                {% else %}
                    <div class="pfp-initials">{{ post.author.username[0]|upper }}</div>
                {% endif %}
            </div>
        </a>
    </div>
    <div style="flex-grow:1;">
        <div>
            <a href="{{ url_for('profile', username=post.author.username) }}" style="color:var(--text-color); font-weight:bold;">{{ post.author.username }}</a>
            <span style="color:var(--text-muted);">· {{ post.timestamp.strftime('%b %d') }}</span>
        </div>
        
        {% if post.repost_of %}
            <p style="margin: 4px 0 8px 0;">{{ post.text_content }}</p>
            <div style="border: 1px solid var(--border-color); border-radius: 12px; padding: 12px; margin-bottom: 12px; cursor:pointer;" onclick="window.location.href='{{ url_for('home') }}#post-{{ post.repost_of.id }}'">
                <div style="display:flex; align-items:center; gap:8px; margin-bottom: 4px;">
                    <div style="width:20px; height:20px; border-radius:50%; background:{{ post.repost_of.author.pfp_gradient }}; font-size:0.8rem; flex-shrink:0;">
                        {% if post.repost_of.author.pfp_filename %}<img src="{{ url_for('static', filename='uploads/pfp/' + post.repost_of.author.pfp_filename) }}" class="pfp-image">{% else %}<div class="pfp-initials">{{ post.repost_of.author.username[0]|upper }}</div>{% endif %}
                    </div>
                    <a href="{{ url_for('profile', username=post.repost_of.author.username) }}" style="color:var(--text-color); font-weight:bold; font-size:0.9em;">{{ post.repost_of.author.username }}</a>
                </div>
                <p style="margin:0;">{{ post.repost_of.text_content }}</p>
            </div>
        {% else %}
            <p style="margin: 4px 0 12px 0;">{{ post.text_content }}</p>
        {% endif %}

        <div style="display: flex; justify-content: space-between; max-width: 425px; color:var(--text-muted);">
            <button onclick="openCommentModal({{ post.id }})" style="background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer; padding:0;">{{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span></button>
            <button onclick="handleRepost(this, {{ post.id }})" class="{{ 'reposted' if post.is_reposted_by_current_user else '' }}" style="background:none; border:none; color: {{ 'var(--green-color)' if post.is_reposted_by_current_user else 'var(--text-muted)' }}; display:flex; align-items:center; gap:8px; cursor:pointer; padding:0;"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg> <span id="repost-count-{{ post.id }}">{{ post.reposted_by|length }}</span></button>
            <button onclick="handleLike(this, {{ post.id }})" class="{{ 'liked' if post.liked_by_current_user else '' }}" style="background:none; border:none; color:{{ 'var(--red-color)' if post.liked_by_current_user else 'var(--text-muted)' }}; display:flex; align-items:center; gap:8px; cursor:pointer; padding:0;"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="{{ 'var(--red-color)' if post.liked_by_current_user else 'none' }}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg> <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span></button>
        </div>
    </div>
</article>
""",
"create_post.html": """
{% extends "layout.html" %}
{% block header_title %}Create{% endblock %}
{% block content %}
<div class="feed-nav" style="top:0;">
    <a href="?type=text" class="feed-nav-link {{ 'active' if request.args.get('type', 'text') == 'text' else '' }}">Text</a>
    <a href="?type=six" class="feed-nav-link {{ 'active' if request.args.get('type') == 'six' else '' }}">Six</a>
</div>
{% if request.args.get('type') == 'six' %}
    <div style="padding:16px;">
        <div id="six-creator" style="text-align: center;">
            <p id="recorder-status" style="color:var(--text-muted); min-height: 20px;">Tap the red button to record</p>
            <div style="width:100%; max-width: 400px; margin: 15px auto; aspect-ratio: 1/1; border-radius:50%; overflow:hidden; background:#111; border: 2px solid var(--border-color);">
                <video id="video-preview" autoplay muted playsinline style="width:100%; height:100%; object-fit:cover; transform: scaleX(-1);"></video>
            </div>
            <button id="record-button" style="width: 80px; height: 80px; border-radius: 50%; border: 4px solid white; background-color: var(--red-color); cursor: pointer; transition: all 0.2s ease;" disabled></button>
            <form id="six-form-element" method="POST" enctype="multipart/form-data" style="display: none; margin-top: 20px;">
                 <input type="hidden" name="post_type" value="six">
                 <div class="form-group"> <input type="text" name="caption" maxlength="50" placeholder="Add a caption... (optional)"> </div>
                 <button type="submit" class="btn" style="width: 100%;">Post Six</button>
            </form>
        </div>
    </div>
{% else %}
    <div style="padding:16px;">
        <form method="POST" action="{{ url_for('create_post') }}">
            <input type="hidden" name="post_type" value="text">
            <div class="form-group">
                <textarea name="text_content" rows="5" placeholder="What's on your mind?" required maxlength="280"></textarea>
            </div>
            <button type="submit" class="btn" style="float:right;">Post</button>
        </form>
    </div>
{% endif %}
{% endblock %}
{% block scripts %}
{% if request.args.get('type') == 'six' %}
<script>
    let mediaRecorder; let recordedBlobs; let stream;
    const recordButton = document.getElementById('record-button');
    const preview = document.getElementById('video-preview');
    const sixForm = document.getElementById('six-form-element');
    const recorderStatus = document.getElementById('recorder-status');

    async function initCamera() {
        try {
            const constraints = { audio: true, video: { width: 480, height: 480, facingMode: "user" } };
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            preview.srcObject = stream;
            recordButton.disabled = false;
        } catch (e) {
            recorderStatus.textContent = "Camera/Mic permission is required to create a Six.";
            console.error(e);
        }
    }
    document.addEventListener('DOMContentLoaded', initCamera);

    recordButton.addEventListener('click', () => {
        if (recordButton.classList.contains('recording')) mediaRecorder.stop();
        else if (recordButton.classList.contains('previewing')) resetRecorder();
        else startRecording();
    });

    function startRecording() {
        recordedBlobs = [];
        let options = { mimeType: 'video/webm;codecs=vp9,opus' };
        if (!MediaRecorder.isTypeSupported(options.mimeType)) { options = { mimeType: 'video/webm' }; }
        mediaRecorder = new MediaRecorder(stream, options);
        mediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) recordedBlobs.push(e.data); };
        mediaRecorder.onstop = handleStop;
        mediaRecorder.start();
        recordButton.classList.add('recording');
        recordButton.style.cssText += 'border-radius:20%; background-color:white;';
        recorderStatus.innerHTML = 'Recording... <strong><span id="timer">6</span>s</strong>';
        let timeLeft = 5;
        const timerInterval = setInterval(() => { document.getElementById('timer').textContent = timeLeft; timeLeft--; if (timeLeft < 0) clearInterval(timerInterval); }, 1000);
        setTimeout(() => { if (mediaRecorder.state === "recording") mediaRecorder.stop(); }, 6000);
    }
    
    function handleStop() {
        recordButton.classList.remove('recording'); recordButton.classList.add('previewing');
        recordButton.style.cssText += 'border-radius:50%; background-color:var(--red-color);';
        recorderStatus.textContent = 'Previewing... Tap red button to re-record.';
        const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
        preview.srcObject = null;
        preview.src = window.URL.createObjectURL(superBuffer);
        preview.muted = false; preview.controls = true; preview.loop = true;
        sixForm.style.display = 'block';
    }

    function resetRecorder() {
        sixForm.style.display = 'none'; recordButton.classList.remove('previewing');
        preview.srcObject = stream; preview.controls = false; preview.muted = true;
        recorderStatus.textContent = "Tap the red button to record";
    }

    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        formData.append('video_file', videoBlob, 'six-video.webm');
        const submitBtn = sixForm.querySelector('button');
        submitBtn.disabled = true; submitBtn.textContent = "Uploading...";
        fetch("{{ url_for('create_post') }}", { method: 'POST', body: formData })
        .then(response => { if (response.redirected) window.location.href = response.url; })
        .catch(error => console.error('Error:', error));
    });
</script>
{% endif %}
{% endblock %}
""",

"edit_profile.html": """
{% extends "layout.html" %}
{% block header_title %}Settings{% endblock %}
{% block content %}
<div style="padding:16px;">
    <h4>Edit Profile</h4>
    <form method="POST" action="{{ url_for('edit_profile') }}" enctype="multipart/form-data">
        <div class="form-group">
            <label for="pfp">Profile Picture</label>
            <input type="file" id="pfp" name="pfp" accept="image/png, image/jpeg, image/gif">
        </div>
        <div class="form-group"><label for="bio">Bio</label><textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea></div>
        <button type="submit" class="btn">Save Changes</button>
    </form>
    <hr style="border-color: var(--border-color); margin: 30px 0;">
    <h4>Account Actions</h4>
    <a href="{{ url_for('logout') }}" class="btn btn-outline" style="display:block; text-align:center; margin-bottom: 20px;">Log Out</a>

    <div style="border: 1px solid var(--red-color); border-radius: 8px; padding: 16px;">
        <h5 style="margin-top:0;">Delete Account</h5>
        <p style="color:var(--text-muted);">This action is permanent. All your data will be removed.</p>
        <button onclick="document.getElementById('deleteModal').style.display='flex'" class="btn btn-danger">Delete My Account</button>
    </div>
</div>
<div id="deleteModal" class="modal">
    <div class="modal-content">
        <div class="modal-header">
            <span class="close" onclick="closeModal('deleteModal')">×</span>
            <h4 style="margin:0; padding-left:16px;">Confirm Account Deletion</h4>
        </div>
        <div class="modal-body">
            <p>This is permanent. Are you sure you want to delete your account?</p>
            <form action="{{ url_for('delete_account') }}" method="POST">
                <div class="form-group"><label for="password">Enter your password to confirm</label><input type="password" id="password" name="password" required></div>
                <button type="submit" class="btn btn-danger" style="width:100%;">Permanently Delete Account</button>
            </form>
        </div>
    </div>
</div>
{% endblock %}
""",

"profile.html": """
{% extends "layout.html" %}
{% block header_title %}{{ user.username }}{% endblock %}
{% block content %}
    <div style="padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div style="width: 80px; height: 80px; border-radius:50%; background: {{ user.pfp_gradient }}; font-size:2.5rem; flex-shrink:0;">
                {% if user.pfp_filename %}
                    <img src="{{ url_for('static', filename='uploads/pfp/' + user.pfp_filename) }}" class="pfp-image">
                {% else %}
                    <div class="pfp-initials">{{ user.username[0]|upper }}</div>
                {% endif %}
            </div>
            <div style="text-align: right;">
            {% if current_user.is_authenticated and current_user != user %}
                {% if not current_user.is_following(user) %} <a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>
                {% else %} <a href="{{ url_for('unfollow', username=user.username) }}" class="btn btn-outline">Following</a> {% endif %}
            {% endif %}
            </div>
        </div>
        <h2 style="margin: 12px 0 0 0;">{{ user.username }}</h2>
        <p style="color: var(--text-muted); margin: 4px 0 12px 0;">{{ user.bio or "No bio yet." }}</p>
        <div style="display:flex; gap: 16px; color:var(--text-muted);">
            <a href="#" onclick="openUserListModal('{{ url_for('user_list', username=user.username, list_type='followers') }}')"><strong style="color:var(--text-color)">{{ user.followers.count() }}</strong> Followers</a>
            <a href="#" onclick="openUserListModal('{{ url_for('user_list', username=user.username, list_type='following') }}')"><strong style="color:var(--text-color)">{{ user.followed.count() }}</strong> Following</a>
        </div>
    </div>
    <div class="feed-nav" style="border-top: 1px solid var(--border-color);">
        {% set tabs = [('Posts', url_for('profile', username=user.username, tab='posts')), ('Likes', url_for('profile', username=user.username, tab='likes'))] %}
        {% for name, url in tabs %}
        <a href="{{ url }}" class="feed-nav-link {{ 'active' if active_tab == name.lower() else '' }}">{{ name }}</a>
        {% endfor %}
    </div>
    {% for post in posts %}
        {% include 'post_card_text.html' %}
    {% else %}
        <p style="text-align:center; color:var(--text-muted); padding:40px;">No posts in this section.</p>
    {% endfor %}
{% endblock %}
""",

"discover.html": """
{% extends "layout.html" %}
{% block header_title %}Discover{% endblock %}
{% block content %}
    {% for user in users %}
    <div style="border-bottom: 1px solid var(--border-color); padding:12px 16px; display:flex; align-items:center; gap:12px;">
        <div style="width: 40px; height: 40px; border-radius:50%; flex-shrink:0; background: {{ user.pfp_gradient }}; font-size:1.4rem;">
            {% if user.pfp_filename %}
                <img src="{{ url_for('static', filename='uploads/pfp/' + user.pfp_filename) }}" class="pfp-image">
            {% else %}
                <div class="pfp-initials">{{ user.username[0]|upper }}</div>
            {% endif %}
        </div>
        <div style="flex-grow:1;">
            <a href="{{ url_for('profile', username=user.username) }}" style="color:var(--text-color); font-weight:bold;">{{ user.username }}</a>
            <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ user.bio|truncate(50) if user.bio else 'No bio yet.' }}</p>
        </div>
        <div>{% if not current_user.is_following(user) %}<a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>{% endif %}</div>
    </div>
    {% endfor %}
{% endblock %}
""",

"auth_form.html": """
{% extends "layout.html" %}
{% block title %}{{ title }}{% endblock %}
{% block header_title %}{{ title }}{% endblock %}
{% block content %}
<div style="padding:16px;">
    <form method="POST">
        <div class="form-group"><label for="username">Username</label><input type="text" id="username" name="username" required></div>
        <div class="form-group"><label for="password">Password</label><input type="password" id="password" name="password" required></div>
        <button type="submit" class="btn" style="width:100%; height: 40px;">{{ title }}</button>
    </form>
    <p style="text-align:center; margin-top:20px; color:var(--text-muted);">
        {% if form_type == 'login' %}
            Don't have an account? <a href="{{ url_for('signup') }}">Sign Up</a>
        {% else %}
            Already have an account? <a href="{{ url_for('login') }}">Login</a>
        {% endif %}
    </p>
</div>
{% endblock %}
""",

"_repost_modal.html": """
<div class="modal-header">
    <span class="close" onclick="closeModal('repostModal')">×</span>
    <h4 style="margin:0; padding-left:16px;">Repost</h4>
</div>
<form onsubmit="submitRepost(this, event)" action="{{ url_for('repost', post_id=post.id) }}" method="POST">
    <div class="modal-body">
        <div class="form-group">
            <textarea name="caption" rows="3" placeholder="Add a comment... (optional)" maxlength="150"></textarea>
        </div>
        <div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 12px;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom: 4px;">
                <div style="width:20px; height:20px; border-radius:50%; background:{{ post.author.pfp_gradient }}; font-size:0.8rem; flex-shrink:0;">
                    {% if post.author.pfp_filename %}<img src="{{ url_for('static', filename='uploads/pfp/' + post.author.pfp_filename) }}" class="pfp-image">{% else %}<div class="pfp-initials">{{ post.author.username[0]|upper }}</div>{% endif %}
                </div>
                <strong style="font-size:0.9em;">{{ post.author.username }}</strong>
            </div>
            <p style="margin:0; color:var(--text-muted);">{{ post.text_content|truncate(150) }}</p>
        </div>
    </div>
    <div class="modal-footer" style="text-align:right;">
        <button type="submit" class="btn">Repost</button>
    </div>
</form>
""",

"_comments_modal.html": """
<div class="modal-header">
    <span class="close" onclick="closeModal('commentModal')">×</span>
    <h4 style="margin:0; padding-left:16px;">Comments</h4>
</div>
<div class="modal-body" id="comment-list">
    {% for c in comments %}
    <div style="display:flex; gap:12px; margin-bottom:16px;">
        <div style="width:40px; height:40px; border-radius:50%; flex-shrink:0; background:{{c.user.pfp_gradient}}; font-size:1.4rem;">
             {% if c.user.pfp_filename %}<img src="{{ url_for('static', filename='uploads/pfp/' + c.user.pfp_filename) }}" class="pfp-image">{% else %}<div class="pfp-initials">{{ c.user.username[0]|upper }}</div>{% endif %}
        </div>
        <div>
            <strong style="color:var(--text-color);">{{ c.user.username }}</strong> <span style="color:var(--text-muted);">{{ c.timestamp.strftime('%b %d') }}</span>
            <div style="color:var(--text-color);">{{ c.text }}</div>
        </div>
    </div>
    {% else %}
    <p style="text-align:center; color: var(--text-muted);">No comments yet.</p>
    {% endfor %}
</div>
<div class="modal-footer">
    <form onsubmit="submitComment(this, event)" action="{{ url_for('add_comment', post_id=post_id) }}" style="display: flex; gap: 8px;">
        <input type="text" name="text" class="form-group" placeholder="Add a comment..." style="margin:0; flex-grow:1;">
        <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
    </form>
</div>
""",

"_user_list_modal.html": """
<div class="modal-header">
    <span class="close" onclick="closeModal('userListModal')">×</span>
    <h4 style="margin:0; padding-left:16px;">{{ title }}</h4>
</div>
<div class="modal-body">
    {% for user in users %}
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
        <a href="{{ url_for('profile', username=user.username) }}" style="width: 40px; height: 40px; border-radius:50%; flex-shrink:0; background: {{ user.pfp_gradient }}; font-size:1.4rem;">
            {% if user.pfp_filename %}<img src="{{ url_for('static', filename='uploads/pfp/' + user.pfp_filename) }}" class="pfp-image">{% else %}<div class="pfp-initials">{{ user.username[0]|upper }}</div>{% endif %}
        </a>
        <div style="flex-grow:1;">
            <a href="{{ url_for('profile', username=user.username) }}" style="color:var(--text-color); font-weight:bold;">{{ user.username }}</a>
            <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ user.bio|truncate(50) if user.bio else 'No bio yet.' }}</p>
        </div>
        {% if current_user.is_authenticated and current_user != user %}
        <div>
            {% if not current_user.is_following(user) %}<a href="{{ url_for('follow', username=user.username, next=request.url) }}" class="btn">Follow</a>
            {% else %}<a href="{{ url_for('unfollow', username=user.username, next=request.url) }}" class="btn btn-outline">Following</a>{% endif %}
        </div>
        {% endif %}
    </div>
    {% else %}
    <p style="text-align:center; color:var(--text-muted);">Nothing to see here.</p>
    {% endfor %}
</div>
"""
}

# --- JINJA2 LOADER ---
class DictLoader(BaseLoader):
    def __init__(self, templates_dict): self.templates = templates_dict
    def get_source(self, environment, template):
        if template in self.templates: return self.templates[template], None, lambda: True
        raise TemplateNotFound(template)
app.jinja_loader = DictLoader(templates)

# --- DATABASE MODELS ---
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')), db.Column('followed_id', db.Integer, db.ForeignKey('user.id')))

likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')), db.Column('post_id', db.Integer, db.ForeignKey('post.id')))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(150))
    pfp_filename = db.Column(db.String(120))
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Post.user_id')
    liked_posts = db.relationship('Post', secondary=likes, lazy='dynamic', backref=db.backref('liked_by', lazy='dynamic'))
    followed = db.relationship('User', secondary=followers, primaryjoin=(followers.c.follower_id == id), secondaryjoin=(followers.c.followed_id == id), backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')
    
    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)
    def is_following(self, u): return self.followed.filter(followers.c.followed_id == u.id).count() > 0
    def follow(self, u):
        if not self.is_following(u): self.followed.append(u)
    def unfollow(self, u):
        if self.is_following(u): self.followed.remove(u)
        
    @property
    def pfp_gradient(self):
        colors = [("#ef4444", "#fb923c"), ("#a855f7", "#ec4899"), ("#84cc16", "#22c55e"), ("#0ea5e9", "#6366f1")]
        c1, c2 = colors[hash(self.username) % len(colors)]; return f"linear-gradient(45deg, {c1}, {c2})"

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(10), nullable=False) # 'text', 'six', or 'repost'
    text_content = db.Column(db.String(280))
    video_filename = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    
    # For reposts ("quote tweets")
    repost_of_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    reposted_by = db.relationship('Post', backref=db.backref('repost_of', remote_side=[id]), lazy='dynamic', cascade="all, delete-orphan")

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user = db.relationship('User', backref='comments')


# --- CONTEXT PROCESSOR ---
@app.context_processor
def inject_user_status():
    def is_reposted_by_current_user(post):
        if not current_user.is_authenticated:
            return False
        return Post.query.filter_by(author=current_user, repost_of_id=post.id).count() > 0
    return dict(is_reposted_by_current_user=is_reposted_by_current_user)

# --- ROUTES ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    
    posts_query = Post.query.filter(Post.user_id.in_(followed_ids))
    
    if feed_type == 'text':
        posts = posts_query.filter(or_(Post.post_type == 'text', Post.post_type == 'repost')).order_by(Post.timestamp.desc()).all()
    else: # sixs
        posts = posts_query.filter_by(post_type='six').order_by(Post.timestamp.desc()).all()
    
    for p in posts:
        p.liked_by_current_user = current_user in p.liked_by
        p.is_reposted_by_current_user = is_reposted_by_current_user(p)
    return render_template('home.html', posts=posts, feed_type=feed_type)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    active_tab = request.args.get('tab', 'posts')
    if active_tab == 'likes': 
        posts = user.liked_posts.order_by(likes.c.post_id.desc()).all()
    else: 
        posts = user.posts.order_by(Post.timestamp.desc()).all()
        
    for p in posts:
        p.liked_by_current_user = current_user in p.liked_by
        p.is_reposted_by_current_user = is_reposted_by_current_user(p)
    return render_template('profile.html', user=user, posts=posts, active_tab=active_tab)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form.get('post_type')
        if post_type == 'text':
            content = request.form.get('text_content', '').strip()
            if not content:
                flash('Post cannot be empty.', 'error'); return redirect(url_for('create_post', type='text'))
            post = Post(post_type='text', text_content=content, author=current_user)
            db.session.add(post); db.session.commit()
            flash('Post created!', 'success'); return redirect(url_for('home'))
        elif post_type == 'six':
            video_file = request.files.get('video_file')
            if not video_file:
                flash('Video data not received.', 'error'); return redirect(url_for('create_post', type='six'))
            filename = secure_filename(f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.webm")
            video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post = Post(post_type='six', text_content=request.form.get('caption', ''), video_filename=filename, author=current_user)
            db.session.add(post); db.session.commit()
            flash('Six posted!', 'success'); return redirect(url_for('home', feed_type='sixs'))
    return render_template('create_post.html')

@app.route('/post/<int:post_id>/comments_modal')
@login_required
def get_comments_modal(post_id):
    post = Post.query.get_or_404(post_id)
    comments = post.comments.order_by(Comment.timestamp.asc()).all()
    return render_template('_comments_modal.html', comments=comments, post_id=post_id)

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    text = request.form.get('text', '').strip()
    if not text: return jsonify({'error': 'Comment text is required'}), 400
    comment = Comment(text=text, user_id=current_user.id, post_id=post_id)
    db.session.add(comment); db.session.commit()
    return jsonify({'success': True, 'postId': post_id})

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user in post.liked_by: post.liked_by.remove(current_user); liked = False
    else: post.liked_by.append(current_user); liked = True
    db.session.commit()
    return jsonify({'liked': liked, 'likes': post.liked_by.count()})

@app.route('/repost/<int:post_id>/modal')
@login_required
def repost_modal(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('_repost_modal.html', post=post)

@app.route('/repost/<int:post_id>', methods=['POST'])
@login_required
def repost(post_id):
    original_post = Post.query.get_or_404(post_id)
    if original_post.author == current_user:
        return jsonify({'success': False, 'message': "You can't repost your own post."})
    if is_reposted_by_current_user(original_post):
        return jsonify({'success': False, 'message': "You've already reposted this."})
    
    caption = request.form.get('caption', '').strip()
    repost = Post(post_type='repost', text_content=caption, author=current_user, repost_of_id=original_post.id)
    db.session.add(repost); db.session.commit()
    return jsonify({'success': True, 'message': 'Post reposted!'})

@app.route('/unrepost/<int:post_id>', methods=['POST'])
@login_required
def unrepost(post_id):
    repost_to_delete = Post.query.filter_by(author=current_user, repost_of_id=post_id).first()
    if repost_to_delete:
        db.session.delete(repost_to_delete); db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Repost not found.'}), 404

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', current_user.bio)
        pfp_file = request.files.get('pfp')
        if pfp_file:
            filename = secure_filename(f"pfp_{current_user.id}_{int(datetime.datetime.now().timestamp())}.png")
            pfp_file.save(os.path.join(app.config['PFP_FOLDER'], filename))
            current_user.pfp_filename = filename
        db.session.commit(); flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    if not current_user.check_password(request.form.get('password')):
        flash('Incorrect password. Account not deleted.', 'error'); return redirect(url_for('edit_profile'))
    user = User.query.get(current_user.id)
    logout_user()
    db.session.delete(user); db.session.commit()
    flash('Your account has been permanently deleted.', 'success'); return redirect(url_for('login'))

@app.route('/discover')
@login_required
def discover():
    followed_ids = [u.id for u in current_user.followed]; followed_ids.append(current_user.id)
    users = User.query.filter(User.id.notin_(followed_ids)).order_by(db.func.random()).limit(15).all()
    return render_template('discover.html', users=users)

@app.route('/<username>/<list_type>')
@login_required
def user_list(username, list_type):
    user = User.query.filter_by(username=username).first_or_404()
    if list_type == 'followers':
        users = user.followers.all(); title = "Followers"
    elif list_type == 'following':
        users = user.followed.all(); title = "Following"
    else:
        return "Invalid list type", 404
    return render_template('_user_list_modal.html', users=users, title=title)

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: current_user.follow(user); db.session.commit()
    return redirect(request.args.get('next') or request.referrer or url_for('profile', username=username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: current_user.unfollow(user); db.session.commit()
    return redirect(request.args.get('next') or request.referrer or url_for('profile', username=username))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True); return redirect(url_for('home'))
        flash('Invalid username or password.', 'error')
    return render_template('auth_form.html', title="Login", form_type="login")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already taken.', 'error'); return redirect(url_for('signup'))
        new_user = User(username=request.form['username'])
        new_user.set_password(request.form['password'])
        db.session.add(new_user); db.session.commit()
        flash('Account created! Please log in.', 'success'); return redirect(url_for('login'))
    return render_template('auth_form.html', title="Sign Up", form_type="signup")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(app.config['PFP_FOLDER']): os.makedirs(app.config['PFP_FOLDER'])
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)