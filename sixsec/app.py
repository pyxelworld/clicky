import os
import datetime
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required

# --- APP CONFIGURATION ---
app = Flask(__name__)
# IMPORTANT: Change this secret key in a real application!
app.config['SECRET_KEY'] = 'a-very-secret-key-for-sixsec'
# Setup database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sixsec.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')

# --- INITIALIZE EXTENSIONS ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect to login page if user is not authenticated

# --- DATABASE MODELS ---
# Association table for the many-to-many relationship (followers)
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
    
    posts = db.relationship('Post', backref='author', lazy='dynamic', foreign_keys='Post.user_id')
    reposts = db.relationship('Post', secondary='reposts', backref=db.backref('reposted_by', lazy='dynamic'), lazy='dynamic')
    
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0
            
    def followed_posts(self, post_type):
        followed = Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)).filter(
                followers.c.follower_id == self.id)
        own = Post.query.filter_by(user_id=self.id)
        all_posts = followed.union(own)
        if post_type:
            all_posts = all_posts.filter_by(post_type=post_type)
        return all_posts.order_by(Post.timestamp.desc())

reposts = db.Table('reposts',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)

likes = db.Table('likes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(10), nullable=False) # 'text' or 'six'
    text_content = db.Column(db.String(150)) # For text posts or video captions
    video_filename = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    original_post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True) # For reposts
    
    comments = db.relationship('Comment', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    liked_by = db.relationship('User', secondary=likes, backref=db.backref('liked_posts', lazy='dynamic'), lazy='dynamic')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))


# --- LOGIN MANAGER ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- TEMPLATES ---
# We store HTML templates as strings in a dictionary
# This keeps everything in one file, as requested.

templates = {
"layout.html": """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>{% block title %}Sixsec{% endblock %}</title>
    <style>
        :root { --primary-color: #008080; --secondary-color: #f4f4f4; --font-color: #333; --white: #fff; --border-color: #ddd; --hover-color: #006666; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; background-color: var(--secondary-color); color: var(--font-color); }
        .container { max-width: 600px; margin: 0 auto; padding: 15px; }
        nav { background: var(--primary-color); color: var(--white); padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; }
        nav a { color: var(--white); text-decoration: none; font-weight: bold; padding: 8px 15px; }
        nav a:hover { text-decoration: underline; }
        .logo { font-size: 1.5em; }
        .flash { padding: 1em; margin-bottom: 1em; border: 1px solid transparent; border-radius: .25rem; }
        .flash-success { color: #155724; background-color: #d4edda; border-color: #c3e6cb; }
        .flash-error { color: #721c24; background-color: #f8d7da; border-color: #f5c6cb; }
        .post-card { background: var(--white); border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 20px; padding: 15px; }
        .post-header { display: flex; align-items: center; margin-bottom: 10px; }
        .post-header img { width: 40px; height: 40px; border-radius: 50%; margin-right: 10px; object-fit: cover; }
        .post-header a { text-decoration: none; color: var(--font-color); font-weight: bold; }
        .post-content p { white-space: pre-wrap; word-wrap: break-word; }
        .post-actions { display: flex; justify-content: space-around; padding-top: 10px; border-top: 1px solid var(--border-color); }
        .post-actions button, .post-actions a { background: none; border: none; cursor: pointer; color: #555; font-size: 1.2em; text-decoration: none; }
        .post-actions .liked { color: red; }
        .btn { background-color: var(--primary-color); color: var(--white); padding: 10px 15px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }
        .btn:hover { background-color: var(--hover-color); }
        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; margin-bottom: .5rem; }
        .form-group input, .form-group textarea { width: 100%; padding: .5rem; border: 1px solid var(--border-color); border-radius: 4px; box-sizing: border-box; }
        /* Mobile specific styles */
        @media (max-width: 600px) { body { margin-bottom: 60px; } .mobile-nav { position: fixed; bottom: 0; left: 0; right: 0; background: var(--white); border-top: 1px solid var(--border-color); display: flex; justify-content: space-around; padding: 10px 0; z-index: 1000; } .mobile-nav a { color: var(--primary-color); font-size: 1.5em; } }
        @media (min-width: 601px) { .mobile-nav { display: none; } }
    </style>
    {% block head %}{% endblock %}
</head>
<body>
    <nav>
        <a href="{{ url_for('home') }}" class="logo">Sixsec</a>
        <div>
        {% if current_user.is_authenticated %}
            <a href="{{ url_for('home') }}">Home</a>
            <a href="{{ url_for('discover') }}">Discover</a>
            <a href="{{ url_for('create_post') }}">Create</a>
            <a href="{{ url_for('profile', username=current_user.username) }}">Profile</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
            <a href="{{ url_for('login') }}">Login</a>
            <a href="{{ url_for('signup') }}">Sign Up</a>
        {% endif %}
        </div>
    </nav>
    
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>

    {% if current_user.is_authenticated %}
    <div class="mobile-nav">
        <a href="{{ url_for('home') }}">🏠</a>
        <a href="{{ url_for('discover') }}">🔍</a>
        <a href="{{ url_for('create_post') }}">➕</a>
        <a href="{{ url_for('profile', username=current_user.username) }}">👤</a>
    </div>
    {% endif %}
    
    <script>
    // Simple script for handling likes without page reload
    function handleLike(postId) {
        fetch(`/like/${postId}`, { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                const likeButton = document.getElementById(`like-btn-${postId}`);
                const likeCount = document.getElementById(`like-count-${postId}`);
                likeCount.innerText = data.likes;
                if (data.liked) {
                    likeButton.classList.add('liked');
                } else {
                    likeButton.classList.remove('liked');
                }
            });
    }
    </script>
</body>
</html>
""",

"home.html": """
{% extends "layout.html" %}
{% block title %}Home - Sixsec{% endblock %}
{% block head %}
<style>
    .feed-nav { display: flex; justify-content: center; margin-bottom: 20px; background: #fff; padding: 10px; border-radius: 8px; border: 1px solid var(--border-color); }
    .feed-nav a { padding: 10px 20px; text-decoration: none; color: var(--primary-color); font-weight: bold; border-radius: 20px; }
    .feed-nav a.active { background-color: var(--primary-color); color: var(--white); }
    /* TikTok-like feed for Sixs */
    .sixs-feed-container { display: none; flex-direction: column; align-items: center; }
    .six-video-card { width: 100%; height: 80vh; max-height: 700px; background: #000; border-radius: 12px; margin-bottom: 20px; position: relative; scroll-snap-align: start; }
    .six-video { width: 100%; height: 100%; object-fit: cover; border-radius: 12px; clip-path: circle(40% at 50% 50%); }
    .six-info { position: absolute; bottom: 20px; left: 20px; color: white; text-shadow: 1px 1px 3px rgba(0,0,0,0.7); }
    @media (max-width: 600px) {
        .feed-container { padding-bottom: 60px; }
        #text-feed-container { display: {% if feed_type == 'text' %}block{% else %}none{% endif %}; }
        #sixs-feed-container { display: {% if feed_type == 'six' %}flex{% else %}none{% endif %}; scroll-snap-type: y mandatory; overflow-y: scroll; height: calc(100vh - 120px); }
    }
    @media (min-width: 601px) {
        .feed-container { display: block; }
        #sixs-feed-container { display: {% if feed_type == 'six' %}flex{% else %}none{% endif %}; }
    }
    .end-of-feed { text-align: center; padding: 40px; color: #777; }
</style>
{% endblock %}
{% block content %}
    <h1>Home</h1>
    <div class="feed-nav">
        <a href="{{ url_for('home', feed_type='text') }}" class="{% if feed_type == 'text' %}active{% endif %}">Text</a>
        <a href="{{ url_for('home', feed_type='six') }}" class="{% if feed_type == 'six' %}active{% endif %}">Sixs</a>
    </div>

    <div id="text-feed-container" class="feed-container">
        {% if feed_type == 'text' %}
            {% for post in posts %}
                {% include 'post_card.html' %}
            {% else %}
                <p>No text posts from people you follow yet. Check out the <a href="{{ url_for('discover') }}">Discover</a> page!</p>
            {% endfor %}
        {% endif %}
    </div>

    <div id="sixs-feed-container" class="sixs-feed-container">
        {% if feed_type == 'six' %}
            {% for post in posts %}
                <div class="six-video-card">
                    <video class="six-video" src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" loop autoplay muted playsinline></video>
                    <div class="six-info">
                        <a href="{{ url_for('profile', username=post.author.username) }}" style="color:white; text-decoration: none;"><strong>@{{ post.author.username }}</strong></a>
                        <p>{{ post.text_content }}</p>
                    </div>
                </div>
            {% else %}
                <div class="end-of-feed">
                    <h3>Nothing new to see here!</h3>
                    <p>Follow more creators or <a href="{{ url_for('create_post') }}">create something new!</a></p>
                </div>
            {% endfor %}
            {% if posts %}
            <div class="end-of-feed">
                <h3>You've seen all new Sixs!</h3>
                <p>Scroll up to re-watch or create your own.</p>
            </div>
            {% endif %}
        {% endif %}
    </div>
{% endblock %}
""",

"post_card.html": """
<div class="post-card" id="post-{{ post.id }}">
    <div class="post-header">
        <img src="{{ url_for('static', filename='uploads/profiles/' + post.author.profile_pic) }}" alt="{{ post.author.username }}'s profile picture">
        <div>
            <a href="{{ url_for('profile', username=post.author.username) }}">{{ post.author.username }}</a>
            <small style="color:#888;">· {{ post.timestamp.strftime('%b %d') }}</small>
            {% if post.original_post_id %}
                <small style="color:#888;"><i>(reposted by {{ post.reposted_by.first().username }})</i></small>
            {% endif %}
        </div>
    </div>
    <div class="post-content">
        <p>{{ post.text_content }}</p>
        {% if post.post_type == 'six' and post.video_filename %}
             <video controls style="width: 100%; border-radius: 8px; clip-path: circle(40% at 50% 50%); max-height: 400px; background-color: black;">
                <source src="{{ url_for('static', filename='uploads/' + post.video_filename) }}" type="video/mp4">
                Your browser does not support the video tag.
            </video>
        {% endif %}
    </div>
    <div class="post-actions">
        <button title="Like" onclick="handleLike({{ post.id }})" id="like-btn-{{ post.id }}" class="{{ 'liked' if current_user in post.liked_by else '' }}">
            ❤️ <span id="like-count-{{ post.id }}">{{ post.liked_by.count() }}</span>
        </button>
        <button title="Comment">💬 {{ post.comments.count() }}</button>
        <a href="{{ url_for('repost', post_id=post.id) }}" title="Repost">🔁</a>
    </div>
</div>
""",

"discover.html": """
{% extends "layout.html" %}
{% block title %}Discover - Sixsec{% endblock %}
{% block content %}
    <h1>Discover</h1>
    <p>Find new accounts and content to follow.</p>
    {% for item in discover_items %}
        {% if item.type == 'post' %}
            {% set post = item.content %}
            {% include 'post_card.html' %}
        {% elif item.type == 'user' %}
            {% set user = item.content %}
            <div class="post-card">
                <div class="post-header">
                     <img src="{{ url_for('static', filename='uploads/profiles/' + user.profile_pic) }}" alt="{{ user.username }}'s profile picture">
                     <div>
                        <a href="{{ url_for('profile', username=user.username) }}"><strong>{{ user.username }}</strong></a>
                        <p style="margin: 4px 0; color: #555;">{{ user.bio or 'No bio yet.' }}</p>
                     </div>
                     <div style="margin-left: auto;">
                        {% if not current_user.is_following(user) %}
                        <a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>
                        {% else %}
                        <span style="color: #777;">Following</span>
                        {% endif %}
                     </div>
                </div>
            </div>
        {% endif %}
    {% else %}
        <p>Nothing to discover right now. Be the first to <a href="{{ url_for('create_post') }}">create a post</a>!</p>
    {% endfor %}
{% endblock %}
""",

"create_post.html": """
{% extends "layout.html" %}
{% block title %}Create - Sixsec{% endblock %}
{% block head %}
<style>
    #video-preview-container { display: none; margin-top: 15px; }
    #video-preview { max-width: 100%; border-radius: 8px; clip-path: circle(40% at 50% 50%); background: black; }
</style>
{% endblock %}
{% block content %}
    <h1>Sixs Creator</h1>
    <form method="POST" enctype="multipart/form-data">
        <div class="form-group">
            <label for="post_type">What do you want to post?</label>
            <select id="post_type" name="post_type" onchange="toggleForm()" class="form-group input">
                <option value="text">Text (150 chars)</option>
                <option value="six">Six (6s video)</option>
            </select>
        </div>

        <div id="text-form">
            <div class="form-group">
                <label for="text_content">Your text:</label>
                <textarea name="text_content" id="text_content" rows="4" maxlength="150" placeholder="What's happening?"></textarea>
            </div>
        </div>

        <div id="six-form" style="display:none;">
            <div class="form-group">
                <label for="video_file">Upload your 6-second video:</label>
                <input type="file" id="video_file" name="video_file" accept="video/mp4,video/webm" onchange="previewVideo(this)">
                <small>Max 6 seconds. MP4 or WebM format.</small>
            </div>
            <div id="video-preview-container">
                <video id="video-preview" controls></video>
            </div>
            <div class="form-group">
                <label for="caption">Caption (50 chars max):</label>
                <input type="text" name="caption" maxlength="50" placeholder="Add a caption...">
            </div>
        </div>
        
        <button type="submit" class="btn">Post</button>
    </form>

<script>
    function toggleForm() {
        const postType = document.getElementById('post_type').value;
        const textForm = document.getElementById('text-form');
        const sixForm = document.getElementById('six-form');
        if (postType === 'text') {
            textForm.style.display = 'block';
            sixForm.style.display = 'none';
        } else {
            textForm.style.display = 'none';
            sixForm.style.display = 'block';
        }
    }
    
    function previewVideo(input) {
        const videoPreviewContainer = document.getElementById('video-preview-container');
        const videoPreview = document.getElementById('video-preview');
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function (e) {
                videoPreview.src = e.target.result;
                videoPreviewContainer.style.display = 'block';
                videoPreview.onloadedmetadata = function() {
                    if (videoPreview.duration > 6.5) { // a little buffer
                        alert("Video is longer than 6 seconds! Please choose a shorter one.");
                        input.value = ""; // Clear the file input
                        videoPreviewContainer.style.display = 'none';
                    }
                };
            }
            reader.readAsDataURL(input.files[0]);
        }
    }
    // Initial call
    toggleForm();
</script>
{% endblock %}
""",

"profile.html": """
{% extends "layout.html" %}
{% block title %}{{ user.username }}'s Profile{% endblock %}
{% block head %}
<style>
    .profile-header { display: flex; align-items: flex-start; margin-bottom: 20px; }
    .profile-pic { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; margin-right: 20px; }
    .profile-info { flex-grow: 1; }
    .profile-stats { display: flex; gap: 20px; margin-top: 10px; }
    .profile-actions { margin-left: auto; }
</style>
{% endblock %}
{% block content %}
    <div class="profile-header">
        <img class="profile-pic" src="{{ url_for('static', filename='uploads/profiles/' + user.profile_pic) }}" alt="Profile picture">
        <div class="profile-info">
            <h2>{{ user.username }}</h2>
            <p>{{ user.bio or "This user hasn't set a bio yet." }}</p>
            <div class="profile-stats">
                <span><strong>{{ user.posts.count() }}</strong> Posts</span>
                <span><strong>{{ user.followers.count() }}</strong> Followers</span>
                <span><strong>{{ user.followed.count() }}</strong> Following</span>
            </div>
        </div>
        <div class="profile-actions">
            {% if current_user.is_authenticated and current_user != user %}
                {% if not current_user.is_following(user) %}
                    <a href="{{ url_for('follow', username=user.username) }}" class="btn">Follow</a>
                {% else %}
                    <a href="{{ url_for('unfollow', username=user.username) }}" class="btn" style="background-color:#ccc; color:#333;">Unfollow</a>
                {% endif %}
            {% elif current_user == user %}
                 <a href="{{ url_for('edit_profile') }}" class="btn">Edit Profile</a>
            {% endif %}
        </div>
    </div>
    
    <div class="feed-nav">
        <a href="{{ url_for('profile', username=user.username, feed='all') }}" class="{% if feed_type == 'all' %}active{% endif %}">All</a>
        <a href="{{ url_for('profile', username=user.username, feed='texts') }}" class="{% if feed_type == 'texts' %}active{% endif %}">Texts</a>
        <a href="{{ url_for('profile', username=user.username, feed='sixs') }}" class="{% if feed_type == 'sixs' %}active{% endif %}">Sixs</a>
        <a href="{{ url_for('profile', username=user.username, feed='reposts') }}" class="{% if feed_type == 'reposts' %}active{% endif %}">Reposts</a>
    </div>

    <div>
        {% for post in posts %}
            {% include 'post_card.html' %}
        {% else %}
            <p>No posts to show here yet.</p>
        {% endfor %}
    </div>
{% endblock %}
""",

"auth_form.html": """
{% extends "layout.html" %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
    <div style="max-width: 400px; margin: 2rem auto; padding: 2rem; background: var(--white); border-radius: 8px; border: 1px solid var(--border-color);">
        <h2>{{ title }}</h2>
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
            <div class="form-group">
                <label for="profile_pic">Profile Picture (optional)</label>
                <input type="file" id="profile_pic" name="profile_pic" accept="image/png, image/jpeg, image/gif">
            </div>
            {% endif %}
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn">{{ title }}</button>
        </form>
        <p style="margin-top: 1rem;">
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

# --- ROUTES ---

@app.route('/')
@login_required
def home():
    feed_type = request.args.get('feed_type', 'text')
    if feed_type == 'text':
        posts = current_user.followed_posts('text').all()
    elif feed_type == 'six':
        posts = current_user.followed_posts('six').all()
    else:
        posts = []
    
    session['last_seen_posts'] = [p.id for p in posts] # Store seen posts
    
    return render_template_string(templates['home.html'], posts=posts, feed_type=feed_type)

@app.route('/discover')
@login_required
def discover():
    # A simple discovery algorithm: recent posts from users you don't follow, plus some random users
    followed_ids = [u.id for u in current_user.followed]
    followed_ids.append(current_user.id)
    
    recent_posts = Post.query.filter(Post.user_id.notin_(followed_ids)).order_by(Post.timestamp.desc()).limit(10).all()
    random_users = User.query.filter(User.id.notin_(followed_ids)).order_by(db.func.random()).limit(5).all()
    
    discover_items = []
    for post in recent_posts:
        discover_items.append({'type': 'post', 'content': post})
    for user in random_users:
        discover_items.append({'type': 'user', 'content': user})
    
    # Simple shuffle
    import random
    random.shuffle(discover_items)

    return render_template_string(templates['discover.html'], discover_items=discover_items)

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        post_type = request.form.get('post_type')

        if post_type == 'text':
            content = request.form.get('text_content')
            if not content or len(content) > 150:
                flash('Text must be between 1 and 150 characters.', 'error')
                return redirect(url_for('create_post'))
            post = Post(post_type='text', text_content=content, author=current_user)
        
        elif post_type == 'six':
            video_file = request.files.get('video_file')
            caption = request.form.get('caption')
            if not video_file:
                flash('You must upload a video for a Six post.', 'error')
                return redirect(url_for('create_post'))
            
            # Simple security check for filename
            from werkzeug.utils import secure_filename
            filename = secure_filename(video_file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            video_file.save(video_path)
            
            # Here you would add server-side validation for video length (requires a library like moviepy or ffmpeg-python)
            # For this demo, we rely on the client-side check.

            post = Post(post_type='six', text_content=caption, video_filename=filename, author=current_user)
        
        else:
            flash('Invalid post type.', 'error')
            return redirect(url_for('create_post'))
        
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('home'))

    return render_template_string(templates['create_post.html'])

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    feed_type = request.args.get('feed', 'all')
    
    if feed_type == 'texts':
        posts = user.posts.filter_by(post_type='text').order_by(Post.timestamp.desc()).all()
    elif feed_type == 'sixs':
        posts = user.posts.filter_by(post_type='six').order_by(Post.timestamp.desc()).all()
    elif feed_type == 'reposts':
        posts = user.reposts.order_by(Post.timestamp.desc()).all()
    else: # 'all'
        posts = user.posts.order_by(Post.timestamp.desc()).all() # This shows original posts and reposts made by the user
    
    return render_template_string(templates['profile.html'], user=user, posts=posts, feed_type=feed_type)
    
@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.bio = request.form.get('bio', current_user.bio)
        profile_pic = request.files.get('profile_pic')
        if profile_pic:
            from werkzeug.utils import secure_filename
            filename = secure_filename(profile_pic.filename)
            pic_path = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles', filename)
            profile_pic.save(pic_path)
            current_user.profile_pic = filename
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile', username=current_user.username))

    return render_template_string(templates['auth_form.html'], title="Edit Profile", form_type='signup', user=current_user)


# --- ACTIONS (Follow, Like, Repost) ---

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(f'User {username} not found.', 'error')
        return redirect(url_for('home'))
    if user == current_user:
        flash('You cannot follow yourself!', 'error')
        return redirect(url_for('profile', username=username))
    current_user.follow(user)
    db.session.commit()
    flash(f'You are now following {username}!', 'success')
    return redirect(url_for('profile', username=username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(f'User {username} not found.', 'error')
        return redirect(url_for('home'))
    if user == current_user:
        flash('You cannot unfollow yourself!', 'error')
        return redirect(url_for('profile', username=username))
    current_user.unfollow(user)
    db.session.commit()
    flash(f'You have unfollowed {username}.', 'success')
    return redirect(url_for('profile', username=username))

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

@app.route('/repost/<int:post_id>')
@login_required
def repost(post_id):
    post_to_repost = Post.query.get_or_404(post_id)
    if post_to_repost.author == current_user:
        flash("You can't repost your own post.", "error")
        return redirect(request.referrer or url_for('home'))
    
    # To keep it simple, we just link to the user's reposts.
    # A more complex system might create a new 'post' entry of type 'repost'
    current_user.reposts.append(post_to_repost)
    db.session.commit()
    flash("Post reposted!", "success")
    return redirect(request.referrer or url_for('home'))


# --- AUTHENTICATION ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('login'))
        login_user(user, remember=True)
        return redirect(url_for('home'))
    return render_template_string(templates['auth_form.html'], title="Login", form_type="login")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        bio = request.form.get('bio')
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return redirect(url_for('signup'))
        
        new_user = User(username=username, bio=bio)
        new_user.set_password(password)

        profile_pic = request.files.get('profile_pic')
        if profile_pic:
            from werkzeug.utils import secure_filename
            filename = secure_filename(profile_pic.filename)
            pic_path = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles', filename)
            profile_pic.save(pic_path)
            new_user.profile_pic = filename
        
        db.session.add(new_user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template_string(templates['auth_form.html'], title="Sign Up", form_type="signup")

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # Create necessary folders and the database if they don't exist
    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        if not os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')):
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'))
        db.create_all()
    app.run(debug=True)