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
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB

# --- INITIALIZE EXTENSIONS & HELPERS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

ICONS = {
    'home': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
    'discover': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    'create': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M12 5v14m-7-7h14" stroke="var(--bg-color)" stroke-width="2" stroke-linecap="round"/></svg>',
    'profile': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>',
    'like': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
    'comment': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>',
    'repost': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>',
    'send': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>',
    'settings': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>',
    'text': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path><line x1="9" y1="10" x2="15" y2="10"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg>',
    'video': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>',
    'close': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
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
        .modal-content-center { animation: none; border-radius: 16px; margin: auto; }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        .modal-header { padding: 12px 16px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; }
        .modal-header .close-btn { background: none; border: none; color: var(--text-color); cursor: pointer; padding: 4px; }
        .modal-body { flex-grow: 1; padding: 16px; overflow-y: auto; }
        .modal-footer { padding: 8px 16px; border-top: 1px solid var(--border-color); }
        .avatar {
            width: 40px; height: 40px; border-radius: 50%;
            background-size: cover; background-position: center;
            display: flex; align-items: center; justify-content: center;
            font-weight: bold; flex-shrink: 0;
        }
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

    <div id="commentModal" class="modal">
      <div class="modal-content">
        <div class="modal-header">
          <button class="close-btn" onclick="closeCommentModal()">{{ ICONS.close|safe }}</button>
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
    
    <div id="repostModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <button class="close-btn" onclick="closeRepostModal()">{{ ICONS.close|safe }}</button>
                <h4 style="margin:0; padding-left:16px;">Repost</h4>
            </div>
            <div class="modal-body">
                <form id="repost-form">
                    <div class="form-group">
                        <textarea name="caption" id="repost-caption" rows="4" placeholder="Add a comment... (optional)"></textarea>
                    </div>
                    <input type="hidden" id="repost-post-id">
                    <button type="submit" class="btn" style="width:100%;">Repost</button>
                </form>
                <div id="repost-preview" style="margin-top: 15px; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px;"></div>
            </div>
        </div>
    </div>

    <script>
    const commentModal = document.getElementById('commentModal');
    const repostModal = document.getElementById('repostModal');
    
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
                const pfp = c.user.pfp_filename ? `url(${c.user.pfp_filename})` : c.user.pfp_gradient;
                const pfp_content = c.user.pfp_filename ? '' : c.user.initial;
                const div = document.createElement('div');
                div.style = "display:flex; gap:12px; margin-bottom:16px;";
                div.innerHTML = `<div class="avatar" style="background-image:${pfp};">${pfp_content}</div>
                                 <div>
                                    <strong style="color:var(--text-color);">${c.user.username}</strong> <span style="color:var(--text-muted);">${c.timestamp}</span>
                                    <div style="color:var(--text-color); margin-top: 4px;">${c.text}</div>
                                    <button onclick="handleRepostText(this, ${c.id}, 'comment')" style="background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer; padding:0; margin-top:8px;">${ICONS.repost|safe}</button>
                                 </div>`;
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
    
    async function openRepostModal(postId, postType = 'post') {
        document.getElementById('repost-post-id').value = postId;
        repostModal.style.display = 'flex';
        const preview = document.getElementById('repost-preview');
        preview.innerHTML = 'Loading preview...';
        // Fetch post content for preview
        const response = await fetch(`/get_post_json/${postId}?type=${postType}`);
        const post = await response.json();
        const pfp = post.author.pfp_filename ? `url(${post.author.pfp_filename})` : post.author.pfp_gradient;
        const pfp_content = post.author.pfp_filename ? '' : post.author.initial;
        preview.innerHTML = `<div style="display:flex; gap:12px;">
                                <div class="avatar" style="background-image: ${pfp};">${pfp_content}</div>
                                <div><strong>${post.author.username}</strong><p style="margin:4px 0 0 0;">${post.content}</p></div>
                             </div>`;
    }

    function closeRepostModal() {
        repostModal.style.display = 'none';
        document.getElementById('repost-form').reset();
    }
    
    document.getElementById('repost-form').addEventListener('submit', async(e) => {
        e.preventDefault();
        const postId = document.getElementById('repost-post-id').value;
        const caption = document.getElementById('repost-caption').value;
        
        const response = await fetch(`/repost/${postId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ caption: caption })
        });
        const data = await response.json();
        alert(data.message);
        if(data.success) closeRepostModal();
    });

    window.onclick = (event) => { 
        if (event.target == commentModal) closeCommentModal(); 
        if (event.target == repostModal) closeRepostModal();
    };
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
""",

"home.html": """
{% extends "layout.html" %}
{% block style_override %}
    {% if feed_type == 'sixs' %}
    #sixs-feed-container { height: 100dvh; width: 100vw; overflow-y: scroll; scroll-snap-type: y mandatory; background-color: #000; position: fixed; top: 0; left: 0; }
    .six-video-slide { height: 100dvh; width: 100vw; scroll-snap-align: start; position: relative; display: flex; justify-content: center; align-items: center; }
    .six-video-wrapper { position: relative; width: 100vw; height: 100vw; max-width: 100dvh; max-height: 100dvh; clip-path: circle(50% at 50% 50%); }
    .six-video { width: 100%; height: 100%; object-fit: cover; }
    .six-ui-overlay { position: absolute; bottom: 0; left: 0; right: 0; top: 0; color: white; display: flex; justify-content: space-between; align-items: flex-end; padding: 16px; padding-bottom: 70px; pointer-events: none; background: linear-gradient(to top, rgba(0,0,0,0.4), transparent 40%); text-shadow: 1px 1px 3px rgba(0,0,0,0.5); }
    .six-info { pointer-events: auto; }
    .six-info .username { font-weight: bold; font-size: 1.1em; }
    .six-actions { display: flex; flex-direction: column; gap: 20px; pointer-events: auto; align-items: center; }
    .six-actions button { background: none; border: none; color: white; display: flex; flex-direction: column; align-items: center; gap: 5px; cursor: pointer; font-size: 13px; padding: 0; }
    .six-actions svg { width: 32px; height: 32px; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5)); }
    .six-actions .liked svg { fill: var(--red-color); stroke: var(--red-color); }
    .six-actions .reposted svg { color: var(--accent-color); fill: var(--accent-color); }
    {% endif %}
    .feed-nav { display: flex; border-bottom: 1px solid var(--border-color); background: rgba(0, 0, 0, 0.65); backdrop-filter: blur(12px) saturate(180%); -webkit-backdrop-filter: blur(12px) saturate(180%); position: sticky; top: 53px; z-index: 999; }
{% endblock %}
{% block content %}
    <div class="feed-nav">
        <a href="{{ url_for('home', feed_type='text') }}" style="flex:1; text-align:center; padding: 15px; color: {% if feed_type == 'text' %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">Text {% if feed_type == 'text' %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
        <a href="{{ url_for('home', feed_type='sixs') }}" style="flex:1; text-align:center; padding: 15px; color: {% if feed_type == 'sixs' %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">Sixs {% if feed_type == 'sixs' %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
    </div>

    {% if feed_type == 'text' %}
        {% for post in posts %}
            {% include 'post_card_text.html' %}
        {% else %}
            <div style="text-align:center; padding: 40px; color:var(--text-muted);"><h4>Your feed is empty.</h4><p>Follow accounts on the <a href="{{ url_for('discover') }}">Discover</a> page!</p></div>
        {% endfor %}
    {% elif feed_type == 'sixs' %}
        <div id="sixs-feed-container">
            {% for post in posts %}
            <section class="six-video-slide" data-post-id="{{ post.id }}">
                <div class="six-video-wrapper"><video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop preload="auto" playsinline muted></video></div>
                <div class="six-ui-overlay">
                    <div class="six-info">
                        <a href="{{ url_for('profile', username=post.author.username) }}" style="color:white;"><strong class="username">@{{ post.author.username }}</strong></a>
                        <p>{{ post.text_content }}</p>
                    </div>
                    <div class="six-actions">
                        <button onclick="handleLike(this, {{ post.id }})" class="{{ 'liked' if post.liked_by_current_user else '' }}">{{ ICONS.like|safe }}<span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span></button>
                        <button onclick="openCommentModal({{ post.id }})">{{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span></button>
                        <button onclick="handleRepost(this, {{ post.id }})" class="{{ 'reposted' if post.reposted_by_current_user else '' }}">{{ ICONS.repost|safe }}</button>
                    </div>
                </div>
            </section>
            {% else %}
            <section class="six-video-slide" style="flex-direction:column; text-align:center; color:white;"><h4>No Sixs to show!</h4><p style="color:#aaa;">Follow accounts or create your own.</p><a href="{{ url_for('create_post') }}" class="btn" style="margin-top:20px;">Create a Six</a></section>
            {% endfor %}
        </div>
        <nav class="bottom-nav" style="position:fixed; z-index:1001; bottom:0; left:0; right:0;"><a href="{{ url_for('home') }}" class="{{ 'active' if request.endpoint == 'home' else '' }}">{{ ICONS.home|safe }}</a><a href="{{ url_for('discover') }}" class="{{ 'active' if request.endpoint == 'discover' else '' }}">{{ ICONS.discover|safe }}</a><a href="{{ url_for('create_post') }}" class="create-btn">{{ ICONS.create|safe }}</a><a href="{{ url_for('profile', username=current_user.username) }}">{{ ICONS.profile|safe }}</a></nav>
    {% endif %}
{% endblock %}
{% block scripts %}
{% if feed_type == 'sixs' %}
<script>
    const videos = document.querySelectorAll('.six-video');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target;
            if (entry.isIntersecting) { video.play().catch(e => console.log("Play interrupted")); video.muted = video.dataset.muted === 'true' || typeof video.dataset.muted === 'undefined'; } 
            else { video.pause(); video.currentTime = 0; }
        });
    }, { threshold: 0.5 });
    videos.forEach(video => {
        observer.observe(video);
        video.addEventListener('click', () => { video.muted = !video.muted; video.dataset.muted = video.muted; });
    });
    
    async function handleRepost(button, postId) {
        const isReposted = button.classList.contains('reposted');
        if (isReposted) {
             const response = await fetch(`/unrepost/${postId}`, { method: 'POST' });
             const data = await response.json();
             if(data.success) button.classList.remove('reposted');
             flashMessage(data.message);
        } else {
            openRepostModal(postId);
        }
    }
    
    function flashMessage(message, isError = false) {
        let flashDiv = document.createElement('div');
        flashDiv.textContent = message;
        flashDiv.style.cssText = `position:fixed; bottom:80px; left:50%; transform:translateX(-50%); padding:12px 20px; border-radius:20px; background:${isError ? 'var(--red-color)' : 'var(--accent-color)'}; color:white; z-index:9999; box-shadow:0 4px 10px rgba(0,0,0,0.3);`;
        document.body.appendChild(flashDiv);
        setTimeout(() => flashDiv.remove(), 3000);
    }
</script>
{% endif %}
<script>
    async function handleLike(button, postId) {
        const response = await fetch(`/like/${postId}`, { method: 'POST' });
        const data = await response.json();
        const icon = button.querySelector('svg');
        button.querySelector('span').innerText = data.likes;
        button.classList.toggle('liked', data.liked);
        if(data.liked) icon.style.fill = 'var(--red-color)'; else icon.style.fill = 'none';
    }

    async function handleRepostText(button, postId, postType = 'post') {
        const isReposted = button.classList.contains('reposted');
        if(isReposted) {
             const response = await fetch(`/unrepost/${postId}`, { method: 'POST' });
             const data = await response.json();
             if(data.success) {
                 button.classList.remove('reposted');
                 button.style.color = 'var(--text-muted)';
             }
             alert(data.message);
        } else {
            openRepostModal(postId, postType);
        }
    }
</script>
{% endblock %}
""",

"post_card_text.html": """
<div style="border-bottom: 1px solid var(--border-color); padding: 12px 16px;">
    {% if post.repost_of %}
    <div style="color: var(--text-muted); font-size: 0.9em; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
        {{ ICONS.repost|safe }} Reposted by <a href="{{ url_for('profile', username=post.author.username) }}" style="color:var(--text-muted); font-weight:bold;">{{ post.author.username }}</a>
    </div>
    <p style="margin: 4px 0 12px 0;">{{ post.text_content }}</p> {# This is the caption of the repost #}
    {% set original_post = post.repost_of %}
    <div style="border: 1px solid var(--border-color); border-radius: 12px; padding: 12px;">
    {% else %}
    {% set original_post = post %}
    {% endif %}

    <div style="display:flex; gap:12px;">
        <a href="{{ url_for('profile', username=original_post.author.username) }}">
            <div class="avatar" style="background-image: {{ 'url(' + url_for('static', filename='uploads/' + original_post.author.pfp_filename) + ')' if original_post.author.pfp_filename else original_post.author.pfp_gradient }};">
                {% if not original_post.author.pfp_filename %}{{ original_post.author.username[0]|upper }}{% endif %}
            </div>
        </a>
        <div style="flex-grow:1;">
            <div>
                <a href="{{ url_for('profile', username=original_post.author.username) }}" style="color:var(--text-color); font-weight:bold;">{{ original_post.author.username }}</a>
                <span style="color:var(--text-muted);">· {{ original_post.timestamp.strftime('%b %d') }}</span>
            </div>
            <p style="margin: 4px 0 12px 0;">{{ original_post.text_content }}</p>
            <div style="display: flex; justify-content: space-between; max-width: 425px; color:var(--text-muted);">
                <button onclick="openCommentModal({{ original_post.id }})" style="background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer; padding:0;">{{ ICONS.comment|safe }} <span id="comment-count-{{ original_post.id }}">{{ original_post.comments.count() }}</span></button>
                <button onclick="handleRepostText(this, {{ original_post.id }})" class="{{ 'reposted' if original_post.reposted_by_current_user else '' }}" style="background:none; border:none; color:{{ 'var(--accent-color)' if original_post.reposted_by_current_user else 'var(--text-muted)' }}; display:flex; align-items:center; gap:8px; cursor:pointer; padding:0;">{{ ICONS.repost|safe }}</button>
                <button onclick="handleLike(this, {{ original_post.id }})" class="{{ 'liked' if original_post.liked_by_current_user else '' }}" style="background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer; padding:0;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="{{ 'var(--red-color)' if original_post.liked_by_current_user else 'none' }}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: {{ 'var(--red-color)' if original_post.liked_by_current_user else 'var(--text-muted)' }}"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                    <span id="like-count-{{ original_post.id }}">{{ original_post.liked_by.count() }}</span>
                </button>
            </div>
        </div>
    </div>
    {% if post.repost_of %}</div>{% endif %}
</div>
""",
"create_post.html": """
{% extends "layout.html" %}
{% block header_title %}Create{% endblock %}
{% block content %}
<div style="padding:16px;">
    <div class="feed-nav" style="position:static; border-radius: 8px; overflow: hidden; margin-bottom: 24px;">
        <a href="{{ url_for('create_post', type='text') }}" style="flex:1; text-align:center; padding: 15px; background: {% if type == 'text' %}var(--border-color){% else %}transparent{% endif %}; font-weight:bold;">{{ ICONS.text|safe }} Text</a>
        <a href="{{ url_for('create_post', type='six') }}" style="flex:1; text-align:center; padding: 15px; background: {% if type == 'six' %}var(--border-color){% else %}transparent{% endif %}; font-weight:bold;">{{ ICONS.video|safe }} Six</a>
    </div>

    {% if type == 'text' %}
    <form method="POST" action="{{ url_for('create_post', type='text') }}">
        <input type="hidden" name="post_type" value="text">
        <div class="form-group">
            <textarea name="text_content" rows="6" placeholder="What's happening?" maxlength="280" required></textarea>
        </div>
        <button type="submit" class="btn" style="float:right;">Post</button>
    </form>
    {% elif type == 'six' %}
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
    {% endif %}
</div>
{% endblock %}
{% block scripts %}
{% if type == 'six' %}
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
            preview.srcObject = stream; recordButton.disabled = false;
        } catch (e) { recorderStatus.textContent = "Camera/Mic permission is required."; console.error(e); }
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
        preview.srcObject = null; preview.src = window.URL.createObjectURL(superBuffer);
        preview.muted = false; preview.controls = true; preview.loop = true;
        sixForm.style.display = 'block';
    }

    function resetRecorder() {
        sixForm.style.display = 'none';
        recordButton.classList.remove('previewing');
        preview.srcObject = stream;
        preview.controls = false; preview.muted = true;
        recorderStatus.textContent = "Tap the red button to record";
    }

    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        formData.append('video_file', videoBlob, 'six-video.webm');
        const submitBtn = sixForm.querySelector('button');
        submitBtn.disabled = true; submitBtn.textContent = "Uploading...";
        fetch("{{ url_for('create_post', type='six') }}", { method: 'POST', body: formData })
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
        <div class="form-group" style="text-align:center;">
             <div class="avatar" style="width:100px; height:100px; margin:auto; background-image: {{ 'url(' + url_for('static', filename='uploads/' + current_user.pfp_filename) + ')' if current_user.pfp_filename else current_user.pfp_gradient }}; font-size:3em;">
                {% if not current_user.pfp_filename %}{{ current_user.username[0]|upper }}{% endif %}
            </div>
            <label for="pfp" style="cursor:pointer; color: var(--accent-color); margin-top:10px;">Change Profile Picture</label>
            <input type="file" name="pfp" id="pfp" style="display:none;" accept="image/*">
        </div>
        <div class="form-group"><label for="bio">Bio</label><textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea></div>
        <button type="submit" class="btn">Save Changes</button>
    </form>
    <hr style="border-color: var(--border-color); margin: 30px 0;">
    <h4>Account Actions</h4>
    <a href="{{ url_for('logout') }}" class="btn btn-outline" style="display:block; text-align:center; margin-bottom: 20px;">Log Out</a>
    <div style="border: 1px solid var(--red-color); border-radius: 8px; padding: 16px;">
        <h5 style="margin-top:0;">Delete Account</h5>
        <p style="color:var(--text-muted);">This action is permanent and cannot be undone.</p>
        <button onclick="document.getElementById('deleteModal').style.display='flex'" class="btn btn-danger">Delete My Account</button>
    </div>
</div>
<div id="deleteModal" class="modal" style="align-items:center;">
    <div class="modal-content modal-content-center">
        <div class="modal-header">
            <button class="close-btn" onclick="document.getElementById('deleteModal').style.display='none'">{{ ICONS.close|safe }}</button>
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
            <div class="avatar" style="width: 80px; height: 80px; font-size: 2.5em; background-image: {{ 'url(' + url_for('static', filename='uploads/' + user.pfp_filename) + ')' if user.pfp_filename else user.pfp_gradient }};">
                {% if not user.pfp_filename %}{{ user.username[0]|upper }}{% endif %}
            </div>
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
            <span style="cursor:pointer;" onclick="openFollowModal('{{ user.username }}', 'followers')"><strong style="color:var(--text-color)">{{ user.followers.count() }}</strong> Followers</span>
            <span style="cursor:pointer;" onclick="openFollowModal('{{ user.username }}', 'following')"><strong style="color:var(--text-color)">{{ user.followed.count() }}</strong> Following</span>
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

    <div id="followModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <button class="close-btn" onclick="closeFollowModal()">{{ ICONS.close|safe }}</button>
                <h4 id="followModalTitle" style="margin:0; padding-left:16px;"></h4>
            </div>
            <div class="modal-body" id="followModalList"></div>
        </div>
    </div>
{% endblock %}
{% block scripts %}
<script>
    const followModal = document.getElementById('followModal');
    async function openFollowModal(username, type) {
        document.getElementById('followModalTitle').textContent = type.charAt(0).toUpperCase() + type.slice(1);
        const list = document.getElementById('followModalList');
        list.innerHTML = '<p>Loading...</p>';
        followModal.style.display = 'flex';
        const response = await fetch(`/get_follows/${username}?type=${type}`);
        const users = await response.json();
        list.innerHTML = '';
        if(users.length === 0) {
            list.innerHTML = `<p style="text-align:center; color:var(--text-muted);">No users to show.</p>`;
        } else {
            users.forEach(u => {
                const pfp = u.pfp_filename ? `url(/static/uploads/${u.pfp_filename})` : u.pfp_gradient;
                const pfp_content = u.pfp_filename ? '' : u.initial;
                const div = document.createElement('div');
                div.style = "display:flex; align-items:center; gap:12px; margin-bottom:12px;";
                div.innerHTML = `<div class="avatar" style="background-image:${pfp};">${pfp_content}</div>
                                 <div><a href="/profile/${u.username}" style="color:var(--text-color); font-weight:bold;">${u.username}</a><p style="margin:2px 0; color:var(--text-muted);">${u.bio}</p></div>`;
                list.appendChild(div);
            });
        }
    }
    function closeFollowModal() { followModal.style.display = 'none'; }
    window.addEventListener('click', (e) => { if(e.target == followModal) closeFollowModal(); });
</script>
{% endblock %}
""",

"discover.html": """
{% extends "layout.html" %}
{% block header_title %}Discover{% endblock %}
{% block content %}
    {% for user in users %}
    <div style="border-bottom: 1px solid var(--border-color); padding:12px 16px; display:flex; align-items:center; gap:12px;">
        <div class="avatar" style="background-image: {{ 'url(' + url_for('static', filename='uploads/' + user.pfp_filename) + ')' if user.pfp_filename else user.pfp_gradient }};">
            {% if not user.pfp_filename %}{{ user.username[0]|upper }}{% endif %}
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

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(150))
    pfp_filename = db.Column(db.String(120), nullable=True)
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Post.user_id')
    followed = db.relationship('User', secondary=followers, primaryjoin=(followers.c.follower_id == id), secondaryjoin=(followers.c.followed_id == id), backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')
    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)
    def is_following(self, u): return self.followed.filter(followers.c.followed_id == u.id).count() > 0
    def follow(self, u):
        if not self.is_following(u): self.followed.append(u)
    def unfollow(self, u):
        if self.is_following(u): self.followed.remove(u)
    def is_reposting(self, post):
        return Post.query.filter_by(author=self, repost_of=post).count() > 0
    @property
    def pfp_gradient(self):
        colors = [("#ef4444", "#fb923c"), ("#a855f7", "#ec4899"), ("#84cc16", "#22c55e"), ("#0ea5e9", "#6366f1")]
        c1, c2 = colors[hash(self.username) % len(colors)]; return f"linear-gradient(45deg, {c1}, {c2})"

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(10), nullable=False) # 'text', 'six', 'repost'
    text_content = db.Column(db.String(280)) # Caption for six/repost, content for text
    video_filename = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    repost_of_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    repost_of = db.relationship('Post', remote_side=[id], backref='reposts')
    liked_by = db.relationship('User', secondary='likes', backref=db.backref('liked_posts', lazy='dynamic'))
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Comment.post_id')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    user = db.relationship('User')

likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True))

# --- ROUTES ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    
    if feed_type == 'text':
        posts = Post.query.filter(Post.user_id.in_(followed_ids), Post.post_type != 'six').order_by(Post.timestamp.desc()).all()
    else: # sixs
        posts = Post.query.filter(Post.user_id.in_(followed_ids), Post.post_type == 'six').order_by(Post.timestamp.desc()).all()
        
    for p in posts:
        original_post = p.repost_of if p.repost_of else p
        original_post.liked_by_current_user = current_user in original_post.liked_by
        original_post.reposted_by_current_user = current_user.is_reposting(original_post)
    return render_template('home.html', posts=posts, feed_type=feed_type)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    active_tab = request.args.get('tab', 'posts')
    if active_tab == 'reposts': posts = user.posts.filter(Post.repost_of_id != None).order_by(Post.timestamp.desc()).all()
    elif active_tab == 'likes': posts = user.liked_posts.order_by(likes.c.post_id.desc()).all()
    else: posts = user.posts.filter_by(repost_of_id=None).order_by(Post.timestamp.desc()).all()
    for p in posts:
        original_post = p.repost_of if p.repost_of else p
        original_post.liked_by_current_user = current_user in original_post.liked_by
        original_post.reposted_by_current_user = current_user.is_reposting(original_post)
    return render_template('profile.html', user=user, posts=posts, active_tab=active_tab)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    post_type = request.args.get('type', 'text')
    if request.method == 'POST':
        if post_type == 'text':
            content = request.form.get('text_content')
            if not content:
                flash('Post content cannot be empty.', 'error'); return redirect(url_for('create_post', type='text'))
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
            flash('Six posted successfully!', 'success'); return redirect(url_for('home', feed_type='sixs'))
    return render_template('create_post.html', type=post_type)

@app.route('/get_post_json/<int:post_id>')
@login_required
def get_post_json(post_id):
    post_type = request.args.get('type', 'post')
    if post_type == 'comment':
        item = Comment.query.get_or_404(post_id)
        content = item.text
    else:
        item = Post.query.get_or_404(post_id)
        content = item.text_content
    
    author = item.user if post_type == 'comment' else item.author
    return jsonify({
        'author': {
            'username': author.username, 
            'pfp_filename': url_for('static', filename='uploads/' + author.pfp_filename) if author.pfp_filename else None,
            'pfp_gradient': author.pfp_gradient,
            'initial': author.username[0].upper()
        },
        'content': content
    })

@app.route('/post/<int:post_id>/comments')
@login_required
def get_comments(post_id):
    post = Post.query.get_or_404(post_id)
    comments_data = []
    for c in post.comments.order_by(Comment.timestamp.asc()).all():
        comments_data.append({
            'id': c.id, 'text': c.text, 'timestamp': c.timestamp.strftime('%b %d'), 
            'user': {
                'username': c.user.username, 
                'pfp_filename': url_for('static', filename='uploads/' + c.user.pfp_filename) if c.user.pfp_filename else None,
                'pfp_gradient': c.user.pfp_gradient, 'initial': c.user.username[0].upper()
            }
        })
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
    return jsonify({'liked': liked, 'likes': len(post.liked_by)})

@app.route('/repost/<int:post_id>', methods=['POST'])
@login_required
def repost(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author == current_user: return jsonify({'success': False, 'message': "You can't repost your own post."})
    if current_user.is_reposting(post): return jsonify({'success': False, 'message': "You've already reposted this."})
    
    caption = request.json.get('caption', '')
    new_repost = Post(post_type='repost', text_content=caption, author=current_user, repost_of=post)
    db.session.add(new_repost)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Reposted!'})

@app.route('/unrepost/<int:post_id>', methods=['POST'])
@login_required
def unrepost(post_id):
    original_post = Post.query.get_or_404(post_id)
    repost_to_delete = Post.query.filter_by(author=current_user, repost_of=original_post).first()
    if repost_to_delete:
        db.session.delete(repost_to_delete)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Repost removed.'})
    return jsonify({'success': False, 'message': 'Repost not found.'})

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', current_user.bio)
        pfp_file = request.files.get('pfp')
        if pfp_file and allowed_file(pfp_file.filename):
            filename = secure_filename(f"pfp_{current_user.id}_{pfp_file.filename}")
            pfp_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.pfp_filename = filename
        db.session.commit(); flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    password = request.form.get('password')
    if not password or not current_user.check_password(password):
        flash('Incorrect password. Account not deleted.', 'error'); return redirect(url_for('edit_profile'))
    user_to_delete = User.query.get(current_user.id)
    logout_user()
    db.session.delete(user_to_delete); db.session.commit()
    flash('Your account has been permanently deleted.', 'success'); return redirect(url_for('login'))

@app.route('/get_follows/<username>')
@login_required
def get_follows(username):
    user = User.query.filter_by(username=username).first_or_404()
    follow_type = request.args.get('type', 'followers')
    users = user.followers if follow_type == 'followers' else user.followed
    user_list = [{
        'username': u.username, 'bio': u.bio or '', 
        'pfp_filename': u.pfp_filename, 'pfp_gradient': u.pfp_gradient, 
        'initial': u.username[0].upper()
    } for u in users]
    return jsonify(user_list)

@app.route('/discover')
@login_required
def discover():
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    users = User.query.filter(User.id.notin_(followed_ids)).order_by(db.func.random()).limit(15).all()
    return render_template('discover.html', users=users)

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: current_user.follow(user); db.session.commit()
    return redirect(request.referrer or url_for('profile', username=username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: current_user.unfollow(user); db.session.commit()
    return redirect(request.referrer or url_for('profile', username=username))

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
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)