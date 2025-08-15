import os
import datetime
import random
import pytz
import shutil
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, not_, text
from sqlalchemy.orm import selectinload
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from jinja2 import BaseLoader, TemplateNotFound
from flask_caching import Cache
from PIL import Image
import ffmpeg

# --- CONFIGURAÇÃO DO APP ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-chave-final-completa-e-polida-para-sixsec-v10-ptbr-final'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['CACHE_TYPE'] = 'FileSystemCache'
app.config['CACHE_DIR'] = os.path.join(basedir, 'cache')
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024 # Increased for larger video files before compression
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'webm'}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
VIDEO_EXTENSIONS = {'mp4', 'mov', 'webm'}


# --- INICIALIZAÇÃO DE EXTENSÕES E HELPERS ---
db = SQLAlchemy(app)
cache = Cache(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

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
    'redo': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>',
    'reply': '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>',
    'logout': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>',
    'volume_on': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>',
    'volume_off': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>',
    'trash': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>',
    'notifications': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>',
    'camera_switch': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 19H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"></path><path d="M13 5h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-5"></path><path d="m18 19-3-3 3-3"></path><path d="m6 5 3 3-3 3"></path></svg>',
    'pause': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"></rect><rect x="14" y="4" width="4" height="16" rx="1"></rect></svg>',
    'record_circle': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"></circle></svg>',
    'check': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>',
    'attach_file': '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
}
app.jinja_env.globals.update(ICONS=ICONS)

@app.template_filter('sao_paulo_time')
def sao_paulo_time_filter(utc_dt):
    if not utc_dt:
        return ""
    sao_paulo_tz = pytz.timezone('America/Sao_Paulo')
    utc_tz = pytz.utc
    # Make the naive datetime object timezone-aware (as UTC)
    aware_utc_dt = utc_tz.localize(utc_dt)
    # Convert to São Paulo timezone
    sao_paulo_dt = aware_utc_dt.astimezone(sao_paulo_tz)
    
    # Format the string
    return sao_paulo_dt.strftime('%d de %b · %H:%M')

def allowed_file(filename, file_type='any'):
    is_allowed = '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    if not is_allowed:
        return False
    if file_type == 'image':
        return filename.rsplit('.', 1)[1].lower() in IMAGE_EXTENSIONS
    if file_type == 'video':
        return filename.rsplit('.', 1)[1].lower() in VIDEO_EXTENSIONS
    return True

def process_image(input_path, output_path, max_width=1080):
    try:
        with Image.open(input_path) as img:
            if img.width > max_width:
                height = int((max_width / img.width) * img.height)
                img = img.resize((max_width, height), Image.Resampling.LANCZOS)
            
            # Convert to RGB if it's RGBA (to save as JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
                
            img.save(output_path, 'jpeg', quality=85, optimize=True)
        return True
    except Exception as e:
        print(f"Error processing image: {e}")
        # Fallback: just copy the file
        shutil.copy(input_path, output_path)
        return False

def process_video(input_path, output_path):
    try:
        (
            ffmpeg
            .input(input_path)
            .output(output_path, vcodec='libx264', crf=28, preset='fast', acodec='aac', strict='experimental', vf='scale=720:-2')
            .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
        )
        return True
    except ffmpeg.Error as e:
        print(f"FFmpeg Error: {e.stderr.decode()}")
        # Fallback: just copy the file
        shutil.copy(input_path, output_path)
        return False

# --- BANCO DE DADOS ---
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
seen_sixs_posts = db.Table('seen_sixs_posts',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True)
)
seen_text_posts = db.Table('seen_text_posts',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True)
)

# --- DICIONÁRIO DE TEMPLATES ---
templates = {
"view_post.html": """
{% extends "layout.html" %}
{% block title %}Publicação de {{ post.author.username }}{% endblock %}

{# We override the header block to provide a clean back-arrow-only header #}
{% block header_title %}
    <a href="{{ request.referrer or url_for('home') }}" style="color: var(--text-color);">{{ ICONS.back_arrow|safe }}</a>
{% endblock %}

{% block content %}
    {# Render the post itself - no extra padding needed now #}
    {% include 'post_card_text.html' %}

    {# Render the comment section #}
    <div style="border-top: 1px solid var(--border-color); padding: 16px;">
        <h4 style="margin-top:0;">Comentários</h4>
        <form id="comment-form-page" style="display: flex; gap: 8px; margin-bottom: 24px;">
            <input type="text" id="comment-text-input-page" class="form-group comment-input-style" placeholder="Adicionar um comentário..." style="margin:0; flex-grow:1;">
            <input type="hidden" id="comment-post-id-page" value="{{ post.id }}">
            <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
        </form>
        <div id="comment-list-page">
            {# Comments will be loaded here by JS #}
            <div class="spinner" style="margin: 40px auto;"></div>
        </div>
    </div>
    <div class="content-spacer"></div>
{% endblock %}
{% block scripts %}
<script>
    // This script block is specifically for view_post.html
    const commentListPage = document.getElementById('comment-list-page');
    const postId = {{ post.id }};

    async function loadCommentsForPage() {
        commentListPage.innerHTML = '<div class="spinner" style="margin: 40px auto;"></div>';
        try {
            const response = await fetch(`/post/${postId}/comments`);
            const comments = await response.json();
            commentListPage.innerHTML = '';

            if (comments.length === 0) {
                commentListPage.innerHTML = '<p style="text-align:center; color: var(--text-muted);">Nenhum comentário ainda.</p>';
            } else {
                appendComments(commentListPage, comments);
            }
        } catch (e) {
            commentListPage.innerHTML = '<p style="text-align:center; color: var(--text-muted);">Falha ao carregar comentários.</p>';
        }
    }

    document.getElementById('comment-form-page').addEventListener('submit', async (e) => {
        e.preventDefault();
        const button = e.target.querySelector('button[type=submit]');
        setButtonLoading(button, true);

        const textInput = document.getElementById('comment-text-input-page');
        const text = textInput.value;
        if (!text.trim()) {
            setButtonLoading(button, false);
            return;
        }

        try {
            const response = await fetch(`/post/${postId}/comment`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, parent_id: null })
            });

            if (response.ok) {
                textInput.value = '';
                loadCommentsForPage(); // Refresh comments list on the page
                const countEl = document.querySelector(`#comment-count-${postId}`);
                if(countEl) countEl.innerText = parseInt(countEl.innerText) + 1;
            }
        } finally {
            setButtonLoading(button, false);
        }
    });

    // Initial load
    document.addEventListener('DOMContentLoaded', loadCommentsForPage);
</script>
{% endblock %}
""",


"layout.html": """
<!doctype html>
<html lang="pt-br">
<head>
    <meta charset="utf-t-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, user-scalable=no">
    <link rel="icon" href="/static/img/icon.png" type="image/png">
    <link rel="apple-touch-icon" href="/static/img/icon.png">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#000000">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black">
    <title>{% block title %}Six{% endblock %}</title>
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
            padding-bottom: 70px; /* Espaço para nav inferior */
            background-color: var(--bg-color); 
            color: var(--text-color); 
            font-size: 15px;
            overscroll-behavior-y: contain;
            opacity: 1;
        }
        /* REMOVED: body.fade-out class is no longer used */
        body.sixs-view, body.creator-view { padding-bottom: 0; background-color: #000; }
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
        .bottom-nav a svg { width: 28px; height: 28px; } /* New: Make icons bigger */
        .bottom-nav a.active svg { stroke-width: 2.5; }
        .bottom-nav a:not(.create-btn):active { transform: scale(0.9); }
        .bottom-nav .create-btn {
             background: var(--accent-color); border-radius: 50%; width: 50px; height: 50px;
             display: flex; align-items: center; justify-content: center;
             transform: translateY(-15px); border: 4px solid var(--bg-color);
             transition: transform 0.2s ease;
        }
        .bottom-nav .create-btn:active { transform: translateY(-15px) scale(0.9); }
        .bottom-nav .create-btn svg { color: white; width: 28px; height: 28px; }
        .btn {
            background-color: var(--text-color); color: var(--bg-color); padding: 8px 16px;
            border-radius: 20px; border: none;
            cursor: pointer; font-weight: bold; font-size: 15px;
            transition: opacity 0.2s ease;
            display: inline-flex; align-items: center; justify-content: center; gap: 6px;
        }
        .btn:hover { opacity: 0.9; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-outline { background: transparent; border: 1px solid var(--text-muted); color: var(--text-color); }
        .btn-danger { background-color: var(--red-color); color: white; }
        .attachment-btn {
            background: none;
            border: none;
            color: var(--accent-color);
            cursor: pointer;
            padding: 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: background-color 0.2s ease;
        }
        .attachment-btn:hover {
            background-color: rgba(29, 155, 240, 0.1);
        }
        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: .5rem; color: var(--text-muted); }
        .form-group input, .form-group textarea {
            width: 100%; padding: 12px; border: 1px solid var(--border-color);
            border-radius: 6px; background: transparent; color: var(--text-color);
            box-sizing: border-box; font-size: 1rem;
            font-family: inherit; /* This is the key change to ensure consistent font */
        }
        /* New style for comment inputs */
        .comment-input-style {
            background-color: var(--primary-color) !important;
            border: 1px solid var(--primary-color) !important;
            border-radius: 20px !important;
            padding: 10px 16px !important;
            color: white;
        }
        .comment-input-style:focus {
            border-color: var(--accent-color) !important;
        }
        .comment-input-style.auto-growing {
            resize: none;
            overflow-y: hidden;
        }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: var(--accent-color); }
        .modal {
            display: none; position: fixed; z-index: 2000; left: 0; top: 0;
            width: 100%; height: 100%;
            background-color: rgba(91, 112, 131, 0.4);
            align-items: flex-end; justify-content: center;
        }
        .modal-content {
            background-color: var(--bg-color); margin: auto auto 0 auto;
            border-radius: 16px 16px 0 0; width: 100%; max-width: 600px;
            max-height: 80vh; display: flex; flex-direction: column;
        }
        .modal-content.opening { animation: slideUp 0.25s ease-out forwards; }
        .modal-content.closing { animation: slideDown 0.25s ease-out forwards; }
        @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
        @keyframes slideDown { from { transform: translateY(0); } to { transform: translateY(100%); } }
        .modal-header { padding: 12px 16px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; }
        .modal-header .close-btn { font-size: 24px; font-weight: bold; cursor: pointer; padding: 0 8px; }
        .modal-body { flex-grow: 1; padding: 16px; overflow-y: auto; }
        .modal-footer { padding: 8px 16px; border-top: 1px solid var(--border-color); }
        .action-button { background:none; border:none; color:var(--text-muted); display:flex; align-items:center; gap:8px; cursor:pointer; padding: 4px; font-size: 14px; }
        .action-button.liked { color: var(--red-color); }
        .action-button.liked svg { fill: var(--red-color); stroke: var(--red-color); }
        .action-button.reposted { color: var(--accent-color); }
        .action-button.reposted svg { stroke: var(--accent-color); }
        .action-button.delete-btn { color: var(--red-color); }
        .action-button.delete-btn:hover { color: #d60a6a; }
        .comment-thread { position: relative; padding-left: 20px; margin-left: 20px; margin-top: 10px; }
        .comment-thread::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 2px; background-color: var(--border-color); }
        .view-replies-btn { font-size: 14px; color: var(--accent-color); background: none; border: none; cursor: pointer; padding: 4px 0; margin-top: 8px; }
        
        .flash-message-container {
            position: fixed; top: 10px; left: 50%; transform: translateX(-50%); 
            z-index: 9999; max-width: 90%; pointer-events: none;
        }
        .flash-message {
            padding: 12px 16px; border-radius: 8px; margin-bottom: 15px;
            color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3); text-align: center;
            animation: fadeInOut 3.0s ease-in-out forwards;
        }
        .flash-message.info { background-color: var(--accent-color); }
        .flash-message.success { background-color: #0f7b4f; }
        .flash-message.error { background-color: var(--red-color); }
        @keyframes fadeInOut {
            0%, 100% { opacity: 0; transform: translateY(-20px); }
            10%, 90% { opacity: 1; transform: translateY(0); }
        }
        
        #page-loader {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background-color: var(--bg-color);
            z-index: 99999;
            display: flex; align-items: center; justify-content: center;
            transition: opacity 0.25s ease;
        }
        .spinner {
            width: 40px; height: 40px;
            border: 4px solid var(--border-color);
            border-top-color: var(--accent-color);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        {% block style_override %}{% endblock %}
    </style>
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', function() {
                navigator.serviceWorker.register('/static/service-worker.js')
                    .then(function(registration) {
                        console.log('Service Worker registered with scope:', registration.scope);
                    })
                    .catch(function(error) {
                        console.log('Service Worker registration failed:', error);
                    });
            });
        }
    </script>
</head>
<body {% if (request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs') %}class="sixs-view" style="overflow: hidden;"
      {% elif request.endpoint == 'create_post' %}class="creator-view" style="overflow: hidden;"
      {% endif %}>

    <div id="page-loader"><div class="spinner"></div></div>
    
    {% if not ((request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs') or request.endpoint == 'create_post') %}
    <header class="top-bar">
        <h1 class="logo">{% block header_title %}<img src="/static/img/six_icon.png" alt="Six" style="width: 24px; height: 24px; vertical-align: middle; margin-right: 8px;">Início{% endblock %}</h1>
        <div>
        {% if request.endpoint == 'profile' and current_user == user %}
            <a href="{{ url_for('edit_profile') }}" style="margin-left: 16px;">{{ ICONS.settings|safe }} <img src="/static/img/six_icon.png" alt="Six" style="width: 18px; height: 18px; vertical-align: middle; margin-left: 8px;"></a>
        {% elif request.endpoint == 'home' %}
            <a href="{{ url_for('discover') }}">{{ ICONS.discover|safe }}</a>
        {% endif %}
        </div>
    </header>
    {% endif %}
    
    <main {% if not ((request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs')) %}class="container"{% endif %}>
        <div class="flash-message-container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="flash-message {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        </div>
        {% block content %}{% endblock %}
    </main>

    {% if current_user.is_authenticated and not ((request.endpoint == 'home' and feed_type == 'sixs') or (request.endpoint == 'profile' and active_tab == 'sixs') or request.endpoint == 'create_post') %}
    <nav class="bottom-nav">
        <a href="{{ url_for('home') }}" class="{{ 'active' if request.endpoint == 'home' else '' }}">{{ ICONS.home|safe }}</a>
        <a href="{{ url_for('create_post') }}" class="create-btn">{{ ICONS.create|safe }}</a>
        <a href="{{ url_for('profile', username=current_user.username) }}" class="{{ 'active' if request.endpoint == 'profile' and user and current_user.username == user.username else '' }}">{{ ICONS.profile|safe }} <img src="/static/img/six_icon.png" alt="Six" style="width: 16px; height: 16px; vertical-align: middle; margin-left: 4px;"></a>
    </nav>
    {% endif %}

    <div id="commentModal" class="modal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="close-btn" onclick="closeCommentModal()">×</span>
          <h4 style="margin:0; padding-left:16px;">Comentários</h4>
        </div>
        <div id="comment-original-post-context" class="modal-body" style="padding-bottom: 0;"></div>
        <div class="modal-body" id="comment-list" style="flex-grow: 1;"><div class="spinner" style="margin: 40px auto;"></div></div>
        <div class="modal-footer">
          <form id="comment-form" style="display: flex; gap: 8px;">
            <input type="text" id="comment-text-input" class="form-group comment-input-style" placeholder="Adicionar um comentário..." style="margin:0; flex-grow:1;">
            <input type="hidden" id="comment-post-id">
            <input type="hidden" id="comment-parent-id">
            <button type="submit" class="btn">{{ ICONS.send|safe }}</button>
          </form>
        </div>
      </div>
    </div>
    
    <script>
        const ICONS = {{ ICONS|tojson|safe }};
        const pageLoader = document.getElementById('page-loader');

        function showLoader() { if(pageLoader) pageLoader.style.display = 'flex'; }
        function hideLoader() { if(pageLoader) pageLoader.style.display = 'none'; }
        
        // --- Page Loader Logic ---
        document.addEventListener('DOMContentLoaded', () => {
            hideLoader();
        });
        
        window.addEventListener('pageshow', (event) => {
            // Hide loader on back/forward navigation
            if (event.persisted) {
                hideLoader();
            }
        });

        document.addEventListener('click', function(e) {
            let anchor = e.target.closest('a');
            // Check if it's a standard navigation link
            if (anchor && anchor.href && anchor.target !== '_blank' && !anchor.getAttribute('href').startsWith('#') && !anchor.getAttribute('href').startsWith('javascript:') && !anchor.classList.contains('btn')) {
                e.preventDefault();
                showLoader();
                // Navigate immediately, no delay for animation
                window.location.href = anchor.href;
            }
        });
    </script>
    <script>
    const commentModal = document.getElementById('commentModal');
    const commentModalContent = commentModal.querySelector('.modal-content');
    
    // --- Universal Button Loader ---
    function setButtonLoading(button, isLoading) {
        if (!button) return;
        if (isLoading) {
            if (!button.dataset.originalHtml) {
                button.dataset.originalHtml = button.innerHTML;
            }
            button.disabled = true;
            let spinnerSize = '20px';
            let borderWidth = '2px';
            if(button.classList.contains('action-button')) {
                spinnerSize = '16px';
            }
            button.innerHTML = `<div class="spinner" style="width:${spinnerSize}; height:${spinnerSize}; border-width:${borderWidth};"></div>`;
        } else {
            button.disabled = false;
            if (button.dataset.originalHtml) {
                button.innerHTML = button.dataset.originalHtml;
                delete button.dataset.originalHtml;
            }
        }
    }

    function buildCommentNode(comment) {
        const container = document.createElement('div');
        container.className = 'comment-container';
        container.dataset.commentId = comment.id;
        container.style.marginTop = '16px';

        const likeIcon = ICONS.like.replace('width="24"','width="18"').replace('height="24"','height="18"');
        const repostIcon = ICONS.repost.replace('width="24"','width="18"').replace('height="24"','height="18"');

        let repliesButton = '';
        if (comment.replies_count > 0) {
            repliesButton = `<button class="view-replies-btn" onclick="toggleReplies(this, ${comment.id})">Ver ${comment.replies_count} respostas</button>`;
        }
        
        let pfpElement = '';
        if (comment.user.pfp_filename) {
            pfpElement = `<img src="/static/uploads/${comment.user.pfp_filename}" style="width:40px; height:40px; border-radius:50%; object-fit:cover;">`;
        } else {
            pfpElement = `<div style="width:40px; height:40px; border-radius:50%; flex-shrink:0; background:${comment.user.pfp_gradient}; display:flex; align-items:center; justify-content:center; font-weight:bold;">${comment.user.initial}</div>`;
        }

        let deleteButton = '';
        if(comment.is_owned_by_user) {
            deleteButton = `<button onclick="handleDeleteComment(this, ${comment.id})" class="action-button delete-btn">${ICONS.trash}</button>`;
        }

        container.innerHTML = `
            <div style="display: flex; gap: 12px;">
                <div style="flex-shrink:0;">${pfpElement}</div>
                <div style="flex-grow:1">
                    <div><strong style="color:var(--text-color);">${comment.user.username}</strong> <span style="color:var(--text-muted);">· ${comment.timestamp}</span></div>
                    <div style="color:var(--text-color); margin: 4px 0; white-space: pre-wrap; word-wrap: break-word;">${comment.text}</div>
                    <div class="comment-actions" style="display: flex; gap: 12px; align-items: center; margin-top: 8px;">
                        <button onclick="handleLikeComment(this, ${comment.id})" class="action-button ${comment.is_liked_by_user ? 'liked' : ''}">${likeIcon}<span>${comment.like_count}</span></button>
                        <button onclick="prepareReply(${comment.id}, '${comment.user.username}')" class="action-button">${ICONS.reply}<span>Responder</span></button>
                        <button onclick="handleCommentRepost(this, ${comment.id})" class="action-button">${repostIcon}<span>Republicar</span></button>
                        ${deleteButton}
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
        });
    }

    async function toggleReplies(button, commentId) {
        const commentNode = button.closest('.comment-container');
        const repliesWrapper = commentNode.querySelector('.replies-wrapper');

        if (repliesWrapper.style.display === 'none') {
            if (!repliesWrapper.hasChildNodes()) { // Fetch only if empty
                repliesWrapper.innerHTML = '<div class="spinner" style="margin: 20px auto; width:20px; height:20px; border-width:2px;"></div>';
                const response = await fetch(`/comment/${commentId}/replies`);
                const replies = await response.json();
                repliesWrapper.innerHTML = '';
                if(replies.length > 0) {
                    repliesWrapper.classList.add('comment-thread');
                    appendComments(repliesWrapper, replies);
                } else {
                    repliesWrapper.innerHTML = '<p style="color:var(--text-muted); padding-left:20px;">Nenhuma resposta encontrada.</p>';
                }
            }
            repliesWrapper.style.display = 'block';
            button.textContent = 'Esconder respostas';
        } else {
            repliesWrapper.style.display = 'none';
            button.textContent = button.textContent.replace('Esconder', 'Ver');
        }
    }

    async function openCommentModal(postId, highlightCommentId = null) {
        document.getElementById('comment-post-id').value = postId;
        const list = document.getElementById('comment-list');
        const contextContainer = document.getElementById('comment-original-post-context');

        list.innerHTML = '<div class="spinner" style="margin: 40px auto;"></div>';
        contextContainer.innerHTML = '';
        
        commentModal.style.display = 'flex';
        commentModalContent.classList.remove('closing');
        commentModalContent.classList.add('opening');
        document.body.style.overflow = 'hidden';

        // Fetch both comments and post context in parallel
        const [commentsResponse, postContextResponse] = await Promise.all([
            fetch(`/post/${postId}/comments`),
            fetch(`/post/${postId}/context`)
        ]);

        const comments = await commentsResponse.json();
        const postContext = await postContextResponse.json();
        
        // Render post context
        if (postContext.html) {
            contextContainer.innerHTML = postContext.html;
        }

        list.innerHTML = '';
        if (comments.length === 0) {
            list.innerHTML = '<p style="text-align:center; color: var(--text-muted);">Nenhum comentário ainda.</p>';
        } else {
            appendComments(list, comments);
            if (highlightCommentId) {
                setTimeout(() => {
                    const highlightedComment = list.querySelector(`.comment-container[data-comment-id='${highlightCommentId}']`);
                    if (highlightedComment) {
                        highlightedComment.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        highlightedComment.style.backgroundColor = 'rgba(29, 155, 240, 0.1)';
                        setTimeout(() => { highlightedComment.style.backgroundColor = 'transparent'; }, 2000);
                    }
                }, 100);
            }
        }
    }

    function closeCommentModal() {
        commentModalContent.classList.remove('opening');
        commentModalContent.classList.add('closing');

        setTimeout(() => {
            commentModal.style.display = 'none';
            commentModalContent.classList.remove('closing');
            const isSixsView = document.body.classList.contains('sixs-view');
            if (!isSixsView) document.body.style.overflow = 'auto';
            prepareReply(null, null);
        }, 250);
    }
    
    function prepareReply(parentId, username) {
        const textInput = document.getElementById('comment-text-input');
        const parentIdInput = document.getElementById('comment-parent-id');
        if (parentId) {
            parentIdInput.value = parentId;
            textInput.placeholder = `Respondendo a @${username}...`;
            textInput.focus();
        } else {
            parentIdInput.value = '';
            textInput.placeholder = 'Adicionar um comentário...';
        }
    }

    document.getElementById('comment-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const button = e.target.querySelector('button[type=submit]');
        const originalHtml = button.innerHTML;
        setButtonLoading(button, true);

        const postId = document.getElementById('comment-post-id').value;
        const parentId = document.getElementById('comment-parent-id').value;
        const text = document.getElementById('comment-text-input').value;
        if (!text.trim()) {
            button.innerHTML = originalHtml;
            button.disabled = false;
            return;
        }
        
        try {
            const response = await fetch(`/post/${postId}/comment`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, parent_id: parentId || null })
            });

            if (response.ok) {
                document.getElementById('comment-text-input').value = '';
                prepareReply(null, null);
                openCommentModal(postId); // Refresh comments
                const countEl = document.querySelector(`#comment-count-${postId}`);
                if(countEl) countEl.innerText = parseInt(countEl.innerText) + 1;
            }
        } finally {
            button.innerHTML = originalHtml;
            button.disabled = false;
        }
    });

    commentModal.addEventListener('click', (event) => { if (event.target === commentModal) closeCommentModal(); });
    
    async function handleLike(button, postId) {
        const originalHtml = button.innerHTML;
        setButtonLoading(button, true);
        try {
            const response = await fetch(`/like/post/${postId}`, { method: 'POST' });
            const data = await response.json();
            
            button.innerHTML = originalHtml; // Restore structure
            button.querySelector('span').innerText = data.likes;
            button.classList.toggle('liked', data.liked);
        } catch(e) {
            button.innerHTML = originalHtml; // Restore on error
            flash('Ação falhou. Tente novamente.', 'error');
        } finally {
            button.disabled = false;
        }
    }

    async function handleLikeComment(button, commentId) {
        const originalHtml = button.innerHTML;
        setButtonLoading(button, true);
        try {
            const response = await fetch(`/like/comment/${commentId}`, { method: 'POST' });
            const data = await response.json();
            
            button.innerHTML = originalHtml; // Restore structure
            button.querySelector('span').innerText = data.likes;
            button.classList.toggle('liked', data.liked);
        } catch(e) {
            button.innerHTML = originalHtml; // Restore on error
            flash('Ação falhou. Tente novamente.', 'error');
        } finally {
            button.disabled = false;
        }
    }

    async function handleRepost(button, postId) {
        const caption = prompt("Adicionar uma legenda (opcional):", "");
        if (caption === null) return; 

        const originalHtml = button.innerHTML;
        setButtonLoading(button, true);
        try {
            const response = await fetch(`/repost/post/${postId}`, { 
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ caption: caption })
            });
            const data = await response.json();
            
            button.innerHTML = originalHtml; // Restore structure
            if(data.success) {
                button.classList.toggle('reposted', data.reposted);
                flash(data.message, 'success');
            } else {
                flash(data.message, 'error');
            }
        } catch(e) {
            button.innerHTML = originalHtml; // Restore on error
            flash('Ação falhou. Tente novamente.', 'error');
        } finally {
            button.disabled = false;
        }
    }
    
    async function handleCommentRepost(button, commentId) {
        const caption = prompt("Adicionar uma legenda (opcional):", "");
        if (caption === null) return;

        const originalHtml = button.innerHTML;
        setButtonLoading(button, true);
        try {
            const response = await fetch(`/repost/comment/${commentId}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ caption: caption })
            });
            const data = await response.json();
            
            button.innerHTML = originalHtml; // Restore structure
            if(data.success) {
                flash(data.message, 'success');
            } else {
                flash(data.message, 'error');
            }
        } catch(e) {
            button.innerHTML = originalHtml; // Restore on error
            flash('Ação falhou. Tente novamente.', 'error');
        } finally {
            button.disabled = false;
        }
    }

    async function handleDeletePost(button, postId) {
        if (!confirm('Tem certeza que deseja deletar esta publicação? Esta ação é permanente.')) return;
        setButtonLoading(button, true);
        try {
            const response = await fetch(`/delete_post/${postId}`, { method: 'POST' });
            const data = await response.json();
            if(data.success) {
                const postElement = document.getElementById(`post-${postId}`);
                if(postElement) {
                    postElement.style.transition = 'opacity 0.25s ease';
                    postElement.style.opacity = '0';
                    setTimeout(() => postElement.remove(), 250);
                }
                flash(data.message, 'success');
            } else {
                flash(data.message, 'error');
                setButtonLoading(button, false); // Restore only on failure
            }
        } catch(e) {
            setButtonLoading(button, false); // Restore on error
            flash('Ação falhou. Tente novamente.', 'error');
        }
    }

    async function handleDeleteComment(button, commentId) {
        if (!confirm('Tem certeza que deseja deletar este comentário?')) return;
        setButtonLoading(button, true);
        try {
            const response = await fetch(`/delete_comment/${commentId}`, { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                const commentElement = button.closest('.comment-container');
                if (commentElement) {
                    commentElement.style.transition = 'opacity 0.25s ease';
                    commentElement.style.opacity = '0';
                    setTimeout(() => commentElement.remove(), 250);
                }
                const postId = document.getElementById('comment-post-id').value;
                const countEl = document.querySelector(`#comment-count-${postId}`);
                if(countEl) countEl.innerText = Math.max(0, parseInt(countEl.innerText) - 1);
                
                flash(data.message, 'success');
            } else {
                flash(data.message, 'error');
                setButtonLoading(button, false); // Restore only on failure
            }
        } catch(e) {
             setButtonLoading(button, false); // Restore on error
            flash('Ação falhou. Tente novamente.', 'error');
        }
    }

    function flash(message, category = 'info') {
        const container = document.querySelector('.flash-message-container') || document.body;
        const flashDiv = document.createElement('div');
        flashDiv.className = `flash-message ${category}`;
        flashDiv.textContent = message;
        container.appendChild(flashDiv);
        setTimeout(() => {
            flashDiv.remove();
        }, 3000);
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
        flex-direction: column; text-align: center;
    }
    .six-video-wrapper {
        position: relative;
        display:flex; justify-content:center; align-items:center;
        transition: all 0.3s ease;
        {% if current_user.is_authenticated and current_user.six_feed_style == 'fullscreen' %}
        width: 100%; height: 100%;
        {% else %}
        width: min(100vw, 100dvh); height: min(100vw, 100dvh);
        clip-path: circle(50% at 50% 50%);
        {% endif %}
    }
    .six-video { 
        width: 100%; height: 100%; object-fit: cover;
        display: block;
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    .six-video.loaded { opacity: 1; }
    .video-loader {
        position: absolute; width: 40px; height: 40px;
        border: 4px solid rgba(255,255,255,0.2);
        border-top-color: #fff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        z-index: 5;
    }
    .six-video.loaded + .video-loader { display: none; }
    .six-ui-overlay {
        position: absolute; bottom: 0; left: 0; right: 0; top: 0;
        color: white; display: flex; justify-content: space-between; align-items: flex-end;
        padding: 16px; padding-bottom: 70px; pointer-events: none;
        background: linear-gradient(to top, rgba(0,0,0,0.5), transparent 40%), linear-gradient(to bottom, rgba(0,0,0,0.4), transparent 20%);
        text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
    }
    .six-info { pointer-events: auto; text-align: left; }
    .six-info .username { font-weight: bold; font-size: 1.1em; }
    .six-actions {
        display: flex; flex-direction: column; gap: 20px;
        pointer-events: auto;
    }
    .six-actions button {
        background: none; border: none; color: white;
        display: flex; flex-direction: column; align-items: center;
        gap: 5px; cursor: pointer; font-size: 13px;
        transition: transform 0.2s ease;
    }
    .six-actions button:active { transform: scale(0.9); }
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
    .content-spacer { height: 80px; }
    .feed-divider {
        padding: 12px 16px; text-align: center; color: var(--text-muted);
        border-bottom: 1px solid var(--border-color);
        font-size: 0.9em;
    }
{% endblock %}
{% block content %}
    <div class="feed-nav" style="display: flex; border-bottom: 1px solid var(--border-color);">
        <a href="{{ url_for('home', feed_type='text') }}" style="flex:1; text-align:center; padding: 15px; color: {% if feed_type == 'text' %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">Texto {% if feed_type == 'text' %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
        <a href="{{ url_for('home', feed_type='sixs') }}" style="flex:1; text-align:center; padding: 15px; color: {% if feed_type == 'sixs' %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">Sixs {% if feed_type == 'sixs' %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
    </div>

    {% if feed_type == 'text' %}
        <div style="border-bottom: 1px solid var(--border-color); padding: 12px 16px;">
            <form method="POST" action="{{ url_for('create_text_post') }}" enctype="multipart/form-data" onsubmit="setButtonLoading(this.querySelector('button[type=submit]'), true)">
                <div class="form-group" style="margin-bottom: 1rem;">
                    <textarea name="text_content" class="comment-input-style auto-growing" placeholder="O que está acontecendo?" required maxlength="150" rows="1"></textarea>
                    
                    <!-- Image Preview Container -->
                    <div id="image-preview-container" style="display: none; position: relative; margin-top: 10px; max-width: 150px;">
                        <img id="image-preview" src="#" alt="Image preview" style="width: 100%; border-radius: 16px; border: 1px solid var(--border-color);" />
                        <button type="button" id="remove-image-btn" style="position: absolute; top: 5px; right: 5px; background: rgba(0,0,0,0.7); color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-weight: bold; font-size: 16px; display: flex; align-items: center; justify-content: center;">×</button>
                    </div>
                </div>

                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <label for="image-upload" class="attachment-btn" title="Anexar imagem">
                        {{ ICONS.attach_file|safe }}
                    </label>
                    <input type="file" id="image-upload" name="image" accept="image/png, image/jpeg, image/gif" style="display: none;">
                    <button type="submit" class="btn">Publicar</button>
                </div>
            </form>
        </div>
        
        {% for post in unseen_posts %}
            {% include 'post_card_text.html' %}
        {% endfor %}

        {% if unseen_posts and seen_posts %}
            <div class="feed-divider">Publicações já vistas</div>
        {% endif %}

        {% for post in seen_posts %}
            {% include 'post_card_text.html' %}
        {% endfor %}

        {% if unseen_posts or seen_posts %}
             <div class="feed-divider" style="border-top: 1px solid var(--border-color); border-bottom: none;">Fim das publicações</div>
        {% endif %}
        
        {% if not unseen_posts and not seen_posts %}
            <div style="text-align:center; padding: 40px; color:var(--text-muted);">
                <h4>Seu feed está vazio.</h4>
                <p>Siga contas na página <a href="{{ url_for('discover') }}">Descobrir</a>!</p>
            </div>
        {% endif %}
        <div class="content-spacer"></div>

    {% elif feed_type == 'sixs' %}
        <div id="sixs-feed-container">
            <div id="unmute-prompt">Toque para ativar o som</div>
            <button id="volume-toggle">{{ ICONS.volume_off|safe }}</button>
            
            {% for post in unseen_posts %}
                {% include 'six_slide.html' %}
            {% endfor %}

            {% if unseen_posts and seen_posts %}
            <section class="six-video-slide">
                <div style="color:white; padding: 20px;">
                    <h3 style="margin-bottom: 8px;">Você está em dia!</h3>
                    <p style="color: var(--text-muted);">Role para baixo para rever os Sixs que você já assistiu.</p>
                </div>
            </section>
            {% endif %}

            {% for post in seen_posts %}
                {% include 'six_slide.html' %}
            {% endfor %}

            {% if unseen_posts or seen_posts %}
            <section class="six-video-slide">
                 <div style="color:white; padding: 20px;">
                    <h3 style="margin-bottom: 24px;">Fim dos Sixs</h3>
                    <div style="display:flex; flex-direction:column; gap: 16px;">
                        <button class="btn btn-outline" onclick="document.getElementById('sixs-feed-container').scrollTo({top: 0, behavior: 'smooth'})">Voltar ao Topo</button>
                        <a href="{{ url_for('create_post') }}" class="btn">Gravar um Six</a>
                    </div>
                </div>
            </section>
            {% endif %}
            
            {% if not unseen_posts and not seen_posts %}
            <section class="six-video-slide">
                <a href="{{ url_for('home', feed_type='text') }}" style="position: absolute; top: 20px; left: 20px; z-index: 100; pointer-events: auto; color: white;">
                    {{ ICONS.back_arrow|safe }}
                </a>
                <h4>Nenhum Six para mostrar!</h4>
                <p style="color:#aaa;">Siga contas ou crie o seu próprio.</p>
                <a href="{{ url_for('create_post') }}" class="btn" style="margin-top:20px;">Criar um Six</a>
            </section>
            {% endif %}
        </div>
    {% endif %}
{% endblock %}
{% block scripts %}
{% if feed_type == 'text' %}
<script>
    // --- Auto-growing textarea logic ---
    const textarea = document.querySelector('textarea.auto-growing');
    if (textarea) {
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto'; // Reset height
            textarea.style.height = (textarea.scrollHeight) + 'px'; // Set to content height
        });
    }

    // --- Image Preview Logic ---
    const imageInput = document.getElementById('image-upload');
    const previewContainer = document.getElementById('image-preview-container');
    const imagePreview = document.getElementById('image-preview');
    const removeImageBtn = document.getElementById('remove-image-btn');

    imageInput.addEventListener('change', function() {
        if (this.files && this.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                imagePreview.setAttribute('src', e.target.result);
                previewContainer.style.display = 'block';
            }
            reader.readAsDataURL(this.files[0]);
        }
    });

    removeImageBtn.addEventListener('click', function() {
        previewContainer.style.display = 'none';
        imagePreview.setAttribute('src', '#');
        imageInput.value = ''; // This is crucial to clear the file selection
    });


    document.querySelectorAll('img[data-src]').forEach(img => {
        img.onload = () => {
            img.classList.add('loaded');
        };
    });

    const seenTextPosts = new Set();
    function markTextPostAsSeen(postId) {
        if (!postId || seenTextPosts.has(postId)) {
            return;
        }
        seenTextPosts.add(postId);
        fetch(`/mark_text_post_as_seen/${postId}`, { method: 'POST' });
    }
    const textObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                markTextPostAsSeen(entry.target.dataset.postId);
            }
        });
    }, { threshold: 0.5 });
    document.querySelectorAll('.post-card').forEach(card => textObserver.observe(card));
</script>
{% endif %}

{% if feed_type == 'sixs' %}
<script>
    const container = document.getElementById('sixs-feed-container');
    const allVideos = Array.from(container.querySelectorAll('.six-video'));
    const volumeToggle = document.getElementById('volume-toggle');
    const unmutePrompt = document.getElementById('unmute-prompt');

    let isMuted = true;
    let hasInteracted = false;
    const seenSixs = new Set();

    function setMutedState(shouldMute) {
        isMuted = shouldMute;
        allVideos.forEach(v => v.muted = isMuted);
        volumeToggle.innerHTML = isMuted ? ICONS.volume_off : ICONS.volume_on;
        const currentVideo = document.querySelector('.is-visible video');
        if (currentVideo) {
            currentVideo.muted = isMuted;
        }
    }
    
    allVideos.forEach(video => {
        video.addEventListener('canplaythrough', () => {
            video.classList.add('loaded');
        });
    });

    if (allVideos.length > 0) {
        volumeToggle.style.display = 'block';
        
        volumeToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            hasInteracted = true;
            unmutePrompt.style.display = 'none';
            setMutedState(!isMuted);
        });
        
        container.addEventListener('click', () => {
            if (!hasInteracted) {
                hasInteracted = true;
                unmutePrompt.style.display = 'none';
                setMutedState(false);
            }
        }, { once: true });
    }
    
    function markSixAsSeen(postId) {
        if (!postId || seenSixs.has(postId)) return;
        seenSixs.add(postId);
        fetch(`/mark_six_as_seen/${postId}`, { method: 'POST' });
    }

    const sixObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const slide = entry.target;
            const video = slide.querySelector('video');
            
            if (entry.isIntersecting && entry.intersectionRatio >= 0.7) {
                slide.classList.add('is-visible');
                if (video) {
                    video.muted = isMuted;
                    const playPromise = video.play();
                    if (playPromise !== undefined) {
                        playPromise.catch(error => {
                            if (!hasInteracted && allVideos.length > 0) {
                                unmutePrompt.style.display = 'block';
                            }
                        });
                    }
                    markSixAsSeen(slide.dataset.postId);
                }
            } else { 
                slide.classList.remove('is-visible');
                if (video) {
                    video.pause(); 
                    video.currentTime = 0;
                }
            }
        });
    }, { threshold: 0.7 });

    document.querySelectorAll('.six-video-slide').forEach(slide => {
      sixObserver.observe(slide);
    });
</script>
{% endif %}
{% endblock %}
""",
"six_slide.html": """
<section class="six-video-slide" id="post-{{ post.id }}" data-post-id="{{ post.id }}">
    <div class="six-video-wrapper">
        <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop preload="auto" playsinline muted></video>
        <div class="video-loader"></div>
    </div>
    <div class="six-ui-overlay">
        <a href="{{ url_for('home', feed_type='text') }}" style="position: absolute; top: 20px; left: 20px; z-index: 100; pointer-events: auto; color: white; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5));">
            {{ ICONS.back_arrow|safe }}
        </a>
        <div class="six-info">
            <a href="{{ url_for('profile', username=post.author.username) }}" style="color:white;"><strong class="username">@{{ post.author.username }}</strong><span style="font-weight: normal; color: rgba(255,255,255,0.8); font-size: 0.9em;"> · {{ post.timestamp|sao_paulo_time }}</span></a>
            <p>{{ post.text_content }}</p>
        </div>
        <div class="six-actions">
            <button onclick="handleLike(this, {{ post.id }})" class="action-button {{ 'liked' if post.liked_by_current_user else '' }}">
                {{ ICONS.like|safe }}
                <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
            </button>
            <button onclick="openCommentModal({{ post.id }})">{{ ICONS.comment|safe }} <span id="comment-count-{{ post.id }}">{{ post.comments.count() }}</span></button>
            <button onclick="handleRepost(this, {{ post.id }})" class="action-button {{ 'reposted' if post.reposted_by_current_user else '' }}">{{ ICONS.repost|safe }}</button>
            {% if post.author == current_user %}
            <button onclick="handleDeletePost(this, {{ post.id }})" class="delete-btn">{{ ICONS.trash|safe }}</button>
            {% endif %}
        </div>
    </div>
</section>
""",
"post_card_six.html": """
<a href="{{ url_for('profile', username=post.author.username, tab='sixs', scrollTo=post.id) }}" style="text-decoration: none; color: inherit; display: flex; align-items: flex-start; gap: 12px; margin-top: 8px; padding: 12px; border: 1px solid var(--border-color); border-radius: 16px;">
    <div style="position: relative; width: 100px; height: 100px; border-radius: 50%; overflow: hidden; background-color: #111; flex-shrink: 0;">
        <video src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop muted autoplay playsinline style="width: 100%; height: 100%; object-fit: cover;"></video>
    </div>
    <div style="padding-top: 8px;">
        <div style="font-weight: bold; display: flex; align-items: center; gap: 8px;">
            {% if post.author.pfp_filename %}<img src="{{ url_for('static', filename='uploads/' + post.author.pfp_filename) }}" alt="PFP" style="width:20px; height:20px; border-radius:50%; object-fit: cover;">
            {% else %}<div style="width:20px; height:20px; border-radius:50%; background:{{ post.author.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size: 0.8em;">{{ post.author.username[0]|upper }}</div>{% endif %}
            @{{ post.author.username }}
        </div>
        <div style="color: var(--text-muted); font-size: 0.9em; margin-top: 4px;">{{ post.text_content|truncate(80) }}</div>
    </div>
</a>
""",
"post_card_text.html": """
<div class="post-card" id="post-{{ post.id }}" data-post-id="{{ post.id }}" style="border-bottom: 1px solid var(--border-color); padding: 12px 16px; display:flex; gap:12px;">
    <div style="width:40px; height:40px; flex-shrink:0;">
        {% if post.author.pfp_filename %}
            <img src="{{ url_for('static', filename='uploads/' + post.author.pfp_filename) }}" alt="Foto de perfil de {{ post.author.username }}" style="width:40px; height:40px; border-radius:50%; object-fit: cover;">
        {% else %}
            <div style="width:40px; height:40px; border-radius:50%; background:{{ post.author.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">
                {{ post.author.username[0]|upper }}
            </div>
        {% endif %}
    </div>
    <div style="flex-grow:1;">
        <div>
            <a href="{{ url_for('profile', username=post.author.username) }}" style="color:var(--text-color); font-weight:bold;">{{ post.author.username }}</a>
            <span style="color:var(--text-muted);">· {{ post.timestamp|sao_paulo_time }}</span>
        </div>
        <a href="{{ url_for('view_post', post_id=post.id) }}" style="color: inherit; text-decoration: none;">
            <div style="margin: 4px 0 12px 0; white-space: pre-wrap; word-wrap: break-word; cursor: pointer;">{{ post.text_content }}</div>
        </a>
        {% if post.image_filename %}
            <div style="position: relative; margin-bottom:12px;">
                <div class="spinner" style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); z-index:1;"></div>
                <img src="{{ url_for('static', filename='uploads/' + post.image_filename) }}" style="width:100%; border-radius:16px; border: 1px solid var(--border-color); opacity:0; transition: opacity 0.3s ease;" onload="this.style.opacity=1; this.previousElementSibling.style.display='none';">
            </div>
        {% endif %}
        <div style="display: flex; justify-content: space-between; max-width: 425px; color:var(--text-muted);">
            <div style="display: flex; gap: 8px;">
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
            {% if post.author == current_user %}
            <button onclick="handleDeletePost(this, {{ post.id }})" class="action-button delete-btn">{{ ICONS.trash|safe }}</button>
            {% endif %}
        </div>
    </div>
</div>
""",
"comment_card.html": """
<div class="comment-card" style="border: 1px solid var(--border-color); border-radius: 16px; padding: 12px; margin-top: 8px;">
    <div style="display:flex; gap:12px;">
        <div style="width:30px; height:30px; flex-shrink:0;">
            {% if comment.user.pfp_filename %}
                <img src="{{ url_for('static', filename='uploads/' + comment.user.pfp_filename) }}" alt="Foto de perfil de {{ comment.user.username }}" style="width:30px; height:30px; border-radius:50%; object-fit: cover;">
            {% else %}
                <div style="width:30px; height:30px; border-radius:50%; background:{{ comment.user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size: 14px;">
                    {{ comment.user.username[0]|upper }}
                </div>
            {% endif %}
        </div>
        <div style="flex-grow:1;">
            <div>
                <a href="{{ url_for('profile', username=comment.user.username) }}" style="color:var(--text-color); font-weight:bold;">{{ comment.user.username }}</a>
                <span style="color:var(--text-muted); font-size: 0.9em;">· {{ comment.timestamp|sao_paulo_time }}</span>
            </div>
            <a href="javascript:openCommentModal({{ comment.post_id }}, {{ comment.id }})" style="color:inherit; text-decoration:none;">
                <p style="margin: 4px 0 0 0; font-size: 0.95em; cursor: pointer;">{{ comment.text }}</p>
            </a>
        </div>
    </div>
</div>
""",
"create_post.html": """
{% extends "layout.html" %}
{% block title %}Criar Six{% endblock %}
{% block style_override %}
    #six-creator-ui {
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        display: flex; flex-direction: column; align-items: center; justify-content: space-between;
        color: white; z-index: 100;
        background: #000;
        padding: 20px 0;
        box-sizing: border-box;
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    #six-creator-ui.visible { opacity: 1; }
    .controls-top {
        width: 100%; padding: 0 20px; box-sizing: border-box;
        display: flex; justify-content: space-between; align-items: center;
    }
    .video-container {
        width: 90vw;
        max-width: 480px;
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        overflow: hidden;
        background: #111;
        position: relative;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    #video-preview {
        width: 100%; height: 100%;
        object-fit: cover;
        transition: transform 0.3s ease;
    }
    #video-preview.mirrored { transform: scaleX(-1); }
    .controls-bottom {
        width: 100%;
        display: flex; flex-direction: column; align-items: center; gap: 15px;
    }
    .recorder-controls-wrapper {
        height: 80px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 30px;
    }
    .icon-btn {
        background: rgba(255,255,255,0.15); color: white; border: none;
        width: 50px; height: 50px;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer;
        border-radius: 50%;
        backdrop-filter: blur(5px);
        transition: all 0.2s ease;
    }
    .icon-btn:active { transform: scale(0.9); background: rgba(255,255,255,0.25); }
    .icon-btn:disabled { opacity: 0.3; cursor: not-allowed; }
    .record-button {
        width: 70px; height: 70px; border: 4px solid rgba(255,255,255,0.8);
        background-color: transparent; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        border-radius: 50%;
        padding: 2px;
        transition: all 0.2s ease-in-out;
    }
    .record-button .inner-circle {
        width: 100%; height: 100%; background-color: var(--red-color);
        border-radius: 50%;
        transition: all 0.2s ease-in-out;
    }
    .record-button.recording .inner-circle {
        width: 50%; height: 50%;
        border-radius: 8px;
    }
    .progress-ring {
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%) rotate(-90deg);
        z-index: 105; pointer-events: none;
    }
    .progress-ring__circle {
        stroke-dashoffset: 0;
        transition: stroke-dashoffset 0.1s linear;
        stroke: var(--accent-color);
        stroke-linecap: round;
    }
{% endblock %}
{% block content %}
    <div id="permission-prompt" style="padding:16px; text-align: center; color: white; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <div id="prompt-content">
            <p id="permission-status" style="color:var(--text-muted); min-height: 20px; margin: 20px 0; max-width: 300px;">Toque para habilitar sua câmera e microfone para gravar um Six.</p>
            <button id="enable-camera-btn" class="btn">Habilitar Câmera</button>
        </div>
    </div>

    <div id="six-creator-ui" style="display: none;">
        <div class="controls-top">
            <a href="{{ url_for('home') }}" class="icon-btn">{{ ICONS.back_arrow|safe }}</a>
            <button id="switch-camera-btn" class="icon-btn">{{ ICONS.camera_switch|safe }}</button>
        </div>

        <div class="video-container">
            <video id="video-preview" autoplay muted playsinline></video>
             <svg class="progress-ring" width="84" height="84">
                <circle class="progress-ring__circle" stroke-width="4" fill="transparent" r="40" cx="42" cy="42"/>
            </svg>
        </div>

        <div class="controls-bottom">
            <p id="recorder-status" style="min-height: 20px; text-shadow: 1px 1px 2px #000;">Toque no botão para gravar</p>
            <div class="recorder-controls-wrapper">
                 <button id="retake-btn" class="icon-btn">{{ ICONS.redo|safe }}</button>
                 <button id="record-button" class="record-button"><div class="inner-circle"></div></button>
                 <button id="pause-resume-btn" class="icon-btn"></button>
                 <button id="finish-btn" class="icon-btn">{{ ICONS.check|safe }}</button>
            </div>
             <form id="six-form-element" method="POST" enctype="multipart/form-data" style="display: none; width: 80%; max-width: 400px; margin-top: 5px;">
                 <input type="hidden" name="post_type" value="six">
                 <div class="form-group"> <input type="text" name="caption" maxlength="50" placeholder="Adicionar uma legenda... (opcional)"> </div>
                 <button type="submit" class="btn" style="width: 100%;">Publicar Six</button>
            </form>
        </div>
    </div>
{% endblock %}
{% block scripts %}
<script>
    const MAX_DURATION = 6000; // ms
    let mediaRecorder; 
    let recordedBlobs = []; 
    let stream;
    let facingMode = 'user';
    let recorderState = 'idle'; // idle, recording, paused, previewing
    let recordedDuration = 0;
    let timerInterval;

    const sixCreatorUI = document.getElementById('six-creator-ui');
    const permissionPrompt = document.getElementById('permission-prompt');
    const promptContent = document.getElementById('prompt-content');
    const enableCameraBtn = document.getElementById('enable-camera-btn');
    const preview = document.getElementById('video-preview');
    const switchCameraBtn = document.getElementById('switch-camera-btn');
    const recorderStatus = document.getElementById('recorder-status');
    const recordButton = document.getElementById('record-button');
    const pauseResumeBtn = document.getElementById('pause-resume-btn');
    const retakeBtn = document.getElementById('retake-btn');
    const finishBtn = document.getElementById('finish-btn');
    const sixForm = document.getElementById('six-form-element');
    
    const progressCircle = document.querySelector('.progress-ring__circle');
    const radius = progressCircle.r.baseVal.value;
    const circumference = radius * 2 * Math.PI;
    progressCircle.style.strokeDasharray = `${circumference} ${circumference}`;
    
    function setProgress(duration) {
        const percent = (duration / MAX_DURATION);
        const offset = circumference - percent * circumference;
        progressCircle.style.strokeDashoffset = offset;
    }

    async function initCamera() {
        promptContent.innerHTML = '<div class="spinner"></div>';
        try {
            if (stream) { stream.getTracks().forEach(track => track.stop()); }
            const constraints = { audio: true, video: { width: 480, height: 480, facingMode: facingMode } };
            stream = await navigator.mediaDevices.getUserMedia(constraints);
            
            permissionPrompt.style.display = 'none';
            sixCreatorUI.style.display = 'flex';
            if (!sixCreatorUI.classList.contains('visible')) {
                setTimeout(() => sixCreatorUI.classList.add('visible'), 10);
            }
            
            preview.srcObject = stream;
            preview.classList.toggle('mirrored', facingMode === 'user');
            
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp8,opus' });
            mediaRecorder.ondataavailable = e => { if (e.data && e.data.size > 0) recordedBlobs.push(e.data); };
            mediaRecorder.onstop = handleStop;

            if (recorderState === 'idle') {
                resetRecorder();
            } else {
                updateUI();
            }

        } catch (e) {
            console.error(e);
            permissionPrompt.style.display = 'flex';
            promptContent.innerHTML = `<p id="permission-status" style="color:var(--text-muted); max-width: 300px;">Permissão de Câmera/Mic negada. Por favor, habilite nas configurações do seu navegador e atualize a página.</p>`;
        }
    }
    
    function updateUI() {
        const elements = { recordButton, retakeBtn, pauseResumeBtn, finishBtn, sixForm, switchCameraBtn };
        for (const key in elements) {
            elements[key].style.display = 'none';
        }
        
        if (recorderState === 'idle') {
            recorderStatus.textContent = "Toque no botão para gravar";
            recordButton.style.display = 'flex';
            recordButton.classList.remove('recording');
            switchCameraBtn.style.display = 'flex';
            switchCameraBtn.disabled = false;
        } else if (recorderState === 'recording') {
            recorderStatus.textContent = `Gravando... ${((MAX_DURATION - recordedDuration) / 1000).toFixed(1)}s`;
            recordButton.style.display = 'flex';
            recordButton.classList.add('recording');
            switchCameraBtn.style.display = 'flex';
            switchCameraBtn.disabled = true;
        } else if (recorderState === 'paused') {
            recorderStatus.textContent = 'Pausado. Continue ou finalize.';
            pauseResumeBtn.style.display = 'flex';
            retakeBtn.style.display = 'flex';
            finishBtn.style.display = 'flex';
            pauseResumeBtn.innerHTML = ICONS.record_circle;
        } else if (recorderState === 'previewing') {
            recorderStatus.textContent = 'Pré-visualização. Refaça ou publique.';
            retakeBtn.style.display = 'flex';
            sixForm.style.display = 'block';
            switchCameraBtn.style.display = 'none';
        }
    }

    function startRecording() {
        if (recorderState !== 'idle') return;
        recordedBlobs = [];
        mediaRecorder.start();
        recorderState = 'recording';
        startTimer();
        updateUI();
    }
    
    function pauseRecording() {
        if (recorderState !== 'recording' || !mediaRecorder) return;
        mediaRecorder.pause();
        recorderState = 'paused';
        stopTimer();
        updateUI();
    }
    
    function resumeRecording() {
        if (recorderState !== 'paused' || !mediaRecorder) return;
        mediaRecorder.resume();
        recorderState = 'recording';
        startTimer();
        updateUI();
    }
    
    function stopRecording() {
        if (mediaRecorder && (mediaRecorder.state === 'recording' || mediaRecorder.state === 'paused')) {
             mediaRecorder.stop();
        }
    }

    function handleStop() {
        stopTimer();
        recorderState = 'previewing';
        const superBuffer = new Blob(recordedBlobs, { type: 'video/webm' });
        preview.srcObject = null;
        preview.src = window.URL.createObjectURL(superBuffer);
        preview.muted = false;
        preview.controls = false;
        preview.loop = true;
        preview.play();
        updateUI();
    }

    function resetRecorder() {
        stopTimer();
        recordedDuration = 0;
        recorderState = 'idle';
        if (stream) {
            preview.srcObject = stream;
            preview.muted = true;
            preview.play();
        }
        preview.controls = false;
        setProgress(0);
        updateUI();
    }

    function startTimer() {
        timerInterval = setInterval(() => {
            recordedDuration += 100;
            setProgress(recordedDuration);
            recorderStatus.textContent = `Gravando... ${((MAX_DURATION - recordedDuration) / 1000).toFixed(1)}s`;
            if (recordedDuration >= MAX_DURATION) {
                stopRecording();
            }
        }, 100);
    }
    
    function stopTimer() { clearInterval(timerInterval); }

    enableCameraBtn.addEventListener('click', initCamera);
    switchCameraBtn.addEventListener('click', () => {
        if (recorderState === 'idle' || recorderState === 'paused') {
            facingMode = (facingMode === 'user') ? 'environment' : 'user';
            initCamera();
        }
    });
    
    recordButton.addEventListener('click', () => {
        if (recorderState === 'idle') startRecording();
        else if (recorderState === 'recording') pauseRecording();
    });
    pauseResumeBtn.addEventListener('click', resumeRecording);
    retakeBtn.addEventListener('click', resetRecorder);
    finishBtn.addEventListener('click', stopRecording);
    
    sixForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(sixForm);
        const videoBlob = new Blob(recordedBlobs, {type: 'video/webm'});
        formData.append('video_file', videoBlob, 'six-video.webm');
        const submitBtn = sixForm.querySelector('button');
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<div class="spinner" style="width:20px; height:20px; border-width:2px;"></div>`;
        fetch("{{ url_for('create_post') }}", { method: 'POST', body: formData })
        .then(response => { if (response.redirected) window.location.href = response.url; })
        .catch(error => {
            console.error('Erro:', error);
            submitBtn.disabled = false;
            submitBtn.textContent = "Publicar Six";
            recorderStatus.textContent = "Falha no envio. Tente novamente.";
        });
    });
    
    updateUI();
</script>
{% endblock %}
""",
"edit_profile.html": """
{% extends "layout.html" %}
{% block title %}Configurações{% endblock %}
{% block header_title %}Configurações{% endblock %}
{% block content %}
<div style="padding:16px;">
    <form method="POST" action="{{ url_for('edit_profile') }}" enctype="multipart/form-data" onsubmit="setButtonLoading(this.querySelector('button[type=submit]'), true)">
        <h4>Editar Perfil</h4>
        <div class="form-group" style="text-align: center;">
            <label for="pfp" style="cursor: pointer;">
                {% if current_user.pfp_filename %}
                    <img src="{{ url_for('static', filename='uploads/' + current_user.pfp_filename) }}" alt="Sua foto de perfil" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid var(--border-color); margin-bottom: 8px;">
                {% else %}
                    <div style="width: 100px; height: 100px; border-radius:50%; background: {{ current_user.pfp_gradient }}; display:inline-flex; align-items:center; justify-content:center; font-size: 3rem; font-weight:bold; margin-bottom: 8px;">
                        {{ current_user.username[0]|upper }}
                    </div>
                {% endif %}
                <div style="color: var(--accent-color);">Mudar Foto de Perfil</div>
            </label>
            <input type="file" id="pfp" name="pfp" accept="image/png, image/jpeg, image/gif" style="display: none;">
        </div>

        <div class="form-group">
            <label for="username">Nome de usuário</label>
            <input type="text" id="username" name="username" value="{{ current_user.username }}" required minlength="3" maxlength="80">
        </div>
        <div class="form-group">
            <label for="bio">Bio</label>
            <textarea id="bio" name="bio" rows="3" maxlength="150">{{ current_user.bio or '' }}</textarea>
        </div>

        <hr style="border-color: var(--border-color); margin: 30px 0;">
        <h4>Preferências</h4>
        <div class="form-group">
            <label for="six_feed_style">Estilo do Feed de Sixs</label>
            <select name="six_feed_style" id="six_feed_style" class="form-group" style="padding: 12px; width: 100%; -webkit-appearance: none; appearance: none; background-color: var(--primary-color); border: 1px solid var(--border-color);">
                <option value="circle" {% if current_user.six_feed_style == 'circle' %}selected{% endif %}>Círculo</option>
                <option value="fullscreen" {% if current_user.six_feed_style == 'fullscreen' %}selected{% endif %}>Tela Cheia</option>
            </select>
            <small style="color:var(--text-muted); margin-top: 4px; display: block;">Escolha como você prefere visualizar os vídeos Sixs no seu feed.</small>
        </div>
        
        <button type="submit" class="btn" style="width:100%; margin-top: 10px;">Salvar Alterações</button>
    </form>


    <hr style="border-color: var(--border-color); margin: 30px 0;">
    <h4>Alterar Senha</h4>
    <form method="POST" action="{{ url_for('change_password') }}" onsubmit="setButtonLoading(this.querySelector('button[type=submit]'), true)">
        <div class="form-group">
            <label for="current_password">Senha Atual</label>
            <input type="password" id="current_password" name="current_password" required>
        </div>
        <div class="form-group">
            <label for="new_password">Nova Senha</label>
            <input type="password" id="new_password" name="new_password" required minlength="6">
        </div>
        <button type="submit" class="btn">Mudar Senha</button>
    </form>

    <hr style="border-color: var(--border-color); margin: 30px 0;">
    <h4>Gerenciamento de Dados</h4>
    <form method="POST" action="{{ url_for('clear_cache') }}" style="margin-bottom: 24px;" onsubmit="if(confirm('Isso irá limpar os dados em cache no servidor, como imagens e vídeos processados. O site pode carregar um pouco mais devagar na primeira vez que você visualizar o conteúdo novamente. Continuar?')){ setButtonLoading(this.querySelector('button[type=submit]'), true); return true;} else {return false;}">
        <button type="submit" class="btn btn-outline" style="width: 100%;">Limpar Cache do Servidor</button>
    </form>
    
    <hr style="border-color: var(--border-color); margin: 30px 0;">
    <h4>Ações da Conta</h4>
    <a href="{{ url_for('logout') }}" class="btn btn-outline" style="width: 100%; box-sizing: border-box; text-align: center; margin-bottom: 24px;">{{ ICONS.logout|safe }} Sair</a>
    
    <div style="border: 1px solid var(--red-color); border-radius: 8px; padding: 16px;">
        <h5 style="margin-top:0;">Deletar Conta</h5>
        <p style="color:var(--text-muted);">Esta ação é permanente. Todas as suas publicações, comentários, curtidas e dados de seguidores serão removidos.</p>
        <form action="{{ url_for('delete_account') }}" method="POST" onsubmit="if(confirm('Tem certeza absoluta?')){ setButtonLoading(this.querySelector('button[type=submit]'), true); return true;} else {return false;}">
             <div class="form-group"><label for="password">Confirme com sua senha</label><input type="password" id="password" name="password" required></div>
            <button type="submit" class="btn btn-danger">{{ ICONS.trash|safe }} Deletar Minha Conta</button>
        </form>
    </div>
    <div class="content-spacer"></div>
</div>
{% endblock %}
""",
"profile.html": """
{% extends "layout.html" %}
{% block title %}{{ user.username }}{% endblock %}
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
        display:flex; justify-content:center; align-items:center;
        transition: all 0.3s ease;
        {% if current_user.is_authenticated and current_user.six_feed_style == 'fullscreen' %}
        width: 100%; height: 100%;
        {% else %}
        width: min(100vw, 100dvh); height: min(100vw, 100dvh);
        clip-path: circle(50% at 50% 50%);
        {% endif %}
    }
    .six-video { 
        width: 100%; height: 100%; object-fit: cover; 
        display: block; opacity: 0; transition: opacity 0.3s ease;
    }
    .six-video.loaded { opacity: 1; }
    .video-loader {
        position: absolute; width: 40px; height: 40px;
        border: 4px solid rgba(255,255,255,0.2);
        border-top-color: #fff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        z-index: 5;
    }
    .six-video.loaded + .video-loader { display: none; }
    .six-ui-overlay {
        position: absolute; bottom: 0; left: 0; right: 0; top: 0;
        color: white; display: flex; justify-content: space-between; align-items: flex-end;
        padding: 16px; padding-bottom: 70px; pointer-events: none;
        background: linear-gradient(to top, rgba(0,0,0,0.5), transparent 40%), linear-gradient(to bottom, rgba(0,0,0,0.4), transparent 20%);
        text-shadow: 1px 1px 3px rgba(0,0,0,0.5);
    }
    .six-info { pointer-events: auto; text-align: left;}
    .six-info .username { font-weight: bold; font-size: 1.1em; }
    .six-actions {
        display: flex; flex-direction: column; gap: 20px;
        pointer-events: auto;
    }
    .six-actions button {
        background: none; border: none; color: white;
        display: flex; flex-direction: column; align-items: center;
        gap: 5px; cursor: pointer; font-size: 13px;
        transition: transform 0.2s ease;
    }
    .six-actions button:active { transform: scale(0.9); }
    .six-actions svg { width: 32px; height: 32px; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5)); }
    #volume-toggle {
        position: absolute; top: 73px; right: 20px; z-index: 100;
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
    .content-spacer { height: 80px; }
    .follow-stats a { color: var(--text-muted); }
    .follow-stats a:hover { text-decoration: underline; }
    .follow-stats strong { color: var(--text-color); }
{% endblock %}

{% block content %}
    {% if active_tab != 'sixs' %}
    <div style="padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div style="width: 80px; height: 80px; flex-shrink: 0;">
                {% if user.pfp_filename %}
                    <img src="{{ url_for('static', filename='uploads/' + user.pfp_filename) }}" alt="Foto de perfil de {{ user.username }}" style="width:80px; height:80px; border-radius:50%; object-fit: cover;">
                {% else %}
                    <div style="width: 80px; height: 80px; border-radius:50%; background: {{ user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-size: 2.5rem; font-weight:bold;">
                        {{ user.username[0]|upper }}
                    </div>
                {% endif %}
            </div>
            <div style="text-align: right;">
            {% if current_user != user %}
                {% if not current_user.is_following(user) %} <a href="{{ url_for('follow', username=user.username) }}" class="btn">Seguir</a>
                {% else %} <a href="{{ url_for('unfollow', username=user.username) }}" class="btn btn-outline">Seguindo</a> {% endif %}
            {% endif %}
            </div>
        </div>
        <h2 style="margin: 12px 0 0 0;">{{ user.username }}</h2>
        <p style="color: var(--text-muted); margin: 4px 0 12px 0;">{{ user.bio or "Sem biografia ainda." }}</p>
        <div class="follow-stats" style="display:flex; gap: 16px;">
            <a href="{{ url_for('follow_list', username=user.username, list_type='followers') }}"><strong>{{ user.followers.count() }}</strong> Seguidores</a>
            <a href="{{ url_for('follow_list', username=user.username, list_type='following') }}"><strong>{{ user.followed.count() }}</strong> Seguindo</a>
        </div>
    </div>
    {% endif %}

    <div class="feed-nav" style="display: flex; border-bottom: 1px solid var(--border-color); {% if active_tab == 'sixs' %} position: fixed; top:0; left:0; right:0; z-index:100; background:rgba(0,0,0,0.65); backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px); {% endif %}">
        {% set tabs = [('Publicações', 'publicações', url_for('profile', username=user.username, tab='publicações')), ('Sixs', 'sixs', url_for('profile', username=user.username, tab='sixs')), ('Republicações', 'republicações', url_for('profile', username=user.username, tab='republicações'))] %}
        {% for name, tab_id, url in tabs %}
        <a href="{{ url }}" style="flex:1; text-align:center; padding: 15px; color: {% if active_tab == tab_id %}var(--text-color){% else %}var(--text-muted){% endif %}; font-weight:bold; position:relative;">{{ name }} {% if active_tab == tab_id %}<span style="position:absolute; bottom:0; left:0; right:0; height:4px; background:var(--accent-color); border-radius:2px;"></span>{% endif %}</a>
        {% endfor %}
    </div>

    {% if active_tab == 'sixs' %}
        <div id="sixs-feed-container">
            <div id="unmute-prompt">Toque para ativar o som</div>
            <button id="volume-toggle">{{ ICONS.volume_off|safe }}</button>
            {% for post in posts %}
                {% include 'six_slide.html' %}
            {% else %}
            <section class="six-video-slide" style="flex-direction:column; text-align:center; color:white;">
                <a href="{{ url_for('profile', username=user.username, tab='publicações') }}" style="position: absolute; top: 73px; left: 20px; z-index: 100; pointer-events: auto; color: white; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.5));">
                        {{ ICONS.back_arrow|safe }}
                </a>
                <div style="padding-top: 53px;">
                    <h4>Nenhum Six ainda.</h4>
                    <p style="color:#aaa;">Este usuário não publicou nenhum Six.</p>
                </div>
            </section>
            {% endfor %}
        </div>
    {% elif active_tab == 'republicações' %}
        {% for repost in reposts %}
            <div style="border-bottom: 1px solid var(--border-color); padding: 12px 16px;">
                <div style="color: var(--text-muted); margin-bottom: 8px; font-size: 0.9em; display:flex; align-items:center; gap: 8px;">
                    {{ ICONS.repost|safe }}
                    <a href="{{ url_for('profile', username=repost.reposter.username) }}">{{ repost.reposter.username }}</a> republicou
                </div>
                 {% if repost.caption %}
                    <p style="margin: 4px 0 12px 0; padding-left: 20px; border-left: 2px solid var(--border-color);">{{ repost.caption }}</p>
                {% endif %}
                
                {% if repost.original_post %}
                    {% with post=repost.original_post %}
                    {% if post.post_type == 'six' %}
                        {% include 'post_card_six.html' %}
                    {% else %}
                         <a href="{{ url_for('view_post', post_id=post.id) }}" style="text-decoration:none; color:inherit; display:block; border: 1px solid var(--border-color); border-radius: 16px; padding: 12px; margin-top: 8px;">
                            <div style="display:flex; gap:12px;">
                                <div style="width:40px; height:40px; flex-shrink:0;">
                                    {% if post.author.pfp_filename %}<img src="{{ url_for('static', filename='uploads/' + post.author.pfp_filename) }}" alt="PFP" style="width:40px; height:40px; border-radius:50%; object-fit: cover;">
                                    {% else %}<div style="width:40px; height:40px; border-radius:50%; background:{{ post.author.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">{{ post.author.username[0]|upper }}</div>{% endif %}
                                </div>
                                <div style="flex-grow:1;">
                                    <div><strong style="color:var(--text-color);">{{ post.author.username }}</strong><span style="color:var(--text-muted); font-size:0.9em;"> · {{ post.timestamp|sao_paulo_time }}</span></div>
                                    <div style="margin: 4px 0 12px 0; white-space: pre-wrap; word-wrap: break-word;">{{ post.text_content }}</div>
                                    {% if post.image_filename %}<img src="{{ url_for('static', filename='uploads/' + post.image_filename) }}" style="width:100%; border-radius:16px; border: 1px solid var(--border-color);">{% endif %}
                                </div>
                            </div>
                        </a>
                    {% endif %}
                    {% endwith %}

                {% elif repost.original_comment %}
                    {# This block now handles the original post's context #}
                    {% with comment=repost.original_comment %}
                    <div style="margin-top: 8px;">
                        <a href="javascript:openCommentModal({{ comment.post_id }}, {{ comment.id }})" style="text-decoration:none; color:inherit; display:block;">
                            {% include 'comment_card.html' %}
                        </a>
                        {# Now show the original post context below the comment #}
                        {% with post=comment.post %}
                            <div style="padding-left: 30px; margin-top: 8px;">
                            {% if post.post_type == 'six' %}
                                {% include 'post_card_six.html' %}
                            {% else %}
                                <a href="{{ url_for('view_post', post_id=post.id) }}" style="text-decoration:none; color:inherit; display:block; border: 1px solid var(--border-color); border-radius: 16px; padding: 8px; font-size: 0.9em;">
                                    <div><strong style="color:var(--text-color);">@{{ post.author.username }}</strong></div>
                                    <div style="color:var(--text-muted);">{{ post.text_content|truncate(100) }}</div>
                                </a>
                            {% endif %}
                            </div>
                        {% endwith %}
                    </div>
                    {% endwith %}
                {% endif %}
            </div>
        {% else %}
            <p style="text-align:center; color:var(--text-muted); padding:40px;">Nenhum item republicado ainda.</p>
        {% endfor %}
        <div class="content-spacer"></div>
    {% else %}
        {% for post in posts %}
            {% include 'post_card_text.html' %}
        {% else %}
            <p style="text-align:center; color:var(--text-muted); padding:40px;">Nenhuma publicação nesta seção.</p>
        {% endfor %}
        <div class="content-spacer"></div>
    {% endif %}
{% endblock %}

{% block scripts %}
{% if active_tab == 'sixs' %}
<script>
    const container = document.getElementById('sixs-feed-container');
    const allVideos = Array.from(container.querySelectorAll('.six-video'));
    const volumeToggle = document.getElementById('volume-toggle');
    const unmutePrompt = document.getElementById('unmute-prompt');
    
    let isMuted = true;
    let hasInteracted = false;
    
    if(allVideos.length > 0) {
        volumeToggle.style.display = 'block';
    }
    
    allVideos.forEach(video => {
        video.addEventListener('canplaythrough', () => {
            video.classList.add('loaded');
        });
    });

    function setMutedState(shouldMute) {
        isMuted = shouldMute;
        allVideos.forEach(v => v.muted = isMuted);
        volumeToggle.innerHTML = isMuted ? ICONS.volume_off : ICONS.volume_on;
        const currentVideo = document.querySelector('.is-visible video');
        if (currentVideo) {
            currentVideo.muted = isMuted;
        }
    }

    volumeToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        hasInteracted = true;
        unmutePrompt.style.display = 'none';
        setMutedState(!isMuted);
    });
    
    container.addEventListener('click', () => {
        if (!hasInteracted && allVideos.length > 0) {
            hasInteracted = true;
            unmutePrompt.style.display = 'none';
            setMutedState(false);
        }
    }, { once: true });

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const slide = entry.target;
            const video = slide.querySelector('video');
            if (!video) return;
            
            if (entry.isIntersecting && entry.intersectionRatio >= 0.7) {
                slide.classList.add('is-visible');
                video.muted = isMuted;
                const playPromise = video.play();
                if (playPromise !== undefined) {
                    playPromise.catch(error => {
                        if (!hasInteracted) unmutePrompt.style.display = 'block';
                    });
                }
            } else { 
                slide.classList.remove('is-visible');
                video.pause(); 
                video.currentTime = 0;
            }
        });
    }, { threshold: 0.7 });

    document.querySelectorAll('.six-video-slide').forEach(slide => {
      observer.observe(slide);
    });

    // New logic to handle scrolling to a specific Six
    document.addEventListener('DOMContentLoaded', () => {
        const urlParams = new URLSearchParams(window.location.search);
        const scrollToId = urlParams.get('scrollTo');
        if (scrollToId) {
            const targetElement = document.getElementById(`post-${scrollToId}`);
            if (targetElement) {
                // Use a timeout to ensure the browser has rendered everything before scrolling
                setTimeout(() => {
                    targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 100);
            }
        }
    });
</script>
{% endif %}
{% endblock %}
""",
"discover.html": """
{% extends "layout.html" %}
{% block title %}Descobrir{% endblock %}
{% block header_title %}Descobrir{% endblock %}
{% block content %}
    <div style="padding: 16px; border-bottom: 1px solid var(--border-color);">
        <form method="GET" action="{{ url_for('discover') }}">
            <div style="display: flex; gap: 8px;">
                <input type="search" name="q" placeholder="Buscar por usuários..." class="form-group comment-input-style" style="margin:0; flex-grow:1;" value="{{ request.args.get('q', '') }}">
                <button type="submit" class="btn">{{ ICONS.discover|safe }}</button>
            </div>
        </form>
    </div>
    
    {% if users is defined and users %}
        <h4 style="padding: 16px 16px 0 16px;">Resultados para '{{ request.args.get('q', '') }}'</h4>
        {% for user in users %}
        <div style="border-bottom: 1px solid var(--border-color); padding:12px 16px; display:flex; align-items:center; gap:12px;">
            <div style="width: 40px; height: 40px; flex-shrink:0;">
                <a href="{{ url_for('profile', username=user.username) }}">
                {% if user.pfp_filename %}
                    <img src="{{ url_for('static', filename='uploads/' + user.pfp_filename) }}" alt="Foto de perfil de {{ user.username }}" style="width:40px; height:40px; border-radius:50%; object-fit: cover;">
                {% else %}
                    <div style="width: 40px; height: 40px; border-radius:50%; background: {{ user.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">{{ user.username[0]|upper }}</div>
                {% endif %}
                </a>
            </div>
            <div style="flex-grow:1;">
                <a href="{{ url_for('profile', username=user.username) }}" style="color:var(--text-color); font-weight:bold;">{{ user.username }}</a>
                <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ user.bio|truncate(50) if user.bio else 'Sem biografia.' }}</p>
            </div>
            <div>
                {% if user != current_user %}
                    {% if not current_user.is_following(user) %}
                        <a href="{{ url_for('follow', username=user.username) }}" class="btn">Seguir</a>
                    {% else %}
                        <a href="{{ url_for('unfollow', username=user.username) }}" class="btn btn-outline">Seguindo</a>
                    {% endif %}
                {% endif %}
            </div>
        </div>
        {% endfor %}
    {% elif posts is defined and posts %}
         <h4 style="padding: 16px 16px 0 16px;">Para Você</h4>
         {% for post in posts %}
            {% include 'post_card_text.html' %}
         {% endfor %}
    {% else %}
        <p style="text-align:center; padding: 40px; color: var(--text-muted);">
            {% if request.args.get('q') %}
                Nenhum usuário encontrado.
            {% else %}
                Nenhuma publicação para mostrar. Siga mais pessoas!
            {% endif %}
        </p>
    {% endif %}
    <div class="content-spacer"></div>
{% endblock %}
""",
"follow_list.html": """
{% extends "layout.html" %}
{% block title %}{{ title }}{% endblock %}
{% block header_title %}{{ title }}{% endblock %}
{% block content %}
    <a href="{{ url_for('profile', username=user.username) }}" style="display:flex; align-items: center; padding: 12px 16px; gap: 8px; color: var(--text-color); border-bottom: 1px solid var(--border-color);">{{ ICONS.back_arrow|safe }} Voltar para o Perfil</a>
    {% for u in user_list %}
    <div style="border-bottom: 1px solid var(--border-color); padding:12px 16px; display:flex; align-items:center; gap:12px;">
        <div style="width: 40px; height: 40px; flex-shrink:0;">
            <a href="{{ url_for('profile', username=u.username) }}">
            {% if u.pfp_filename %}
                <img src="{{ url_for('static', filename='uploads/' + u.pfp_filename) }}" alt="Foto de perfil de {{ u.username }}" style="width:40px; height:40px; border-radius:50%; object-fit: cover;">
            {% else %}
                <div style="width: 40px; height: 40px; border-radius:50%; background: {{ u.pfp_gradient }}; display:flex; align-items:center; justify-content:center; font-weight:bold;">{{ u.username[0]|upper }}</div>
            {% endif %}
            </a>
        </div>
        <div style="flex-grow:1;">
            <a href="{{ url_for('profile', username=u.username) }}" style="color:var(--text-color); font-weight:bold;">{{ u.username }}</a>
            <p style="font-size: 0.9em; color: var(--text-muted); margin: 2px 0;">{{ u.bio|truncate(50) if u.bio else 'Sem biografia.' }}</p>
        </div>
        <div>
            {% if u != current_user %}
                {% if not current_user.is_following(u) %}
                    <a href="{{ url_for('follow', username=u.username) }}" class="btn">Seguir</a>
                {% else %}
                    <a href="{{ url_for('unfollow', username=u.username) }}" class="btn btn-outline">Seguindo</a>
                {% endif %}
            {% endif %}
        </div>
    </div>
    {% else %}
        <p style="text-align:center; padding: 40px; color: var(--text-muted);">Nenhum usuário nesta lista.</p>
    {% endfor %}
    <div class="content-spacer"></div>
{% endblock %}
""",
"auth_form.html": """
{% extends "layout.html" %}
{% block title %}{{ title }}{% endblock %}
{% block header_title %}{{ title }}{% endblock %}
{% block content %}
<div style="padding:16px;">
    <form method="POST">
        <div class="form-group"><label for="username">Nome de usuário</label><input type="text" id="username" name="username" required></div>
        {% if form_type == 'signup' %}<div class="form-group"><label for="bio">Bio (opcional)</label><textarea id="bio" name="bio" rows="3" maxlength="150"></textarea></div>{% endif %}
        <div class="form-group"><label for="password">Senha</label><input type="password" id="password" name="password" required></div>
        <button type="submit" class="btn" style="width:100%; height: 40px;">{{ title }}</button>
    </form>
    <p style="text-align:center; margin-top:20px; color:var(--text-muted);">
        {% if form_type == 'login' %}
            Não tem uma conta? <a href="{{ url_for('signup') }}">Cadastre-se</a>
        {% else %}
            Já tem uma conta? <a href="{{ url_for('login') }}">Entrar</a>
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

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(150))
    pfp_filename = db.Column(db.String(120), nullable=True)
    six_feed_style = db.Column(db.String(20), nullable=False, default='circle') # 'circle' or 'fullscreen'
    
    posts = db.relationship('Post', backref='author', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Post.user_id')
    reposts = db.relationship('Repost', backref='reposter', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Repost.user_id')
    comment_reposts = db.relationship('CommentRepost', backref='reposter', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='CommentRepost.user_id')
    liked_posts = db.relationship('Post', secondary=post_likes, backref=db.backref('liked_by', lazy='dynamic'), lazy='dynamic')
    liked_comments = db.relationship('Comment', secondary=comment_likes, backref=db.backref('liked_by', lazy='dynamic'), lazy='dynamic')
    
    followed = db.relationship(
        'User', 
        secondary=followers, 
        primaryjoin=(followers.c.follower_id == id), 
        secondaryjoin=(followers.c.followed_id == id), 
        backref=db.backref('followers', lazy='dynamic'), 
        lazy='dynamic'
    )
    
    seen_sixs = db.relationship(
        'Post',
        secondary=seen_sixs_posts,
        backref=db.backref('seen_by_six_users', lazy='dynamic'),
        lazy='dynamic'
    )
    seen_texts = db.relationship(
        'Post',
        secondary=seen_text_posts,
        backref=db.backref('seen_by_text_users', lazy='dynamic'),
        lazy='dynamic'
    )

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
    post_type = db.Column(db.String(10), nullable=False) # 'text' or 'six'
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
    user = db.relationship('User', backref='comments')
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic', cascade="all, delete-orphan")
    reposts = db.relationship('CommentRepost', backref='original_comment', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='CommentRepost.comment_id')

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

# --- Funções Helper ---
def add_user_flags_to_posts(posts):
    if not posts or not current_user.is_authenticated:
        return posts
    post_ids = [p.id for p in posts]
    liked_post_ids = {p.id for p in current_user.liked_posts.filter(Post.id.in_(post_ids)).all()}
    reposted_post_ids = {r.post_id for r in current_user.reposts.filter(Repost.post_id.in_(post_ids)).all()}
    for p in posts:
        p.liked_by_current_user = p.id in liked_post_ids
        p.reposted_by_current_user = p.id in reposted_post_ids
    return posts

def format_comment(comment):
    # Pass the raw datetime object to be formatted by the Jinja filter on the client side
    sao_paulo_formatted_time = sao_paulo_time_filter(comment.timestamp)
    return {
        'id': comment.id,
        'text': comment.text,
        'timestamp': sao_paulo_formatted_time,
        'user': {
            'username': comment.user.username,
            'pfp_gradient': comment.user.pfp_gradient,
            'initial': comment.user.username[0].upper(),
            'pfp_filename': comment.user.pfp_filename
        },
        'like_count': comment.liked_by.count(),
        'is_liked_by_user': current_user in comment.liked_by,
        'is_owned_by_user': current_user.is_authenticated and comment.user_id == current_user.id,
        'replies_count': comment.replies.count()
    }
    
@app.after_request
def add_header(response):
    # This disables caching for dynamic pages (HTML)
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
    # For static assets served through Flask, we can set a cache policy
    # Note: A production setup would use a webserver like Nginx to serve static files directly.
    elif request.path.startswith('/static/'):
         response.headers['Cache-Control'] = 'public, max-age=31536000' # Cache for 1 year
    return response

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(basedir, 'static'), filename)

# --- ROTAS ---
@app.route('/post/<int:post_id>')
@login_required
def view_post(post_id):
    post = Post.query.options(selectinload(Post.author)).get_or_404(post_id)
    add_user_flags_to_posts([post])
    return render_template('view_post.html', post=post)



@app.route('/post/<int:post_id>/context')
@login_required
def get_post_context(post_id):
    post = Post.query.options(selectinload(Post.author)).get_or_404(post_id)
    add_user_flags_to_posts([post])
    
    if post.post_type == 'six':
        # Render the Six card for context
        template_name = 'post_card_six.html'
    else:
        # Render the text post card for context
        template_name = 'post_card_text.html'
        
    html = render_template(template_name, post=post)
    return jsonify({'html': html})

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    
    # Eagerly load the list of followed users to avoid multiple queries
    followed_users = current_user.followed.all()
    followed_ids = [u.id for u in followed_users]
    followed_ids.append(current_user.id)
    
    post_type_filter = 'text' if feed_type == 'text' else 'six'
    seen_table = seen_text_posts if feed_type == 'text' else seen_sixs_posts

    # Eager load authors to prevent N+1 queries in the template
    base_query = Post.query.options(selectinload(Post.author)).filter(
        Post.user_id.in_(followed_ids),
        Post.post_type == post_type_filter
    )
    
    seen_ids_subquery = db.session.query(seen_table.c.post_id).filter_by(user_id=current_user.id)
    
    # Perform two queries to get seen and unseen posts
    unseen_posts = base_query.filter(not_(Post.id.in_(seen_ids_subquery))).order_by(Post.timestamp.desc()).all()
    seen_posts = base_query.filter(Post.id.in_(seen_ids_subquery)).order_by(Post.timestamp.desc()).all()
    
    # Combine lists and fetch interaction data in one go
    all_posts = unseen_posts + seen_posts
    add_user_flags_to_posts(all_posts)

    return render_template('home.html', unseen_posts=unseen_posts, seen_posts=seen_posts, feed_type=feed_type)

@app.route('/profile/<username>')
@login_required
def profile(username):
    # Get the user. We can't use selectinload on the self-referential followers/followed,
    # but the .count() method on the dynamic relationship is already efficient.
    user = User.query.filter_by(username=username).first_or_404()

    active_tab = request.args.get('tab', 'publicações')
    posts = []
    reposts_data = []

    if active_tab == 'republicações':
        # Eager load related data to avoid N+1 queries
        post_reposts = user.reposts.options(selectinload(Repost.original_post).selectinload(Post.author)).order_by(Repost.timestamp.desc()).all()
        comment_reposts = user.comment_reposts.options(selectinload(CommentRepost.original_comment).selectinload(Comment.user)).order_by(CommentRepost.timestamp.desc()).all()
        reposts_data = sorted(post_reposts + comment_reposts, key=lambda r: r.timestamp, reverse=True)
        original_posts = [r.original_post for r in post_reposts if r.original_post]
        add_user_flags_to_posts(original_posts)

    else:
        post_type_filter = 'six' if active_tab == 'sixs' else 'text'
        # Eager load author for each post
        posts = user.posts.options(selectinload(Post.author)).filter(Post.post_type == post_type_filter).order_by(Post.timestamp.desc()).all()
        add_user_flags_to_posts(posts)
        
    return render_template('profile.html', user=user, posts=posts, reposts=reposts_data, active_tab=active_tab)

@app.route('/profile/<username>/<list_type>')
@login_required
def follow_list(username, list_type):
    user = User.query.filter_by(username=username).first_or_404()
    if list_type == 'followers':
        user_list = user.followers.all()
        title = "Seguidores"
    elif list_type == 'following':
        user_list = user.followed.all()
        title = "Seguindo"
    else:
        return redirect(url_for('profile', username=username))
    return render_template('follow_list.html', user=user, user_list=user_list, title=title)


@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        video_file = request.files.get('video_file')
        if not video_file or not allowed_file(video_file.filename, 'video'):
            flash('Arquivo de vídeo inválido ou não enviado.', 'error')
            return redirect(url_for('create_post'))

        # Process and save video
        temp_filename = secure_filename(f"temp_six_{current_user.id}_{int(datetime.datetime.now().timestamp())}")
        final_filename = f"six_{current_user.id}_{int(datetime.datetime.now().timestamp())}.mp4" # Standardize to mp4
        
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
        
        video_file.save(temp_path)
        
        process_video(temp_path, final_path)
        
        # Clean up temporary file
        os.remove(temp_path)

        post = Post(
            post_type='six',
            text_content=request.form.get('caption', ''),
            video_filename=final_filename,
            author=current_user
        )
        db.session.add(post)
        db.session.commit()
        
        flash('Six publicado com sucesso!', 'success')
        # Redirect back to the home sixs feed with a cache-busting param
        return redirect(url_for('home', feed_type='sixs', _t=int(datetime.datetime.now().timestamp())))
        
    return render_template('create_post.html')

@app.route('/create_text_post', methods=['POST'])
@login_required
def create_text_post():
    text = request.form.get('text_content')
    if not text or not text.strip():
        flash('O conteúdo da publicação não pode estar vazio.', 'error')
        return redirect(url_for('home'))

    image_file = request.files.get('image')
    final_filename = None

    if image_file and image_file.filename != '':
        if not allowed_file(image_file.filename, 'image'):
            flash('Tipo de arquivo de imagem inválido.', 'error')
            return redirect(url_for('home'))
            
        temp_filename = secure_filename(f"temp_img_{current_user.id}_{int(datetime.datetime.now().timestamp())}")
        final_filename = f"img_{current_user.id}_{int(datetime.datetime.now().timestamp())}.jpg" # Standardize to jpg for consistency
        
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
        
        image_file.save(temp_path)
        
        process_image(temp_path, final_path)
        
        # Clean up temporary file
        os.remove(temp_path)

    post = Post(post_type='text', text_content=text, image_filename=final_filename, author=current_user)
    db.session.add(post)
    db.session.commit()
    flash('Publicação criada!', 'success')
    return redirect(url_for('home', feed_type='text'))

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403

    # Safely try to delete associated files
    if post.image_filename:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename))
        except OSError as e:
            print(f"Error deleting image file {post.image_filename}: {e}")
    if post.video_filename:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], post.video_filename))
        except OSError as e:
            print(f"Error deleting video file {post.video_filename}: {e}")

    db.session.delete(post)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Publicação deletada com sucesso.'})

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Permissão negada.'}), 403
    
    db.session.delete(comment)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Comentário deletado.'})

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
    if not text: return jsonify({'error': 'O texto do comentário é obrigatório'}), 400
    
    parent_comment = None
    if parent_id:
        parent_comment = Comment.query.get(parent_id)
        if not parent_comment or parent_comment.post_id != post_id:
            return jsonify({'error': 'Comentário pai inválido'}), 400
            
    comment = Comment(text=text, user_id=current_user.id, post_id=post_id, parent_id=parent_id)
    db.session.add(comment); db.session.commit()
    return jsonify({'success': True}), 201

@app.route('/like/post/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    if current_user in post.liked_by:
        post.liked_by.remove(current_user)
        liked = False
    else:
        post.liked_by.append(current_user)
        liked = True
    db.session.commit()
    return jsonify({'liked': liked, 'likes': post.liked_by.count()})

@app.route('/like/comment/<int:comment_id>', methods=['POST'])
@login_required
def like_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if current_user in comment.liked_by:
        comment.liked_by.remove(current_user)
        liked = False
    else:
        comment.liked_by.append(current_user)
        liked = True
    db.session.commit()
    return jsonify({'liked': liked, 'likes': comment.liked_by.count()})

@app.route('/repost/post/<int:post_id>', methods=['POST'])
@login_required
def repost_post(post_id):
    post = Post.query.get_or_404(post_id)
    caption = request.json.get('caption', '').strip() or None
    existing_repost = Repost.query.filter_by(user_id=current_user.id, post_id=post.id).first()
    
    if existing_repost:
        db.session.delete(existing_repost)
        message = "Republicação removida."
        reposted = False
    else:
        new_repost = Repost(user_id=current_user.id, post_id=post.id, caption=caption)
        db.session.add(new_repost)
        reposted = True
        message = "Republicado com sucesso!"
    db.session.commit()
    return jsonify({'success': True, 'reposted': reposted, 'message': message})

@app.route('/repost/comment/<int:comment_id>', methods=['POST'])
@login_required
def repost_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    caption = request.json.get('caption', '').strip() or None
    existing_repost = CommentRepost.query.filter_by(user_id=current_user.id, comment_id=comment.id).first()
    if existing_repost:
        db.session.delete(existing_repost)
        message = "Republicação de comentário removida."
        reposted = False
    else:
        new_repost = CommentRepost(user_id=current_user.id, comment_id=comment.id, caption=caption)
        db.session.add(new_repost)
        message = "Comentário republicado!"
        reposted = True
    db.session.commit()
    return jsonify({'success': True, 'reposted': reposted, 'message': message})

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        pfp_file = request.files.get('pfp')
        if pfp_file and pfp_file.filename != '' and allowed_file(pfp_file.filename):
            if current_user.pfp_filename:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.pfp_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            ext = os.path.splitext(pfp_file.filename)[1].lower()
            filename = secure_filename(f"pfp_{current_user.id}_{int(datetime.datetime.now().timestamp())}{ext}")
            pfp_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.pfp_filename = filename

        new_username = request.form.get('username', '').strip()
        new_bio = request.form.get('bio', current_user.bio).strip()
        if new_username and new_username != current_user.username:
            existing_user = User.query.filter(func.lower(User.username) == func.lower(new_username), User.id != current_user.id).first()
            if existing_user:
                flash('Nome de usuário já está em uso.', 'error')
                return redirect(url_for('edit_profile'))
            current_user.username = new_username
        current_user.bio = new_bio
        
        # Salvar a nova preferência de feed
        new_feed_style = request.form.get('six_feed_style')
        if new_feed_style in ['circle', 'fullscreen']:
            current_user.six_feed_style = new_feed_style

        db.session.commit()
        flash('Perfil atualizado!', 'success')
        return redirect(url_for('profile', username=current_user.username))
        
    return render_template('edit_profile.html')

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    if not current_user.check_password(current_password):
        flash('Sua senha atual está incorreta.', 'error')
    elif len(new_password) < 6:
        flash('A nova senha deve ter pelo menos 6 caracteres.', 'error')
    else:
        current_user.set_password(new_password)
        db.session.commit()
        flash('Sua senha foi alterada com sucesso!', 'success')
    return redirect(url_for('edit_profile'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    if not current_user.check_password(request.form.get('password')):
        flash('Senha incorreta. A conta não foi deletada.', 'error')
        return redirect(url_for('edit_profile'))
    user_id = current_user.id
    logout_user()
    user = User.query.get(user_id)
    if user:
        if user.pfp_filename:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], user.pfp_filename))
            except OSError: pass
        db.session.delete(user)
        db.session.commit()
    flash('Sua conta foi permanentemente deletada.', 'success')
    return redirect(url_for('login'))

@app.route('/discover')
@login_required
def discover():
    query = request.args.get('q')
    if query:
        search_term = f"%{query}%"
        users = User.query.filter(User.username.ilike(search_term), User.id != current_user.id).all()
        return render_template('discover.html', users=users)
    else:
        followed_ids = [u.id for u in current_user.followed]
        followed_ids.append(current_user.id)

        popular_posts = Post.query\
            .join(post_likes, Post.id == post_likes.c.post_id)\
            .filter(Post.post_type == 'text')\
            .filter(not_(Post.user_id.in_(followed_ids)))\
            .group_by(Post.id)\
            .having(func.count(post_likes.c.user_id) > 0)\
            .order_by(func.count(post_likes.c.user_id).desc(), Post.timestamp.desc())\
            .limit(30).all()
        
        add_user_flags_to_posts(popular_posts)
        return render_template('discover.html', posts=popular_posts)

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: 
        current_user.follow(user)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user != current_user: 
        current_user.unfollow(user)
        db.session.commit()
    return redirect(request.referrer or url_for('home'))

@app.route('/mark_six_as_seen/<int:post_id>', methods=['POST'])
@login_required
def mark_six_as_seen(post_id):
    # Use raw SQL for performance and to avoid race conditions
    stmt = text("""
        INSERT INTO seen_sixs_posts (user_id, post_id)
        VALUES (:user_id, :post_id)
        ON CONFLICT(user_id, post_id) DO NOTHING
    """)
    db.session.execute(stmt, {'user_id': current_user.id, 'post_id': post_id})
    db.session.commit()
    return jsonify({'success': True}), 200

@app.route('/mark_text_post_as_seen/<int:post_id>', methods=['POST'])
@login_required
def mark_text_post_as_seen(post_id):
    stmt = text("""
        INSERT INTO seen_text_posts (user_id, post_id)
        VALUES (:user_id, :post_id)
        ON CONFLICT(user_id, post_id) DO NOTHING
    """)
    db.session.execute(stmt, {'user_id': current_user.id, 'post_id': post_id})
    db.session.commit()
    return jsonify({'success': True}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter(func.lower(User.username) == func.lower(request.form['username'])).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True)
            return redirect(url_for('home'))
        flash('Nome de usuário ou senha inválidos.', 'error')
    return render_template('auth_form.html', title="Entrar", form_type="login")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        if User.query.filter(func.lower(User.username) == func.lower(username)).first():
            flash('Nome de usuário já existe.', 'error')
            return redirect(url_for('signup'))
        new_user = User(username=username, bio=request.form.get('bio', ''))
        new_user.set_password(request.form['password'])
        db.session.add(new_user); db.session.commit()
        flash('Conta criada! Por favor, faça login.', 'success')
        return redirect(url_for('login'))
    return render_template('auth_form.html', title="Cadastrar", form_type="signup")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado.', 'success')
    return redirect(url_for('login'))

@app.route('/clear-cache', methods=['POST'])
@login_required
def clear_cache():
    try:
        shutil.rmtree(app.config['CACHE_DIR'])
        os.makedirs(app.config['CACHE_DIR'], exist_ok=True)
        flash('O cache do servidor foi limpo com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao limpar o cache: {e}', 'error')
    return redirect(url_for('edit_profile'))


def check_and_upgrade_db():
    """Verifica o esquema do DB e adiciona colunas ausentes sem perda de dados."""
    engine = db.get_engine()
    with engine.connect() as connection:
        from sqlalchemy import inspect, text, exc
        
        inspector = inspect(engine)
        table_name = 'user'
        
        if inspector.has_table(table_name):
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            
            # --- Adicionar coluna 'six_feed_style' ---
            if 'six_feed_style' not in columns:
                print(f"INFO: Coluna 'six_feed_style' não encontrada na tabela '{table_name}'. Adicionando...")
                try:
                    # O 'str' no default é importante para o SQL
                    # Using a transactional block for safety
                    with connection.begin():
                        connection.execute(text("ALTER TABLE user ADD COLUMN six_feed_style VARCHAR(20) NOT NULL DEFAULT 'circle'"))
                    print("INFO: Coluna 'six_feed_style' adicionada com sucesso.")
                except (exc.OperationalError, exc.SQLAlchemyError) as e:
                    print(f"ERRO: Falha ao adicionar a coluna 'six_feed_style': {e}")
                    # Para cenários complexos, Flask-Migrate é recomendado.


# --- EXECUÇÃO PRINCIPAL ---
if __name__ == '__main__':
    with app.app_context():
        # Ensure upload and cache directories exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['CACHE_DIR'], exist_ok=True)
        db.create_all()
        check_and_upgrade_db() # Executa a verificação/atualização aqui

    app.run(debug=True, host='0.0.0.0', port=8000)
