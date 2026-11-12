import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, g, session
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

DATABASE = os.path.join(os.path.dirname(__file__), "tracker.db")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """
    Return a per-request SQLite connection.
    Opens a fresh connection on first call per request and stores it on g
    so all code within the same request shares one connection.
    teardown_appcontext closes it after the response is sent.
    """
    if not hasattr(g, "_database") or g._database is None:
        g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        g._database.row_factory = sqlite3.Row
        g._database.execute("PRAGMA journal_mode=WAL")
        g._database.execute("PRAGMA synchronous=NORMAL")
    return g._database


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        g._database = None
        db.close()


def init_db():
    """Create tables if they don't already exist."""
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT    NOT NULL UNIQUE,
                password TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name    TEXT    NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS members (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                name       TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                member_id  INTEGER NOT NULL REFERENCES members(id),
                title      TEXT    NOT NULL,
                status     TEXT    NOT NULL DEFAULT 'Pending'
            );
        """)
        # Migrate existing databases: add user_id column if missing
        try:
            db.execute("ALTER TABLE projects ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")
        except Exception:
            pass
        # Add 'deleted' column to existing databases that pre-date this change
        try:
            db.execute("ALTER TABLE projects ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    """Decorator: redirect to login if no session user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth routes – Login / Register / Logout
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        db = get_db()
        user = db.execute(
            "SELECT id, password FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is None or user["password"] != password:
            error = "Invalid username or password."
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = username
            return redirect(url_for("home"))
    return render_template("login.html", error=error, mode="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm  = request.form.get("confirm_password", "").strip()
        if not username or not password:
            error = "Username and password are required."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                error = "Username already taken. Please choose another."
            else:
                db.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, password),
                )
                db.commit()
                user = db.execute(
                    "SELECT id FROM users WHERE username = ?", (username,)
                ).fetchone()
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = username
                return redirect(url_for("home"))
    return render_template("login.html", error=error, mode="register")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Module 1 – Home Screen  (index.html)
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def home():
    db = get_db()
    uid = session["user_id"]
    projects = db.execute(
        "SELECT id, name FROM projects WHERE user_id = ? AND deleted = 0 ORDER BY id DESC",
        (uid,)
    ).fetchall()
    deleted_projects = db.execute(
        "SELECT id, name FROM projects WHERE user_id = ? AND deleted = 1 ORDER BY id DESC",
        (uid,)
    ).fetchall()
    return render_template("index.html", projects=projects, deleted_projects=deleted_projects)


@app.route("/create_project", methods=["POST"])
@login_required
def create_project():
    name = request.form.get("project_name", "").strip()
    if name:
        db = get_db()
        db.execute(
            "INSERT INTO projects (user_id, name) VALUES (?, ?)",
            (session["user_id"], name)
        )
        db.commit()
    return redirect(url_for("home"))


@app.route("/delete_project/<int:project_id>", methods=["POST"])
@login_required
def delete_project(project_id):
    db = get_db()
    db.execute(
        "UPDATE projects SET deleted = 1 WHERE id = ? AND user_id = ?",
        (project_id, session["user_id"])
    )
    db.commit()
    return redirect(url_for("home"))


@app.route("/restore_project/<int:project_id>", methods=["POST"])
@login_required
def restore_project(project_id):
    db = get_db()
    db.execute(
        "UPDATE projects SET deleted = 0 WHERE id = ? AND user_id = ?",
        (project_id, session["user_id"])
    )
    db.commit()
    return redirect(url_for("home"))


@app.route("/delete_project_permanent/<int:project_id>", methods=["POST"])
@login_required
def delete_project_permanent(project_id):
    db = get_db()
    # Verify ownership before deleting
    project = db.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, session["user_id"])
    ).fetchone()
    if project:
        db.execute("DELETE FROM tasks   WHERE project_id = ?", (project_id,))
        db.execute("DELETE FROM members WHERE project_id = ?", (project_id,))
        db.execute("DELETE FROM projects WHERE id = ?",        (project_id,))
        db.commit()
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# Module 2 – Project Workspace  (project_detail.html)
# ---------------------------------------------------------------------------

@app.route("/project/<int:project_id>")
@login_required
def project_detail(project_id):
    db = get_db()

    # Guard: reject soft-deleted, non-existent, or other user's projects
    project = db.execute(
        "SELECT id, name FROM projects WHERE id = ? AND deleted = 0 AND user_id = ?",
        (project_id, session["user_id"])
    ).fetchone()

    if project is None:
        return redirect(url_for("home"))

    members = db.execute(
        "SELECT id, name FROM members WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()

    # Join tasks with member name for display
    tasks = db.execute(
        """
        SELECT t.id, t.title, t.status, m.name AS member_name
        FROM   tasks   t
        JOIN   members m ON m.id = t.member_id
        WHERE  t.project_id = ?
        ORDER  BY t.id
        """,
        (project_id,),
    ).fetchall()

    return render_template(
        "project_detail.html",
        project=project,
        members=members,
        tasks=tasks,
    )


@app.route("/project/<int:project_id>/add_member", methods=["POST"])
@login_required
def add_member(project_id):
    name = request.form.get("member_name", "").strip()
    if name:
        db = get_db()
        db.execute(
            "INSERT INTO members (project_id, name) VALUES (?, ?)",
            (project_id, name),
        )
        db.commit()
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/project/<int:project_id>/delete_member/<int:member_id>", methods=["POST"])
@login_required
def delete_member(project_id, member_id):
    db = get_db()
    # Remove tasks assigned to this member in this project first
    db.execute(
        "DELETE FROM tasks WHERE member_id = ? AND project_id = ?",
        (member_id, project_id),
    )
    db.execute(
        "DELETE FROM members WHERE id = ? AND project_id = ?",
        (member_id, project_id),
    )
    db.commit()
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/project/<int:project_id>/assign_task", methods=["POST"])
@login_required
def assign_task(project_id):
    title     = request.form.get("task_title", "").strip()
    member_id = request.form.get("member_id", "").strip()

    if title and member_id:
        db = get_db()
        db.execute(
            "INSERT INTO tasks (project_id, member_id, title, status) VALUES (?, ?, ?, 'Pending')",
            (project_id, int(member_id), title),
        )
        db.commit()
    return redirect(url_for("project_detail", project_id=project_id))


@app.route("/task/<int:task_id>/complete", methods=["POST"])
@login_required
def complete_task(task_id):
    db = get_db()

    # Retrieve project_id before updating so we can redirect back
    row = db.execute(
        "SELECT project_id FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()

    if row:
        db.execute(
            "UPDATE tasks SET status = 'Completed' WHERE id = ?", (task_id,)
        )
        db.commit()
        return redirect(url_for("project_detail", project_id=row["project_id"]))

    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# Module 3 – Contribution Summary  (summary.html)
# ---------------------------------------------------------------------------

@app.route("/project/<int:project_id>/summary")
@login_required
def summary(project_id):
    db = get_db()

    project = db.execute(
        "SELECT id, name FROM projects WHERE id = ? AND deleted = 0 AND user_id = ?",
        (project_id, session["user_id"])
    ).fetchone()

    if project is None:
        return redirect(url_for("home"))

    # Per-member contribution (matches spec SQL)
    contributions = db.execute(
        """
        SELECT m.name,
               COUNT(t.id)                                              AS assigned,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) AS completed
        FROM   members m
        LEFT JOIN tasks t ON t.member_id = m.id AND t.project_id = m.project_id
        WHERE  m.project_id = ?
        GROUP  BY m.id, m.name
        ORDER  BY m.name
        """,
        (project_id,),
    ).fetchall()

    # Overall project totals
    totals = db.execute(
        """
        SELECT COUNT(*)                                                 AS total,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END)   AS completed
        FROM   tasks
        WHERE  project_id = ?
        """,
        (project_id,),
    ).fetchone()

    total_tasks     = totals["total"]     or 0
    total_completed = totals["completed"] or 0
    overall_pct     = int(total_completed / total_tasks * 100) if total_tasks > 0 else 0

    return render_template(
        "summary.html",
        project=project,
        contributions=contributions,
        total_tasks=total_tasks,
        total_completed=total_completed,
        overall_pct=overall_pct,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
