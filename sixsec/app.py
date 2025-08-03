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
app.config['SECRET_KEY'] = 'the-final-complete-polished-key-for-sixsec-v6-pfp-sound'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

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
    'settings': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06-.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>',
    'back_arrow': '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>',
    'stop_square': '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>',
    'redo': '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>',
    'reply': '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>',
    'logout': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>',
    'volume_on': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>',
    'volume_off': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>'
}
app.jinja_env.globals.update(ICONS=ICONS)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        .action-button { background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer; padding: 4px; font-size: 14px; }
        .action-button.liked { color: var(--red-color); }
        .action-button.liked svg { fill: var(--red-color); stroke: var(--red-color); }
        .action-button.reposted { color: var(--accent-color); }
        .action-button.reposted svg { stroke: var(--accent-color); }
        
        .comment-thread {
            position: relative;
            padding-left: 20px;
            margin-left: 20px;
            margin-top: 10px;
        }
        .comment-thread::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 2px;
            background-color: var(--border-color);
        }
        .view-replies-btn {
            font-size: 14px;
            color: var(--accent-color);
            background: none;
            border: none;
            cursor: pointer;
            padding: 4px 0;
            margin-top: 8px;
        }
        
        {% block style_override %}{% endblock %}
    </style>
</head>
<body {% if (request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs') %}style="overflow: hidden;"{% endif %}>
    
    {% if not ((request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs')) %}
    <header class="top-bar">
        <h1 class="logo">{% block header_title %}Home{% endblock %}</h1>
        {% if request.endpoint == 'profile' and current_user == user %}
        <a href="{{ url_for('edit_profile') }}">{{ ICONS.settings|safe }}</a>
        {% endif %}
    </header>
    {% endif %}
    
    <main {% if not ((request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs')) %}class="container"{% endif %}>
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

    {% if current_user.is_authenticated and not ((request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs')) %}
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
            <input type="hidden" id="comment-parent-id">
            <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
          </form>
        </div>
      </div>
    </div>
    
    <script>
        const ICONS = {{ ICONS|tojson|safe }};
    </script>
    <script>
    const commentModal = document.getElementById('commentModal');
    
    function buildCommentNode(comment) {
        const container = document.createElement('div');
        container.className = 'comment-container';
        container.dataset.commentId = comment.id;
        container.style.marginTop = '16px';

        const likeIcon = ICONS.like.replace('width="24"','width="18"').replace('height="24"','height="18"');
        const repostIcon = ICONS.repost.replace('width="24"','width="18"').replace('height="24"','height="18"');

        let repliesButton = '';
        if (comment.replies_count > 0) {
            repliesButton = `<button class="view-replies-btn" onclick="toggleReplies(this, ${comment.id})">View ${comment.replies_count} replies</button>`;
        }
        
        let pfpElement = '';
        if (comment.user.pfp_filename) {
            pfpElement = `<img src="/static/uploads/${comment.user.pfp_filename}" style="width:40px; height:40px; border-radius:50%; object-fit:cover;">`;
        } else {
            pfpElement = `<div style="width:40px; height:40px; border-radius:50%; flex-shrink:0; background:${comment.user.pfp_gradient}; display:flex; align-items:center; justify-content:center; font-weight:bold;">${comment.user.initial}</div>`;
        }

        container.innerHTML = `
            <div style="display: flex; gap: 12px;">
                <div style="flex-shrink:0;">${pfpElement}</div>
                <div style="flex-grow:1">
                    <div><strong style="color:var(--text-color);">${comment.user.username}</strong> <span style="color:var(--text-muted);">${comment.timestamp}</span></div>
                    <div style="color:var(--text-color); margin: 4px 0;">${comment.text}</div>
                    <div class="comment-actions" style="display: flex; gap: 12px; align-items: center; margin-top: 8px;">
                        <button onclick="handleLikeComment(this, ${comment.id})" class="action-button ${comment.is_liked_by_user ? 'liked' : ''}">${likeIcon}<span>${comment.like_count}</span></button>
                        <button onclick="prepareReply(${comment.id}, '${comment.user.username}')" class="action-button">${ICONS.reply}<span>Reply</span></button>
                        <button onclick="handleCommentRepost(this, ${comment.id})" class="action-button">${repostIcon}<span>Repost</span></button>
                    </div>
                    ${repliesButton}
                </div>
            </div>
            <div class="replies-wrapper" style="display: none;"></div>
        `;
        return container;
    }
    
    function appendComments(container, comments) {
        comments.forEach(c => {
            const node = buildCommentNode(c);
            container.appendChild(node);
            if (c.replies && c.replies.length > 0) {
                const repliesWrapper = node.querySelector('.replies-wrapper');
                repliesWrapper.classList.add('comment-thread');
                appendComments(repliesWrapper, c.replies);
            }
        });
    }

    async function toggleReplies(button, commentId) {
        const commentNode = button.closest('.comment-container');
        const repliesWrapper = commentNode.querySelector('.replies-wrapper');

        if (repliesWrapper.style.display === 'none') {
            if (!repliesWrapper.hasChildNodes()) { // Fetch only if empty
                repliesWrapper.innerHTML = '<p style="color:var(--text-muted); padding-left:20px;">Loading replies...</p>';
                const response = await fetch(`/comment/${commentId}/replies`);
                const replies = await response.json();
                repliesWrapper.innerHTML = '';
                if(replies.length > 0) {
                    repliesWrapper.classList.add('comment-thread');
                    appendComments(repliesWrapper, replies);
                } else {
                    repliesWrapper.innerHTML = '<p style="color:var(--text-muted); padding-left:20px;">No replies found.</p>';
                }
            }
            repliesWrapper.style.display = 'block';
            button.textContent = 'Hide replies';
        } else {
            repliesWrapper.style.display = 'none';
            button.textContent = button.textContent.replace('Hide', 'View');
        }
    }

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
            appendComments(list, comments);
        }
    }

    function closeCommentModal() {
        commentModal.style.display = 'none';
        const isSixsView = document.querySelector('#sixs-feed-container');
        if (!isSixsView) document.body.style.overflow = 'auto';
        prepareReply(null, null);
    }
    
    function prepareReply(parentId, username) {
        const textInput = document.getElementById('comment-text-input');
        const parentIdInput = document.getElementById('comment-parent-id');
        if (parentId) {
            parentIdInput.value = parentId;
            textInput.placeholder = `Replying to @${username}...`;
            textInput.focus();
        } else {
            parentIdInput.value = '';
            textInput.placeholder = 'Add a comment...';
        }
    }

    document.getElementById('comment-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const postId = document.getElementById('comment-post-id').value;
        const parentId = document.getElementById('comment-parent-id').value;
        const text = document.getElementById('comment-text-input').value;
        if (!text.trim()) return;

        const response = await fetch(`/post/${postId}/comment`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, parent_id: parentId || null })
        });

        if (response.ok) {
            document.getElementById('comment-text-input').value = '';
            prepareReply(null, null);
            openCommentModal(postId);
            const countEl = document.querySelector(`#comment-count-${postId}`);
            if(countEl) countEl.innerText = parseInt(countEl.innerText) + 1;
        }
    });

    window.onclick = (event) => { if (event.target == commentModal) closeCommentModal(); };
    
    async function handleLike(button, postId) {
        const response = await fetch(`/like/post/${postId}`, { method: 'POST' });
        const data = await response.json();
        button.querySelector('span').innerText = data.likes;
        button.classList.toggle('liked', data.liked);
    }

    async function handleLikeComment(button, commentId) {
        const response = await fetch(`/like/comment/${commentId}`, { method: 'POST' });
        const data = await response.json();
        button.querySelector('span').innerText = data.likes;
        button.classList.toggle('liked', data.liked);
    }

    async function handleRepost(button, postId) {
        const caption = prompt("Add an optional caption:", "");
        if (caption === null) return; 

        const response = await fetch(`/repost/post/${postId}`, { 
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caption: caption })
        });
        const data = await response.json();
        if(data.success) {
            button.classList.toggle('reposted', data.reposted);
            flash(data.message, 'success');
        } else {
            flash(data.message, 'error');
        }
    }
    
    async function handleCommentRepost(button, commentId) {
        const caption = prompt("Add an optional caption:", "");
        if (caption === null) return;

        const response = await fetch(`/repost/comment/${commentId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ caption: caption })
        });
        const data = await response.json();
        if(data.success) {
            flash(data.message, 'success');
        } else {
            flash(data.message, 'error');
        }
    }

    function flash(message, category = 'info') {
        const flashDiv = document.createElement('div');
        flashDiv.style = `position:fixed; top:60px; left:50%; transform:translateX(-50%); z-index: 9999; max-width: 90%; padding: 12px 16px; border-radius: 8px; background-color: ${category === 'error' ? 'var(--red-color)' : 'var(--accent-color)'}; color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3); text-align: center;`;
        flashDiv.innerText = message;
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
        position: fixed; top: 0; left: 0; z-index: 10;
    }
    .six-video-slide {
        height: 100dvh; width: 100vw; scroll-snap-align: start;
        position: relative; display: flex; justify-content: center; align-items: center;
    }
    .six-video-wrapper {
        position: relative;
        width: min(100vw, 100dvh);
        height: min(100vw, 100dvh);
        clip-path: circle(50% at 50% 50%);
    }
    .six-video { width: 100%; height: 100%; object-fit: cover; }
    .six-ui-overlay {
        position: absolute; bottom: 0; left: 0; right: 0; top: 0;
        color: white; display: flex; justify-content: space-between; align-items: flex-end;
        padding: 16px; padding-bottom: 53px; pointer-events: none;
        background: linear-gradient(to top, rgba(0,0,0,0.4), transparent 40%), linear-gradient(to bottom, rgba(0,0,0,0.3), transparent 20%);
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
    #volume-toggle {
        position: absolute; top: 20px; right: 20px; z-index: 100;
        background: rgba(0,0,0,0.3); border-radius: 50%; padding: 8px;
        cursor: pointer; pointer-events: auto; border: none; color: white;
        display: none; /* Initially hidden */
    }
    #unmute-prompt {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
        background: rgba(0,0,0,0.5); padding: 10px 20px; border-radius: 20px;
        font-weight: bold; pointer-events: none; z-index: 100;
        display: none; /* Initially hidden */
    }
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
            <div id="unmute-prompt">Tap to unmute</div>
            <button id="volume-toggle">{{ ICONS.volume_off|safe }}</button>
            {% for post in posts %}
            <section class="six-video-slide" data-post-id="{{ post.id }}">
                <div class="six-video-wrapper">
                    <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop preload="auto" playsinline muted></video>
                </div>
                <div class="six-ui-overlay">
                    <a href="{{ url_for('home', feed_type='text') }}" style="position: absolute; top: 20px; left: 20px; z-index: 100; pointer-events: auto; color: white; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5));">
                        {{ ICONS.back_arrow|safe }}
                    </a>
                    <div class="six-info">
                        <a href="{{ url_for('profile', username=post.author.username) }}" style="color:white;"><strong class="username">@{{ post.author.username }}</strong></a>
                        <p>{{ post.text_content }}</p>
                    </div>
                    <div class="six-actions">
                        <button onclick="handleLike(this, {{ post.id }})" class="action-button {{ 'liked' if post.liked_by_current_user else '' }}">
                            {{ ICONS.like|safe }}
                            <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                        </button>
                        <button onclick="openCommentModal({{ post.id }})">{{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span></button>
                        <button onclick="handleRepost(this, {{ post.id }})" class="action-button {{ 'reposted' if post.reposted_by_current_user else '' }}">{{ ICONS.repost|safe }}</button>
                    </div>
                </div>
            </section>
            {% else %}
            <section class="six-video-slide" style="flex-direction:column; text-align:center; color:white;">
                <a href="{{ url_for('home', feed_type='text') }}" style="position: absolute; top: 20px; left: 20px; z-index: 100; pointer-events: auto; color: white;">
                    {{ ICONS.back_arrow|safe }}
                </a>
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
    const container = document.getElementById('sixs-feed-container');
    const videos = container.querySelectorAll('.six-video');
    const volumeToggle = document.getElementById('volume-toggle');
    const unmutePrompt = document.getElementById('unmute-prompt');

    let isSoundOn = false;
    let hasInteracted = false;

    function setMutedState(isMuted) {
        isSoundOn = !isMuted;
        videos.forEach(v => v.muted = isMuted);
        volumeToggle.innerHTML = isMuted ? ICONS.volume_off : ICONS.volume_on;
        const currentVideo = document.querySelector('.six-video-slide[style*="visible"] video, .six-video-slide.is-visible video');
        if (currentVideo) {
            currentVideo.muted = isMuted;
        }
    }

    volumeToggle.addEventListener('click', () => setMutedState(isSoundOn));
    
    container.addEventListener('click', () => {
        if (!hasInteracted) {
            hasInteracted = true;
            unmutePrompt.style.display = 'none';
            volumeToggle.style.display = 'block';
            setMutedState(false);
        }
    }, { once: true });


    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target.querySelector('video');
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                video.muted = !isSoundOn;
                video.play().catch(e => {
                    console.log("Autoplay was prevented. A user gesture is required.");
                    if (!hasInteracted) unmutePrompt.style.display = 'block';
                });
            } else { 
                entry.target.classList.remove('is-visible');
                video.pause(); 
                video.currentTime = 0;
            }
        });
    }, { threshold: 0.5 });

    document.querySelectorAll('.six-video-slide').forEach(slide => {
      observer.observe(slide);
    });
</script>
{% endif %}
{% endblock %}
""",

"post_card_text.html": """
<div class="post-card" style="border-bottom: 1px solid var(--border-color); padding: 12px 16px; display:flex; gap:12px;">
    <div style="width:40px; height:40px; flex-shrink:0;">
        {% if post.author.pfp_filename %}
            <img src="{{ url_for('static', filename='uploads/' + post.author.pfp_filename) }}" alt="{{ post.author.username }}'s profile picture" style="width:40px; height:40px; border-radius:50%; object-fit: cover;">
        {% else %}
            <div style="width:40px; height:40px; border-radius:50%; background:{{ post.author.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">
                {{ post.author.username[0]|upper }}
            </div>
        {% endif %}
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
            <button onclick="openCommentModal({{ post.id }})" class="action-button">
                {{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span>
            </button>
            <button onclick="handleRepost(this, {{ post.id }})" class="action-button {{ 'reposted' if post.reposted_by_current_user else '' }}">
                {{ ICONS.repost|safe }} <span>{{ post.reposts.count() }}</span>
            </button>
            <button onclick="handleLike(this, {{ post.id }})" class="action-button {{ 'liked' if post.liked_by_current_user else '' }}">
                {{ ICONS.like|safe }} <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
            </button>
        </div>
    </div>
</div>
""",

"comment_card.html": """
<div class="comment-card" style="border: 1px solid var(--border-color); border-radius: 16px; padding: 12px; margin-top: 8px;">
    <div style="display:flex; gap:12px;">
        <div style="width:30px; height:30px; flex-shrink:0;">
            {% if comment.user.pfp_filename %}
                <img src="{{ url_for('static', filename='uploads/' + comment.user.pfp_filename) }}" alt="{{ comment.user.username }}'s profile picture" style="width:30px; height:30px; border-radius:50%; object-fit: cover;">
            {% else %}
                <div style="width:30px; height:30px; border-radius:50%; background:{{ comment.user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size: 14px;">
                    {{ comment.user.username[0]|upper }}
                </div>
            {% endif %}
        </div>
        <div style="flex-grow:1;">
            <div>
                <a href="{{ url_for('profile', username=comment.user.username) }}" style="color:var(--text-color); font-weight:bold;">{{ comment.user.username }}</a>
                <span style="color:var(--text-muted); font-size: 0.9em;">· {{ comment.timestamp.strftime('%b %d') }}</span>
            </div>
            <p style="margin: 4px 0 0 0; font-size: 0.95em;">{{ comment.text }}</p>
        </div>
    </div>
</div>
""",

"create_post.html": """
{% extends "layout.html" %}
{% block header_title %}Create{% endblock %}
{% block style_override %}
    #record-button {
        width: 80px; height: 80px; border-radius: 50%;
        transition: all 0.2s ease-in-out;
        display: flex; align-items: center; justify-content: center;
        padding: 0;
        margin-left: auto;
        margin-right: auto;
    }
    #record-button.recording {
        background-color: #dc2626;
    }
    #record-button svg {
        color: white;
    }
{% endblock %}
{% block content %}
    <div style="padding:16px; text-align: center;">
        <div id="permission-prompt">
            <p id="permission-status" style="color:var(--text-muted); min-height: 20px; margin: 20px 0;">Tap to enable your camera and microphone to record a Six.</p>
            <button id="enable-camera-btn" class="btn">Enable Camera</button>
        </div>

        <div id="six-creator" style="display: none;">
            <p id="recorder-status" style="color:var(--text-muted); min-height: 20px;">Tap the button to record</p>
            <div style="width:100%; max-width: 400px; margin: 15px auto; aspect-ratio: 1/1; border-radius:50%; overflow:hidden; background:#111; border: 2px solid var(--border-color);">
                <video id="video-preview" autoplay muted playsinline style="width:100%; height:100%; object-fit:cover;"></video>
            </div>
            <button id="record-button" class="btn btn-danger" disabled></button>
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
    let mediaRecorder; 
    let recordedBlobs; 
    let stream;
    const recordButton = document.getElementById('record-button');
    const preview = document.getElementById('video-preview');
    const sixForm = document.getElementById('six-form-element');
    const recorderStatus = document.getElementById('recorder-status');
    const sixCreator = document.getElementById('six-creator');
    const permissionPrompt = document.getElementById('permission-prompt');
    const permissionStatus = document.getElementById('permission-status');
    const enableCameraBtn = document.getElementById('enable-camera-btn');

    async function initCamera() {
        try {
            const constraints = { audio: true, video: { width: 480, height: 480, facingMode: "user" } };
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            
            permissionPrompt.style.display = 'none';
            sixCreator.style.display = 'block';

            preview.srcObject = stream;
            resetRecorder();
            recordButton.disabled = false;
        } catch (e) {
            console.error(e);
            permissionStatus.textContent = "Camera/Mic permission denied. Please enable it in your browser settings and refresh the page.";
            enableCameraBtn.disabled = true;
        }
    }
    
    enableCameraBtn.addEventListener('click', initCamera);

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
        
        recordButton.innerHTML = `{{ ICONS.stop_square|safe }}`;
        recordButton.classList.add('recording');
        recorderStatus.textContent = 'Recording... (max 6 seconds)';
        
        setTimeout(() => { 
            if (mediaRecorder && mediaRecorder.state === "recording") {
                mediaRecorder.stop(); 
            }
        }, 6000);
    }
    
    function handleStop() {
        recordButton.classList.remove('recording');
        recordButton.classList.add('previewing');
        recordButton.innerHTML = `{{ ICONS.redo|safe }}`;
        
        recorderStatus.textContent = 'Previewing... Tap icon to re-record.';
        
        const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
        preview.srcObject = null;
        preview.src = window.URL.createObjectURL(superBuffer);
        preview.muted = false;
        preview.controls = true;
        
        sixForm.style.display = 'block';
    }

    function resetRecorder() {
        sixForm.style.display = 'none';
        recordButton.classList.remove('previewing');
        recordButton.classList.remove('recording');
        recordButton.innerHTML = '<div style="width: 32px; height: 32px; border-radius: 50%; background-color: white;"></div>';
        
        if (stream) { preview.srcObject = stream; }
        
        preview.controls = false;
        preview.muted = true;
        
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
        .catch(error => {
            console.error('Error:', error);
            submitBtn.disabled = false;
            submitBtn.textContent = "Post Six";
            recorderStatus.textContent = "Upload failed. Please try again.";
        });
    });
    resetRecorder();
</script>
{% endblock %}
""",

"edit_profile.html": """
{% extends "layout.html" %}
{% block header_title %}Settings{% endblock %}
{% block content %}
<div style="padding:16px;">
    <h4>Edit Profile</h4>
    <form method="POST" action="{{ url_for('edit_profile') }}" enctype="multipart/form-data">
        <div class="form-group" style="text-align: center;">
            <label for="pfp" style="cursor: pointer;">
                {% if current_user.pfp_filename %}
                    <img src="{{ url_for('static', filename='uploads/' + current_user.pfp_filename) }}" alt="Your profile picture" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid var(--border-color); margin-bottom: 8px;">
                {% else %}
                    <div style="width: 100px; height: 100px; border-radius:50%; background: {{ current_user.pfp_gradient }}; display:inline-flex; align-items:center; justify-content:center; font-size: 3rem; font-weight:bold; margin-bottom: 8px;">
                        {{ current_user.username[0]|upper }}
                    </div>
                {% endif %}
                <div style="color: var(--accent-color);">Change Profile Picture</div>
            </label>
            <input type="file" id="pfp" name="pfp" accept="image/png, image/jpeg, image/gif" style="display: none;">
        </div>

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
    <a href="{{ url_for('logout') }}" class="btn btn-outline" style="width: 100%; box-sizing: border-box; text-align: center; margin-bottom: 24px;">Log Out</a>
    
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

{% block style_override %}
    {% if active_tab == 'sixs' %}
    #sixs-feed-container {
        height: 100dvh; width: 100vw; overflow-y: scroll;
        scroll-snap-type: y mandatory; background-color: #000;
        position: fixed; top: 0; left: 0; z-index: 10;
    }
    .six-video-slide {
        height: 100dvh; width: 100vw; scroll-snap-align: start;
        position: relative; display: flex; justify-content: center; align-items: center;
    }
    .six-video-wrapper {
        position: relative;
        width: min(100vw, 100dvh);
        height: min(100vw, 100dvh);
        clip-path: circle(50% at 50% 50%);
    }
    .six-video { width: 100%; height: 100%; object-fit: cover; }
    .six-ui-overlay {
        position: absolute; bottom: 0; left: 0; right: 0; top: 0;
        color: white; display: flex; justify-content: space-between; align-items: flex-end;
        padding: 16px; padding-bottom: 53px; pointer-events: none;
        background: linear-gradient(to top, rgba(0,0,0,0.4), transparent 40%), linear-gradient(to bottom, rgba(0,0,0,0.3), transparent 20%);
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
    {% endif %}
{% endblock %}

{% block content %}
    {% if active_tab != 'sixs' %}
    <div style="padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div style="width: 80px; height: 80px; flex-shrink: 0;">
                {% if user.pfp_filename %}
                    <img src="{{ url_for('static', filename='uploads/' + user.pfp_filename) }}" alt="{{ user.username }}'s profile picture" style="width:80px; height:80px; border-radius:50%; object-fit: cover;">
                {% else %}
                    <div style="width: 80px; height: 80px; border-radius:50%; background: {{ user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-size: 2.5rem; font-weight:bold;">
                        {{ user.username[0]|upper }}
                    </div>
                {% endif %}
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
            <span><strong style="color:var(--text-color)">{{ user.followers.count() }}</strong> Followers</span>
            <span><strong style="color:var(--text-color)">{{ user.followed.count() }}</strong> Following</span>
        </div>
    </div>
    {% endif %}

    <div class="feed-nav" style="display: flex; border-bottom: 1px solid var(--border-color); {% if active_tab == 'sixs' %} position: fixed; top:0; left:0; right:0; z-index:100; background:rgba(0,0,0,0.65); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); {% endif %}">
        {% set tabs = [('Posts', url_for('profile', username=user.username, tab='posts')), ('Sixs', url_for('profile', username=user.username, tab='sixs')), ('Reposts', url_for('profile', username=user.username, tab='reposts'))] %}
        {% for name, url in tabs %}
        <a href="{{ url }}" style="flex:1; text-align:center; padding: 15px; color: {% if active_tab == name.lower() %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">{{ name }} {% if active_tab == name.lower() %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
        {% endfor %}
    </div>

    {% if active_tab == 'sixs' %}
        <div id="sixs-feed-container">
            {% for post in posts %}
            <section class="six-video-slide" data-post-id="{{ post.id }}">
                <div class="six-video-wrapper">
                    <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop preload="auto" playsinline muted></video>
                </div>
                <div class="six-ui-overlay">
                    <a href="{{ url_for('profile', username=user.username, tab='posts') }}" style="position: absolute; top: 73px; left: 20px; z-index: 100; pointer-events: auto; color: white; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5));">
                        {{ ICONS.back_arrow|safe }}
                    </a>
                    <div class="six-info">
                        <a href="{{ url_for('profile', username=post.author.username) }}" style="color:white;"><strong class="username">@{{ post.author.username }}</strong></a>
                        <p>{{ post.text_content }}</p>
                    </div>
                    <div class="six-actions">
                        <button onclick="handleLike(this, {{ post.id }})" class="action-button {{ 'liked' if post.liked_by_current_user else '' }}">
                            {{ ICONS.like|safe }}
                            <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
                        </button>
                        <button onclick="openCommentModal({{ post.id }})">{{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span></button>
                        <button onclick="handleRepost(this, {{ post.id }})" class="action-button {{ 'reposted' if post.reposted_by_current_user else '' }}">{{ ICONS.repost|safe }}</button>
                    </div>
                </div>
            </section>
            {% else %}
            <section class="six-video-slide" style="flex-direction:column; text-align:center; color:white;">
                <a href="{{ url_for('profile', username=user.username, tab='posts') }}" style="position: absolute; top: 73px; left: 20px; z-index: 100; pointer-events: auto; color: white; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5));">
                        {{ ICONS.back_arrow|safe }}
                </a>
                <div style="padding-top: 53px;">
                    <h4>No Sixs yet.</h4>
                    <p style="color:#aaa;">This user hasn't posted any Sixs.</p>
                </div>
            </section>
            {% endfor %}
        </div>
    {% elif active_tab == 'reposts' %}
        {% for repost in reposts %}
            <div style="border-bottom: 1px solid var(--border-color); padding: 12px 16px;">
                <div style="color: var(--text-muted); margin-bottom: 8px; font-size: 0.9em; display:flex; align-items:center; gap: 8px;">
                    {{ ICONS.repost|safe }}
                    <a href="{{ url_for('profile', username=repost.reposter.username) }}">{{ repost.reposter.username }}</a> reposted
                </div>
                 {% if repost.caption %}
                    <p style="margin: 4px 0 12px 0; padding-left: 20px; border-left: 2px solid var(--border-color);">{{ repost.caption }}</p>
                {% endif %}
                
                {% if repost.original_post %}
                    {% with post=repost.original_post %}
                        {% include 'post_card_text.html' %}
                    {% endwith %}
                {% elif repost.original_comment %}
                    {% with comment=repost.original_comment %}
                        {% include 'comment_card.html' %}
                    {% endwith %}
                {% endif %}
            </div>
        {% else %}
            <p style="text-align:center; color:var(--text-muted); padding:40px;">No items reposted yet.</p>
        {% endfor %}
    {% else %}
        {% for post in posts %}
            {% include 'post_card_text.html' %}
        {% else %}
            <p style="text-align:center; color:var(--text-muted); padding:40px;">No posts in this section.</p>
        {% endfor %}
    {% endif %}
{% endblock %}

{% block scripts %}
{% if active_tab == 'sixs' %}
<script>
    const container = document.getElementById('sixs-feed-container');
    const videos = container.querySelectorAll('.six-video');
    
    let isSoundOn = false;
    let hasInteracted = false;
    
    function createVolumeControls() {
        const controls = document.createElement('div');
        controls.innerHTML = `
            <div id="unmute-prompt">Tap to unmute</div>
            <button id="volume-toggle">${ICONS.volume_off}</button>
        `;
        container.prepend(controls);

        const volumeToggle = document.getElementById('volume-toggle');
        const unmutePrompt = document.getElementById('unmute-prompt');

        function setMutedState(isMuted) {
            isSoundOn = !isMuted;
            videos.forEach(v => v.muted = isMuted);
            volumeToggle.innerHTML = isMuted ? ICONS.volume_off : ICONS.volume_on;
            const currentSlide = document.querySelector('.six-video-slide.is-visible');
            if (currentSlide) {
                const currentVideo = currentSlide.querySelector('video');
                if (currentVideo) currentVideo.muted = isMuted;
            }
        }

        volumeToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            setMutedState(isSoundOn);
        });
        
        container.addEventListener('click', () => {
            if (!hasInteracted) {
                hasInteracted = true;
                unmutePrompt.style.display = 'none';
                volumeToggle.style.display = 'block';
                setMutedState(false);
            }
        }, { once: true });
    }

    if(videos.length > 0) {
        createVolumeControls();
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target.querySelector('video');
            if (!video) return;
            
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                video.muted = !isSoundOn;
                video.play().catch(e => {
                    if (!hasInteracted) {
                        document.getElementById('unmute-prompt').style.display = 'block';
                    }
                });
            } else { 
                entry.target.classList.remove('is-visible');
                video.pause(); 
                video.currentTime = 0;
            }
        });
    }, { threshold: 0.5 });

    document.querySelectorAll('.six-video-slide').forEach(slide => {
      observer.observe(slide);
    });
</script>
{% endif %}
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
        <div style="width: 40px; height: 40px; flex-shrink:0;">
            {% if user.pfp_filename %}
                <img src="{{ url_for('static', filename='uploads/' + user.pfp_filename) }}" alt="{{ user.username }}'s profile picture" style="width:40px; height:40px; border-radius:50%; object-fit: cover;">
            {% else %}
                <div style="width: 40px; height: 40px; border-radius:50%; background: {{ user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">{{ user.username[0]|upper }}</div>
            {% endif %}
        </div>
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
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)
post_likes = db.Table('post_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)
comment_likes = db.Table('comment_likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('comment_id', db.Integer, db.ForeignKey('comment.id'))
)

class Repost(db.Model):
    __tablename__ = 'repost'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    caption = db.Column(db.String(150), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

class CommentRepost(db.Model):
    __tablename__ = 'comment_repost'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)
    caption = db.Column(db.String(150), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(150))
    pfp_filename = db.Column(db.String(120), nullable=True)
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Post.user_id')
    reposts = db.relationship('Repost', backref='reposter', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Repost.user_id')
    comment_reposts = db.relationship('CommentRepost', backref='reposter', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='CommentRepost.user_id')
    liked_posts = db.relationship('Post', secondary=post_likes, backref=db.backref('liked_by', lazy='dynamic'), lazy='dynamic')
    liked_comments = db.relationship('Comment', secondary=comment_likes, backref=db.backref('liked_by', lazy='dynamic'), lazy='dynamic')
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
    image_filename = db.Column(db.String(120), nullable=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Comment.post_id')
    reposts = db.relationship('Repost', backref='original_post', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Repost.post_id')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user = db.relationship('User')
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic', cascade="all, delete-orphan")
    reposts = db.relationship('CommentRepost', backref='original_comment', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='CommentRepost.comment_id')

# --- Helper function to add user interaction flags to posts ---
def add_user_flags_to_posts(posts):
    if posts and current_user.is_authenticated:
        post_ids = [p.id for p in posts]
        liked_post_ids = {p.id for p in current_user.liked_posts.filter(Post.id.in_(post_ids)).all()}
        reposted_post_ids = {r.post_id for r in current_user.reposts.filter(Repost.post_id.in_(post_ids)).all()}
        for p in posts:
            p.liked_by_current_user = p.id in liked_post_ids
            p.reposted_by_current_user = p.id in reposted_post_ids
    return posts

def format_comment(comment):
    return {
        'id': comment.id,
        'text': comment.text,
        'timestamp': comment.timestamp.strftime('%b %d'),
        'user': {
            'username': comment.user.username,
            'pfp_gradient': comment.user.pfp_gradient,
            'initial': comment.user.username[0].upper(),
            'pfp_filename': comment.user.pfp_filename
        },
        'like_count': comment.liked_by.count(),
        'is_liked_by_user': current_user in comment.liked_by,
        'replies_count': comment.replies.count()
    }

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
    else:
        posts = query.filter_by(post_type='six').order_by(Post.timestamp.desc()).all()

    posts = add_user_flags_to_posts(posts)
    return render_template('home.html', posts=posts, feed_type=feed_type)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    active_tab = request.args.get('tab', 'posts')
    posts = []
    reposts_data = []

    if active_tab == 'reposts':
        post_reposts = user.reposts.all()
        comment_reposts = user.comment_reposts.all()
        reposts_data = sorted(post_reposts + comment_reposts, key=lambda r: r.timestamp, reverse=True)
        if reposts_data:
            original_posts = [r.original_post for r in post_reposts]
            add_user_flags_to_posts(original_posts)
    elif active_tab == 'sixs':
        posts = user.posts.filter_by(post_type='six').order_by(Post.timestamp.desc()).all()
    else: # Default to 'posts'
        active_tab = 'posts'
        posts = user.posts.filter_by(post_type='text').order_by(Post.timestamp.desc()).all()

    if posts:
        posts = add_user_flags_to_posts(posts)
        
    return render_template('profile.html', user=user, posts=posts, reposts=reposts_data, active_tab=active_tab)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form.get('post_type')
        if post_type == 'six':
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
    post = Post.query.get_or_404(post_id)
    top_level_comments = post.comments.filter_by(parent_id=None).order_by(Comment.timestamp.asc()).all()
    return jsonify([format_comment(c) for c in top_level_comments])

@app.route('/comment/<int:comment_id>/replies')
@login_required
def get_replies(comment_id):
    parent_comment = Comment.query.get_or_404(comment_id)
    replies = parent_comment.replies.order_by(Comment.timestamp.asc()).all()
    return jsonify([format_comment(r) for r in replies])

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    data = request.get_json()
    text = data.get('text', '').strip()
    parent_id = data.get('parent_id') if data.get('parent_id') else None
    if not text: return jsonify({'error': 'Comment text is required'}), 400
    
    parent_comment = None
    if parent_id:
        parent_comment = Comment.query.get(parent_id)
        if not parent_comment or parent_comment.post_id != post_id:
            return jsonify({'error': 'Invalid parent comment'}), 400
            
    comment = Comment(text=text, user_id=current_user.id, post_id=post_id, parent_id=parent_id)
    db.session.add(comment); db.session.commit()
    return jsonify({'success': True}), 201

@app.route('/like/post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    liked = current_user in post.liked_by
    if liked:
        post.liked_by.remove(current_user)
    else:
        post.liked_by.append(current_user)
    db.session.commit()
    return jsonify({'liked': not liked, 'likes': post.liked_by.count()})

@app.route('/like/comment/<int:comment_id>', methods=['POST'])
@login_required
def like_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    liked = current_user in comment.liked_by
    if liked:
        comment.liked_by.remove(current_user)
    else:
        comment.liked_by.append(current_user)
    db.session.commit()
    return jsonify({'liked': not liked, 'likes': comment.liked_by.count()})

@app.route('/repost/post/<int:post_id>', methods=['POST'])
@login_required
def repost_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author == current_user: return jsonify({'success': False, 'message': "You can't repost your own post."})
    
    caption = request.json.get('caption', '').strip() or None
    existing_repost = Repost.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    
    if existing_repost:
        db.session.delete(existing_repost)
        message = "Repost removed."
        reposted = False
    else:
        new_repost = Repost(user_id=current_user.id, post_id=post.id, caption=caption)
        db.session.add(new_repost)
        reposted = True
        message = "Post reposted!"

    db.session.commit()
    return jsonify({'success': True, 'reposted': reposted, 'message': message})

@app.route('/repost/comment/<int:comment_id>', methods=['POST'])
@login_required
def repost_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user == current_user:
        return jsonify({'success': False, 'message': "You can't repost your own comment."})

    caption = request.json.get('caption', '').strip() or None
    existing_repost = CommentRepost.query.filter_by(user_id=current_user.id, comment_id=comment.id).first()

    if existing_repost:
        db.session.delete(existing_repost)
        message = "Comment repost removed."
        reposted = False
    else:
        new_repost = CommentRepost(user_id=current_user.id, comment_id=comment.id, caption=caption)
        db.session.add(new_repost)
        message = "Comment reposted!"
        reposted = True
        
    db.session.commit()
    return jsonify({'success': True, 'reposted': reposted, 'message': message})

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        # Handle PFP Upload
        pfp_file = request.files.get('pfp')
        if pfp_file and pfp_file.filename != '' and allowed_file(pfp_file.filename):
            if current_user.pfp_filename: # Delete old PFP
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.pfp_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            ext = pfp_file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"pfp_{current_user.id}_{int(datetime.datetime.now().timestamp())}.{ext}")
            pfp_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.pfp_filename = filename

        # Handle other profile info
        new_username = request.form.get('username', '').strip()
        new_bio = request.form.get('bio', current_user.bio).strip()
        if new_username and new_username != current_user.username:
            existing_user = User.query.filter(User.username.ilike(new_username), User.id != current_user.id).first()
            if existing_user:
                flash('Username is already taken.', 'error')
                return redirect(url_for('edit_profile'))
            current_user.username = new_username
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
    logout_user()
    user = User.query.get(user_id)
    db.session.delete(user); db.session.commit()
    flash('Your account has been permanently deleted.', 'success')
    return redirect(url_for('login'))

@app.route('/discover')
@login_required
def discover():
    query = request.args.get('q')
    if query:
        search_term = f"%{query}%"
        users = User.query.filter(User.username.ilike(search_term), User.id != current_user.id).all()
    else:
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
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']): os.makedirs(app.config['UPLOAD_FOLDER'])
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=8000)