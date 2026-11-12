import hashlib
from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import init_db, get_db

app = Flask(__name__)
app.secret_key = 'gat_secret_2026'   # change this in production


# ── Helpers ────────────────────────────────────────────────────────────────

def hash_password(password):
    """Return SHA-256 hex digest of the password."""
    return hashlib.sha256(password.encode()).hexdigest()


def login_required(f):
    """Decorator: redirect to login if user is not in session."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ── Auth Routes ────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Show login form and authenticate user."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()
        conn.close()

        if user and user['password'] == hash_password(password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            error = 'Invalid username or password.'

    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Show registration form and create a new user."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if not username or not password:
            error = 'Username and password are required.'
        elif password != confirm:
            error = 'Passwords do not match.'
        else:
            try:
                conn = get_db()
                conn.execute(
                    'INSERT INTO users (username, password) VALUES (?, ?)',
                    (username, hash_password(password))
                )
                conn.commit()
                conn.close()
                flash('Account created! Please log in.', 'success')
                return redirect(url_for('login'))
            except Exception:
                error = 'Username already exists.'

    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ── App Routes ─────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    """Home screen – list all projects."""
    conn = get_db()
    projects = conn.execute('SELECT * FROM projects ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('index.html', projects=projects)


@app.route('/create_project', methods=['POST'])
@login_required
def create_project():
    """Save a new project name and redirect back to home."""
    project_name = request.form.get('project_name', '').strip()
    if project_name:
        conn = get_db()
        conn.execute('INSERT INTO projects (project_name) VALUES (?)', (project_name,))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
