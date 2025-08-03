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
app.config['SECRET_KEY'] = 'the-final-complete-polished-key-for-sixsec'
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
            align-items: flex-end; justify-content: center;
        }
        .modal-content {
            background-color: var(--bg-color); margin: auto auto 0 auto;
            border-radius: 16px 16px 0 0; width: 100%; max-width: 600px;
            max-height: 80vh; display: flex; flex-direction: column;
            animation: slideUp 0.3s ease;
        }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        .modal-header { padding: 12px 16px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; }
        .modal-header .close { font-size: 24px; font-weight: bold; cursor: pointer; padding: 0 8px; }
        .modal-body { flex-grow: 1; padding: 16px; overflow-y: auto; }
        .modal-footer { padding: 8px 16px; border-top: 1px solid var(--border-color); }
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
            <div style="position:fixed; top:60px; left:50%; transform:translateX(-50%); z-index: 9999; max-width: 90%;">
                {% for category, message in messages %}
                <div style="padding: 12px 16px; border-radius: 8px; margin-bottom: 15px; background-color: {% if category == 'error' %}var(--red-color){% else %}var(--accent-color){% endif %}; color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3); text-align: center;">{{ message }}</div>
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
        <a href="{{ url_for('profile', username=current_user.username) }}">{{ ICONS.profile|safe }}</a>
    </nav>
    {% endif %}

    <div id="commentModal" class="modal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="close" onclick="closeCommentModal()">×</span>
          <h4 style="margin:0; padding-left:16px;">Comments</h4>
        </div>
        <div class="modal-body" id="comment-list"></div>
        <div class="modal-footer">
          <form id="comment-form" style="display: flex; gap: 8px;">
            <input type="text" id="comment-text-input" class="form-group" placeholder="Add a comment..." style="margin:0; flex-grow:1;">
            <input type="hidden" id="comment-post-id">
            <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
          </form>
        </div>
      </div>
    </div>
    
    <script>
    const commentModal = document.getElementById('commentModal');
    async function openCommentModal(postId) {
        document.getElementById('comment-post-id').value = postId;
        const list = document.getElementById('comment-list');
        list.innerHTML = '<p>Loading...</p>';
        commentModal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        const response = await fetch(`/post/${postId}/comments`);
        const comments = await response.json();
        list.innerHTML = '';
        if (comments.length === 0) {
            list.innerHTML = '<p style="text-align:center; color: var(--text-muted);">No comments yet.</p>';
        } else {
            comments.forEach(c => {
                const div = document.createElement('div');
                div.style = "display:flex; gap:12px; margin-bottom:16px;";
                div.innerHTML = `<div style="width:40px; height:40px; border-radius:50%; flex-shrink:0; background:${c.user.pfp_gradient}; display:flex; align-items:center; justify-content:center; font-weight:bold;">${c.user.initial}</div>
                                 <div><strong style="color:var(--text-color);">${c.user.username}</strong> <span style="color:var(--text-muted);">${c.timestamp}</span><div style="color:var(--text-color);">${c.text}</div></div>`;
                list.appendChild(div);
            });
        }
    }
    function closeCommentModal() {
        commentModal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
    document.getElementById('comment-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const postId = document.getElementById('comment-post-id').value;
        const text = document.getElementById('comment-text-input').value;
        if (!text.trim()) return;
        const response = await fetch(`/post/${postId}/comment`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        if (response.ok) {
            document.getElementById('comment-text-input').value = '';
            openCommentModal(postId);
            const countEl = document.querySelector(`#comment-count-${postId}`);
            if(countEl) countEl.innerText = parseInt(countEl.innerText) + 1;
        }
    });
    window.onclick = (event) => { if (event.target == commentModal) closeCommentModal(); };
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
        padding: 16px; padding-bottom: 53px; pointer-events: none;
        background: linear-gradient(to top, rgba(0,0,0,0.4), transparent 40%);
        text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
    }
    .six-info { pointer-events: auto; }
    .six-info .username { font-weight: bold; font-size: 1.1em; }
    .six-actions {
        display: flex; flex-direction: column; gap: 20px;
        pointer-events: auto;
    }
    .six-actions button {
        background: none; border: none; color: white;
        display: flex; flex-direction: column; align-items: center;
        gap: 5px; cursor: pointer; font-size: 13px;
    }
    .six-actions svg { width: 32px; height: 32px; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5)); }
    .six-actions .liked svg { fill: var(--red-color); stroke: var(--red-color); }
    {% endif %}
{% endblock %}
{% block content %}
    <div class="feed-nav" style="display: flex; border-bottom: 1px solid var(--border-color);">
        <a href="{{ url_for('home', feed_type='text') }}" style="flex:1; text-align:center; padding: 15px; color: {% if feed_type == 'text' %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">Text {% if feed_type == 'text' %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
        <a href="{{ url_for('home', feed_type='sixs') }}" style="flex:1; text-align:center; padding: 15px; color: {% if feed_type == 'sixs' %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">Sixs {% if feed_type == 'sixs' %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
    </div>

    {% if feed_type == 'text' %}
        <div style="border-bottom: 1px solid var(--border-color); padding: 12px 16px;">
            <form method="POST" action="{{ url_for('create_text_post') }}" enctype="multipart/form-data">
                <div class="form-group" style="margin-bottom: 1rem;">
                    <textarea name="text_content" rows="3" placeholder="What's happening?" required maxlength="150" style="resize:vertical;"></textarea>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <input type="file" name="image" accept="image/png, image/jpeg, image/gif">
                    <button type="submit" class="btn">Post</button>
                </div>
            </form>
        </div>
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
                        <button onclick="handleRepost(this, {{ post.id }})">{{ ICONS.repost|safe }}</button>
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
    {% endif %}
{% endblock %}
{% block scripts %}
{% if feed_type == 'sixs' %}
<script>
    const videos = document.querySelectorAll('.six-video');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) { entry.target.play(); } else { entry.target.pause(); }
        });
    }, { threshold: 0.5 });
    videos.forEach(video => observer.observe(video));
    
    async function handleLike(button, postId) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        button.querySelector('span').innerText = data.likes;
        button.classList.toggle('liked', data.liked);
    }
    async function handleRepost(button, postId) {
        const response = await fetch(`/repost/${postId}`, { method: 'POST' });
        const data = await response.json();
        if(data.success) {
            button.style.color = 'var(--accent-color)';
            alert('Reposted!');
        } else {
            alert(data.message);
        }
    }
</script>
{% endif %}
{% endblock %}
""",

"post_card_text.html": """
<div style="border-bottom: 1px solid var(--border-color); padding: 12px 16px; display:flex; gap:12px;">
    <div style="width:40px; flex-shrink:0;">
        <div style="width:40px; height:40px; border-radius:50%; background:{{ post.author.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">
            {{ post.author.username[0]|upper }}
        </div>
    </div>
    <div style="flex-grow:1;">
        <div>
            <a href="{{ url_for('profile', username=post.author.username) }}" style="color:var(--text-color); font-weight:bold;">{{ post.author.username }}</a>
            <span style="color:var(--text-muted);">· {{ post.timestamp.strftime('%b %d') }}</span>
        </div>
        <p style="margin: 4px 0 12px 0;">{{ post.text_content }}</p>
        {% if post.image_filename %}
            <img src="{{ url_for('static', filename='uploads/' + post.image_filename) }}" style="width:100%; border-radius:16px; margin-bottom:12px; border: 1px solid var(--border-color);">
        {% endif %}
        <div style="display: flex; justify-content: space-between; max-width: 425px; color:var(--text-muted);">
            <button onclick="openCommentModal({{ post.id }})" style="background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer;">{{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span></button>
            <button onclick="handleRepostText(this, {{ post.id }})" style="background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer;">{{ ICONS.repost|safe }}</button>
            <button onclick="handleLikeText(this, {{ post.id }})" class="{{ 'liked' if post.liked_by_current_user else '' }}" style="background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer;">{{ ICONS.like|safe }} <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span></button>
        </div>
    </div>
</div>
<script>
    async function handleLikeText(button, postId) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        button.querySelector('span').innerText = data.likes;
        button.classList.toggle('liked', data.liked);
        if(data.liked) button.style.color = 'var(--red-color)'; else button.style.color = 'var(--text-muted)';
    }
    async function handleRepostText(button, postId) {
        const response = await fetch(`/repost/${postId}`, { method: 'POST' });
        const data = await response.json();
        if(data.success) button.style.color = 'var(--accent-color)';
        alert(data.message);
    }
</script>
""",
"create_post.html": """
{% extends "layout.html" %}
{% block header_title %}Create{% endblock %}
{% block content %}
    <div style="padding:16px;">
        <div id="six-creator" style="text-align: center;">
            <p id="recorder-status" style="color:var(--text-muted); min-height: 20px;">Allow camera access to start</p>
            <div style="width:100%; max-width: 400px; margin: 15px auto; aspect-ratio: 1/1; border-radius:50%; overflow:hidden; background:#111;">
                <video id="video-preview" autoplay muted playsinline style="width:100%; height:100%; object-fit:cover;"></video>
            </div>
            <button id="record-button" class="btn btn-danger" style="width: 80px; height: 80px; border-radius: 50%;" disabled></button>
            <form id="six-form-element" method="POST" enctype="multipart/form-data" style="display: none; margin-top: 20px;">
                 <input type="hidden" name="post_type" value="six">
                 <div class="form-group"> <input type="text" name="caption" maxlength="50" placeholder="Add a caption... (optional)"> </div>
                 <button type="submit" class="btn" style="width: 100%;">Post Six</button>
            </form>
        </div>
    </div>
{% endblock %}
{% block scripts %}
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
            recorderStatus.textContent = "Tap the button to record";
            recordButton.disabled = false;
        } catch (e) { recorderStatus.textContent = "Camera/Mic permission denied."; }
    }
    
    document.addEventListener('DOMContentLoaded', initCamera);

    recordButton.addEventListener('click', () => {
        if (recordButton.classList.contains('recording')) {
            mediaRecorder.stop();
        } else if (recordButton.classList.contains('previewing')) {
            resetRecorder();
        } else {
            startRecording();
        }
    });

    function startRecording() {
        recordedBlobs = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
        mediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) recordedBlobs.push(e.data); };
        mediaRecorder.onstop = handleStop;
        mediaRecorder.start();
        recordButton.classList.add('recording');
        recorderStatus.textContent = 'Recording...';
        setTimeout(() => { if (mediaRecorder.state === "recording") mediaRecorder.stop(); }, 6000);
    }
    
    function handleStop() {
        recordButton.classList.remove('recording');
        recordButton.classList.add('previewing');
        recorderStatus.textContent = 'Previewing... Tap to re-record.';
        const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
        preview.srcObject = null;
        preview.src = window.URL.createObjectURL(superBuffer);
        preview.muted = false; preview.controls = true;
        sixForm.style.display = 'block';
    }

    function resetRecorder() {
        sixForm.style.display = 'none';
        recordButton.classList.remove('previewing');
        preview.srcObject = stream;
        preview.controls = false; preview.muted = true;
        recorderStatus.textContent = "Tap the button to record";
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
{% endblock %}
""",

"edit_profile.html": """
{% extends "layout.html" %}
{% block header_title %}Settings{% endblock %}
{% block content %}
<div style="padding:16px;">
    <h4>Edit Profile</h4>
    <form method="POST" action="{{ url_for('edit_profile') }}">
        <div class="form-group">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" value="{{ current_user.username }}" required minlength="3" maxlength="80">
        </div>
        <div class="form-group">
            <label for="bio">Bio</label>
            <textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea>
        </div>
        <button type="submit" class="btn">Save Changes</button>
    </form>
    <hr style="border-color: var(--border-color); margin: 30px 0;">
    <h4>Account Actions</h4>
    <div style="border: 1px solid var(--red-color); border-radius: 8px; padding: 16px;">
        <h5 style="margin-top:0;">Delete Account</h5>
        <p style="color:var(--text-muted);">This action is permanent. All your posts, comments, likes, and follower data will be removed.</p>
        <form action="{{ url_for('delete_account') }}" method="POST">
             <div class="form-group"><label for="password">Confirm with your password</label><input type="password" id="password" name="password" required></div>
            <button type="submit" class="btn btn-danger" onclick="return confirm('Are you absolutely sure?')">Delete My Account</button>
        </form>
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
            <div style="width: 80px; height: 80px; border-radius:50%; background: {{ user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-size: 2.5rem; font-weight:bold;">{{ user.username[0]|upper }}</div>
            <div style="text-align: right;">
            {% if current_user != user %}
                {% if not current_user.is_following(user) %} <a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>
                {% else %} <a href="{{ url_for('unfollow', username=user.username) }}" class="btn btn-outline">Following</a> {% endif %}
            {% endif %}
            </div>
        </div>
        <h2 style="margin: 12px 0 0 0;">{{ user.username }}</h2>
        <p style="color: var(--text-muted); margin: 4px 0 12px 0;">{{ user.bio or "No bio yet." }}</p>
        <div style="display:flex; gap: 16px; color:var(--text-muted);">
            <span><strong style="color:var(--text-color)">{{ user.followers.count() }}</strong> Followers</span>
            <span><strong style="color:var(--text-color)">{{ user.followed.count() }}</strong> Following</span>
        </div>
    </div>
    <div class="feed-nav" style="display: flex; border-bottom: 1px solid var(--border-color);">
        {% set tabs = [('Posts', url_for('profile', username=user.username, tab='posts')), ('Reposts', url_for('profile', username=user.username, tab='reposts')), ('Likes', url_for('profile', username=user.username, tab='likes'))] %}
        {% for name, url in tabs %}
        <a href="{{ url }}" style="flex:1; text-align:center; padding: 15px; color: {% if active_tab == name.lower() %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">{{ name }} {% if active_tab == name.lower() %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
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
    <div style="padding: 16px; border-bottom: 1px solid var(--border-color);">
        <form method="GET" action="{{ url_for('discover') }}">
            <div style="display: flex; gap: 8px;">
                <input type="search" name="q" placeholder="Search for users..." class="form-group" style="margin:0; flex-grow:1;" value="{{ request.args.get('q', '') }}">
                <button type="submit" class="btn">{{ ICONS.discover|safe }}</button>
            </div>
        </form>
    </div>
    {% for user in users %}
    <div style="border-bottom: 1px solid var(--border-color); padding:12px 16px; display:flex; align-items:center; gap:12px;">
        <div style="width: 40px; height: 40px; border-radius:50%; flex-shrink:0; background: {{ user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">{{ user.username[0]|upper }}</div>
        <div style="flex-grow:1;">
            <a href="{{ url_for('profile', username=user.username) }}" style="color:var(--text-color); font-weight:bold;">{{ user.username }}</a>
            <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ user.bio|truncate(50) if user.bio else 'No bio yet.' }}</p>
        </div>
        <div>
            {% if user != current_user %}
                {% if not current_user.is_following(user) %}
                    <a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>
                {% else %}
                    <a href="{{ url_for('unfollow', username=user.username) }}" class="btn btn-outline">Following</a>
                {% endif %}
            {% endif %}
        </div>
    </div>
    {% else %}
        <p style="text-align:center; padding: 40px; color: var(--text-muted);">No users found.</p>
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
        {% if form_type == 'signup' %}<div class="form-group"><label for="bio">Bio (optional)</label><textarea id="bio" name="bio" rows="3"></textarea></div>{% endif %}
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
reposts = db.Table('reposts',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')), db.Column('post_id', db.Integer, db.ForeignKey('post.id')))
likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')), db.Column('post_id', db.Integer, db.ForeignKey('post.id')))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(150))
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Post.user_id')
    reposts = db.relationship('Post', secondary=reposts, backref=db.backref('reposted_by', lazy='dynamic'), lazy='dynamic')
    liked_posts = db.relationship('Post', secondary=likes, backref=db.backref('liked_by', lazy='dynamic'), lazy='dynamic')
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
    post_type = db.Column(db.String(10), nullable=False)
    text_content = db.Column(db.String(150))
    video_filename = db.Column(db.String(120))
    image_filename = db.Column(db.String(120), nullable=True) # ADDED: For text post images
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan")

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
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    query = Post.query.filter(Post.user_id.in_(followed_ids))
    if feed_type == 'text':
        posts = query.filter_by(post_type='text').order_by(Post.timestamp.desc()).all()
    else: # sixs
        posts = query.filter_by(post_type='six').order_by(Post.timestamp.desc()).all()
    for p in posts: p.liked_by_current_user = current_user in p.liked_by
    return render_template('home.html', posts=posts, feed_type=feed_type)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    active_tab = request.args.get('tab', 'posts')
    if active_tab == 'reposts': posts = user.reposts.order_by(Post.timestamp.desc()).all()
    elif active_tab == 'likes': posts = user.liked_posts.order_by(Post.timestamp.desc()).all()
    else: posts = user.posts.filter_by(post_type='text').order_by(Post.timestamp.desc()).all()
    for p in posts: p.liked_by_current_user = current_user in p.liked_by
    return render_template('profile.html', user=user, posts=posts, active_tab=active_tab)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form.get('post_type')
        if post_type == 'text':
             # This functionality is now handled by create_text_post from the home feed
            flash('Text posts can be made from the home feed.', 'info'); return redirect(url_for('home'))
        elif post_type == 'six':
            video_file = request.files.get('video_file')
            if not video_file: flash('Video data not received.', 'error'); return redirect(url_for('create_post'))
            filename = secure_filename(f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.webm")
            video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post = Post(post_type='six', text_content=request.form.get('caption', ''), video_filename=filename, author=current_user)
            db.session.add(post); db.session.commit()
            flash('Six posted successfully!', 'success'); return redirect(url_for('home', feed_type='sixs'))
    return render_template('create_post.html')

@app.route('/create_text_post', methods=['POST'])
@login_required
def create_text_post():
    text = request.form.get('text_content')
    image_file = request.files.get('image')
    filename = None
    if not text or not text.strip():
        flash('Post content cannot be empty.', 'error')
        return redirect(url_for('home'))
    if image_file and image_file.filename != '':
        filename = secure_filename(f"img_{current_user.id}_{int(datetime.datetime.now().timestamp())}{os.path.splitext(image_file.filename)[1]}")
        image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    post = Post(post_type='text', text_content=text, image_filename=filename, author=current_user)
    db.session.add(post); db.session.commit()
    flash('Post created!', 'success')
    return redirect(url_for('home', feed_type='text'))

@app.route('/post/<int:post_id>/comments')
@login_required
def get_comments(post_id):
    comments_data = [{'text': c.text, 'timestamp': c.timestamp.strftime('%b %d'), 'user': {'username': c.user.username, 'pfp_gradient': c.user.pfp_gradient, 'initial': c.user.username[0].upper()}} for c in Post.query.get_or_404(post_id).comments.order_by(Comment.timestamp.asc()).all()]
    return jsonify(comments_data)

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    data = request.get_json(); text = data.get('text', '').strip()
    if not text: return jsonify({'error': 'Comment text is required'}), 400
    comment = Comment(text=text, user_id=current_user.id, post_id=post_id)
    db.session.add(comment); db.session.commit()
    return jsonify({'success': True}), 201

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user in post.liked_by: post.liked_by.remove(current_user); liked = False
    else: post.liked_by.append(current_user); liked = True
    db.session.commit()
    return jsonify({'liked': liked, 'likes': len(post.liked_by.all())})

@app.route('/repost/<int:post_id>', methods=['POST'])
@login_required
def repost(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author == current_user: return jsonify({'success': False, 'message': "You can't repost your own post."})
    if post in current_user.reposts: current_user.reposts.remove(post); message = "Repost removed."
    else: current_user.reposts.append(post); message = "Post reposted!"
    db.session.commit()
    return jsonify({'success': True, 'message': message})

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_bio = request.form.get('bio', current_user.bio).strip()

        # Handle username change
        if new_username and new_username != current_user.username:
            # Case-insensitive check for existing user
            existing_user = User.query.filter(User.username.ilike(new_username)).first()
            if existing_user:
                flash('Username is already taken.', 'error')
                return redirect(url_for('edit_profile'))
            current_user.username = new_username
        
        # Handle bio change
        current_user.bio = new_bio
        
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    
    return render_template('edit_profile.html')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    if not current_user.check_password(request.form.get('password')):
        flash('Incorrect password. Account not deleted.', 'error')
        return redirect(url_for('edit_profile'))
    user_id = current_user.id
    logout_user() # Log out before deleting
    user = User.query.get(user_id)
    db.session.delete(user); db.session.commit()
    flash('Your account has been permanently deleted.', 'success')
    return redirect(url_for('login'))

@app.route('/discover')
@login_required
def discover():
    query = request.args.get('q')
    if query:
        # Search for users by username, case-insensitive, excluding self
        search_term = f"%{query}%"
        users = User.query.filter(User.username.ilike(search_term), User.id != current_user.id).all()
    else:
        # Show random users if no query, excluding self
        users = User.query.filter(User.id != current_user.id).order_by(db.func.random()).limit(20).all()
    return render_template('discover.html', users=users)

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
        username = request.form.get('username').strip()
        if User.query.filter(User.username.ilike(username)).first():
            flash('Username already taken.', 'error'); return redirect(url_for('signup'))
        new_user = User(username=username, bio=request.form.get('bio', ''))
        new_user.set_password(request.form['password'])
        db.session.add(new_user); db.session.commit()
        flash('Account created! Please log in.', 'success'); return redirect(url_for('login'))
    return render_template('auth_form.html', title="Sign Up", form_type="signup")

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)