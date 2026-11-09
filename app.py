import os
import re
import secrets
import unicodedata
import time
import hmac
import hashlib
from collections import defaultdict, deque
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask, Blueprint, render_template, request, redirect,
    url_for, flash, session, abort, g
)
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from models import (
    db, Application, AdminUser, ContactMessage, FAQItem,
    Room, GalleryImage, SiteSettings,
)


# ==================================================================
# APP + CONFIG
# ==================================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
SECRET_KEY_FILE = os.path.join(INSTANCE_DIR, "secret.key")

os.makedirs(INSTANCE_DIR, exist_ok=True)


def _load_or_create_secret_key():
    """
    Load SECRET_KEY from env var if set, otherwise from instance/secret.key.
    If neither exists, generate a strong random key and persist it.
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    if os.path.isfile(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_urlsafe(64)
    with open(SECRET_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key)
    print(f"[bootstrap] Generated new SECRET_KEY and saved to {SECRET_KEY_FILE}")
    return key


app = Flask(__name__)
app.config.update(
    SECRET_KEY=_load_or_create_secret_key(),
    WTF_CSRF_ENABLED=True,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,

    SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(INSTANCE_DIR, "hostel.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_ROOT=os.path.join(BASE_DIR, "static", "uploads"),

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,   # set True only when served over HTTPS
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,   # 8 hours

    # Rate limits
    RATE_LIMIT_CONTACT     = (5, 60 * 60),   # 5 per hour
    RATE_LIMIT_ADMISSION   = (3, 60 * 60),   # 3 per hour
    RATE_LIMIT_ADMIN_LOGIN = (10, 15 * 60),  # 10 per 15 min
)

os.makedirs(os.path.join(app.config["UPLOAD_ROOT"], "applications"), exist_ok=True)
os.makedirs(os.path.join(app.config["UPLOAD_ROOT"], "gallery"), exist_ok=True)

db.init_app(app)
csrf = CSRFProtect(app)

# Trust X-Forwarded-* headers if behind a reverse proxy (harmless otherwise)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


# ==================================================================
# SECURITY HEADERS
# ==================================================================
@app.after_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    # Baseline CSP — allows Google Fonts + inline styles needed by current templates
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


# ==================================================================
# RATE LIMITING (in-memory, per-process)
# ==================================================================
_rl_store: dict = defaultdict(deque)
_rl_lock_owner = object()   # sentinel; we rely on GIL for tiny critical sections


def _client_key(scope: str) -> str:
    ip = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if not ip:
        ip = request.remote_addr or "unknown"
    return f"{scope}:{ip}"


def rate_limited(scope: str, limit_config_key: str):
    """
    Decorator. Usage:
        @rate_limited("contact", "RATE_LIMIT_CONTACT")
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            limit, window = app.config[limit_config_key]
            key = _client_key(scope)
            now = time.time()
            q = _rl_store[key]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                retry_after = int(q[0] + window - now) + 1
                resp = app.make_response(
                    render_template(
                        "errors/429.html",
                        retry_after=retry_after,
                        scope=scope,
                    ) if _template_exists("errors/429.html")
                    else ("<h1>429 — Too many requests</h1>"
                          "<p>Please wait and try again.</p>", 429)
                )
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry_after)
                return resp
            q.append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def _template_exists(name: str) -> bool:
    try:
        app.jinja_env.get_template(name)
        return True
    except Exception:
        return False


# ==================================================================
# UPLOAD HELPERS
# ==================================================================
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOC_EXTS   = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_DOC_SIZE       = 5 * 1024 * 1024
MAX_DOC_COUNT      = 3

_MAGIC = {
    b"\xFF\xD8\xFF":       "jpg",
    b"\x89PNG\r\n\x1A\n":  "png",
    b"RIFF":               "webp",
    b"%PDF":               "pdf",
}


def _detect_magic(head: bytes) -> str:
    for sig, kind in _MAGIC.items():
        if head.startswith(sig):
            if kind == "webp":
                return "webp" if head[8:12] == b"WEBP" else "unknown"
            return kind
    return "unknown"


def _safe_filename(original: str) -> str:
    name = unicodedata.normalize("NFKD", original or "")
    name = name.encode("ascii", "ignore").decode("ascii")
    name = os.path.basename(name)
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-._")
    return name or "file"


def save_upload(file_storage, target_dir: str, allowed_exts: set,
                max_size: int = MAX_DOC_SIZE) -> str:
    if not file_storage or not file_storage.filename:
        raise ValueError("Empty file")

    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in allowed_exts:
        raise ValueError(f"File type '{ext}' is not allowed")

    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    kind = _detect_magic(head)
    if kind == "unknown":
        raise ValueError("File contents do not match a valid file type")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size == 0:
        raise ValueError("File is empty")
    if size > max_size:
        raise ValueError(f"File exceeds {max_size // (1024*1024)} MB limit")

    safe_name = _safe_filename(file_storage.filename)
    stem, ext = os.path.splitext(safe_name)
    unique = f"{stem}-{secrets.token_hex(4)}{ext}"

    os.makedirs(target_dir, exist_ok=True)
    dest = os.path.join(target_dir, unique)
    file_storage.stream.seek(0)
    file_storage.save(dest)
    return unique


# ==================================================================
# HELPERS
# ==================================================================
def generate_reference():
    for _ in range(8):
        ref = "BBH-{}-{}".format(
            datetime.utcnow().strftime("%y%m"),
            secrets.token_hex(3).upper(),
        )
        if not Application.query.filter_by(reference=ref).first():
            return ref
    raise RuntimeError("Could not generate unique reference")


def flash_errors(errors):
    for e in errors:
        flash(e, "error")


def validate_application(form):
    errors = []
    f = {k: (v or "").strip() for k, v in form.items()}

    if len(f.get("full_name", "")) < 3:
        errors.append("Full name is required (min 3 characters).")
    if len(f.get("father_name", "")) < 3:
        errors.append("Father's name is required (min 3 characters).")

    try:
        dob = datetime.strptime(f.get("date_of_birth", ""), "%Y-%m-%d").date()
        age = (date.today() - dob).days / 365.25
        if age < 10 or age > 80:
            errors.append("Please check the date of birth.")
    except ValueError:
        errors.append("Please select a valid date of birth.")

    cnic_digits = "".join(c for c in f.get("cnic", "") if c.isdigit())
    if len(cnic_digits) < 13:
        errors.append("CNIC / B-Form must contain at least 13 digits.")

    phone_digits = "".join(c for c in f.get("phone", "") if c.isdigit())
    if not (10 <= len(phone_digits) <= 15):
        errors.append("Please enter a valid phone number.")

    for key, label, minimum in [
        ("institution_name", "Institution name", 2),
        ("class_degree", "Class / degree", 1),
        ("institution_location", "Institution location", 2),
        ("guardian_name", "Guardian name", 3),
        ("guardian_address", "Address", 5),
    ]:
        if len(f.get(key, "")) < minimum:
            errors.append(f"{label} is required.")

    if not f.get("guardian_relationship"):
        errors.append("Please select a guardian relationship.")

    gcd = "".join(c for c in f.get("guardian_contact", "") if c.isdigit())
    if not (10 <= len(gcd) <= 15):
        errors.append("Guardian contact number is invalid.")

    if not f.get("preferred_room"):
        errors.append("Please select a preferred room type.")

    try:
        joining = datetime.strptime(f.get("expected_joining", ""), "%Y-%m-%d").date()
        if joining < date.today():
            errors.append("Expected joining date cannot be in the past.")
    except ValueError:
        errors.append("Please select a valid joining date.")

    if form.get("privacy_accept") not in ("on", "true", "1", "yes"):
        errors.append("You must accept the privacy statement.")

    dup = Application.query.filter(
        Application.phone == f.get("phone"),
        Application.cnic == f.get("cnic"),
        Application.status != "rejected",
    ).first()
    if dup:
        errors.append(
            f"An active application already exists for this phone/CNIC "
            f"(reference {dup.reference}). Please track that application."
        )

    return errors, f


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin.login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


# ==================================================================
# PUBLIC BLUEPRINT
# ==================================================================
public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def home():
    featured = (
        Room.query
        .filter_by(is_published=True)
        .order_by(Room.sort_order.asc(), Room.id.asc())
        .limit(3)
        .all()
    )
    gallery_preview = (
        GalleryImage.query
        .filter_by(is_published=True)
        .order_by(GalleryImage.sort_order.asc(), GalleryImage.id.desc())
        .limit(6)
        .all()
    )
    return render_template(
        "public/home.html",
        featured_rooms=featured,
        gallery_images=gallery_preview,
    )


@public_bp.route("/about")
def about():
    return render_template("public/about.html")


@public_bp.route("/facilities")
def facilities():
    return render_template("public/facilities.html")


@public_bp.route("/rooms")
def rooms():
    rows = (
        Room.query
        .filter_by(is_published=True)
        .order_by(Room.sort_order.asc(), Room.id.asc())
        .all()
    )
    return render_template("public/rooms_public.html", rooms=rows)


@public_bp.route("/gallery")
def gallery():
    rows = (
        GalleryImage.query
        .filter_by(is_published=True)
        .order_by(GalleryImage.sort_order.asc(), GalleryImage.id.desc())
        .all()
    )
    return render_template("public/gallery.html", gallery_images=rows)


@public_bp.route("/admission", methods=["GET"])
def admission():
    return render_template(
        "public/admission.html",
        available_room_types=[
            {"name": "Single", "capacity": 1},
            {"name": "Double Sharing", "capacity": 2},
            {"name": "Triple Sharing", "capacity": 3},
            {"name": "Any", "capacity": 1},
        ],
        current_date_iso=date.today().isoformat(),
    )


@public_bp.route("/admission/submit", methods=["POST"])
@rate_limited("admission", "RATE_LIMIT_ADMISSION")
def submit_application():
    errors, clean = validate_application(request.form)
    if errors:
        flash_errors(errors)
        return render_template(
            "public/admission.html",
            form_data=clean,
            available_room_types=[
                {"name": "Single", "capacity": 1},
                {"name": "Double Sharing", "capacity": 2},
                {"name": "Triple Sharing", "capacity": 3},
                {"name": "Any", "capacity": 1},
            ],
            current_date_iso=date.today().isoformat(),
        ), 400

    reference = generate_reference()

    saved_files = []
    files = request.files.getlist("documents")
    files = [f for f in files if f and f.filename]
    if files:
        if len(files) > MAX_DOC_COUNT:
            errors.append(f"Maximum {MAX_DOC_COUNT} documents allowed.")
        target_dir = os.path.join(
            app.config["UPLOAD_ROOT"], "applications", reference
        )
        for f in files:
            try:
                saved_name = save_upload(f, target_dir, ALLOWED_DOC_EXTS, MAX_DOC_SIZE)
                saved_files.append(saved_name)
            except ValueError as exc:
                errors.append(f"{f.filename}: {exc}")

    if errors:
        flash_errors(errors)
        return render_template(
            "public/admission.html",
            form_data=clean,
            available_room_types=[
                {"name": "Single", "capacity": 1},
                {"name": "Double Sharing", "capacity": 2},
                {"name": "Triple Sharing", "capacity": 3},
                {"name": "Any", "capacity": 1},
            ],
            current_date_iso=date.today().isoformat(),
        ), 400

    app_obj = Application(
        reference=reference,
        full_name=clean["full_name"],
        father_name=clean["father_name"],
        date_of_birth=datetime.strptime(clean["date_of_birth"], "%Y-%m-%d").date(),
        cnic=clean["cnic"],
        phone=clean["phone"],
        whatsapp=clean.get("whatsapp") or None,
        institution_name=clean["institution_name"],
        class_degree=clean["class_degree"],
        institution_location=clean["institution_location"],
        guardian_name=clean["guardian_name"],
        guardian_contact=clean["guardian_contact"],
        guardian_relationship=clean["guardian_relationship"],
        guardian_address=clean["guardian_address"],
        preferred_room=clean["preferred_room"],
        expected_joining=datetime.strptime(clean["expected_joining"], "%Y-%m-%d").date(),
        monthly_budget=int(clean["monthly_budget"]) if clean.get("monthly_budget") else None,
        additional_requirements=clean.get("additional_requirements") or None,
        documents=",".join(saved_files) if saved_files else None,
        status="submitted",
    )
    db.session.add(app_obj)
    db.session.commit()

    return redirect(url_for("public.application_success", ref=app_obj.reference))


@public_bp.route("/application/success")
def application_success():
    return render_template(
        "public/application_success.html",
        reference_number=request.args.get("ref"),
    )


@public_bp.route("/application/status", methods=["GET", "POST"])
def application_status():
    result = None
    error = None

    if request.method == "POST":
        ref = (request.form.get("reference") or "").strip().upper()
        phone = (request.form.get("phone") or "").strip()

        if not ref or not phone:
            error = "Please enter both your reference number and phone number."
        else:
            app_obj = Application.query.filter_by(reference=ref, phone=phone).first()
            if not app_obj:
                error = "No matching application found. Please check your reference and phone number."
            else:
                result = app_obj

    return render_template(
        "public/application_status.html",
        result=result,
        error=error,
    )


@public_bp.route("/contact", methods=["GET", "POST"])
@rate_limited("contact", "RATE_LIMIT_CONTACT")
def contact():
    success = False
    form_data = {}

    if request.method == "POST":
        form_data = {
            "name":    (request.form.get("name")    or "").strip(),
            "email":   (request.form.get("email")   or "").strip(),
            "phone":   (request.form.get("phone")   or "").strip(),
            "subject": (request.form.get("subject") or "").strip(),
            "message": (request.form.get("message") or "").strip(),
        }
        errors = []
        if len(form_data["name"]) < 2:
            errors.append("Please enter your name.")
        if not form_data["message"] or len(form_data["message"]) < 10:
            errors.append("Please enter a message (at least 10 characters).")
        if not form_data["email"] and not form_data["phone"]:
            errors.append("Please provide an email or phone number so we can reply.")
        if form_data["email"] and ("@" not in form_data["email"] or "." not in form_data["email"]):
            errors.append("Please enter a valid email address.")
        if len(form_data["subject"]) < 2:
            errors.append("Please enter a subject.")

        if errors:
            flash_errors(errors)
        else:
            msg = ContactMessage(
                name=form_data["name"],
                email=form_data["email"] or None,
                phone=form_data["phone"] or None,
                subject=form_data["subject"],
                message=form_data["message"],
            )
            db.session.add(msg)
            db.session.commit()
            success = True
            form_data = {}

    return render_template(
        "public/contact.html",
        success=success,
        form_data=form_data,
    )


@public_bp.route("/faq")
def faq():
    items = (
        FAQItem.query
        .filter_by(is_published=True)
        .order_by(FAQItem.sort_order.asc(), FAQItem.id.asc())
        .all()
    )
    return render_template("public/faq.html", items=items)


app.register_blueprint(public_bp)


# ==================================================================
# ADMIN BLUEPRINT
# ==================================================================
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/login", methods=["GET", "POST"])
@rate_limited("admin_login", "RATE_LIMIT_ADMIN_LOGIN")
def login():
    if session.get("admin_id"):
        return redirect(url_for("admin.dashboard"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "")
        user = AdminUser.query.filter_by(username=username, is_active=True).first()
        if user and user.check_password(password):
            session.clear()
            session.permanent = True
            session["admin_id"] = user.id
            session["admin_username"] = user.username
            return redirect(url_for("admin.dashboard"))
        error = "Invalid username or password."

    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.context_processor
def inject_admin_globals():
    unread = ContactMessage.query.filter_by(is_read=False).count()
    return {"unread_message_count": unread}


@admin_bp.route("/")
@login_required
def dashboard():
    stats = {
        "total":        Application.query.count(),
        "submitted":    Application.query.filter_by(status="submitted").count(),
        "under_review": Application.query.filter_by(status="under_review").count(),
        "approved":     Application.query.filter_by(status="approved").count(),
        "confirmed":    Application.query.filter_by(status="confirmed").count(),
        "rejected":     Application.query.filter_by(status="rejected").count(),
        "unread_msgs":  ContactMessage.query.filter_by(is_read=False).count(),
    }
    recent = Application.query.order_by(Application.id.desc()).limit(5).all()
    return render_template("admin/applications.html",
                          applications=recent,
                          current_filter=None,
                          stats=stats)


@admin_bp.route("/applications")
@login_required
def applications():
    status = request.args.get("status")
    query = Application.query
    if status in Application.STATUSES:
        query = query.filter_by(status=status)
    rows = query.order_by(Application.id.desc()).all()

    stats = {
        "total":        Application.query.count(),
        "submitted":    Application.query.filter_by(status="submitted").count(),
        "under_review": Application.query.filter_by(status="under_review").count(),
        "approved":     Application.query.filter_by(status="approved").count(),
        "confirmed":    Application.query.filter_by(status="confirmed").count(),
        "rejected":     Application.query.filter_by(status="rejected").count(),
    }
    return render_template("admin/applications.html",
                          applications=rows,
                          current_filter=status,
                          stats=stats)


@admin_bp.route("/applications/<int:app_id>")
@login_required
def application_details(app_id):
    application = Application.query.get_or_404(app_id)
    return render_template("admin/application_details.html", application=application)


@admin_bp.route("/applications/<int:app_id>/status", methods=["POST"])
@login_required
def update_status(app_id):
    application = Application.query.get_or_404(app_id)
    new_status = (request.form.get("status") or "").strip()
    if new_status not in Application.STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("admin.application_details", app_id=app_id))
    application.status = new_status
    db.session.commit()
    flash(f"Status updated to “{application.status_label()}”.", "success")
    return redirect(url_for("admin.application_details", app_id=app_id))


@admin_bp.route("/applications/<int:app_id>/notes", methods=["POST"])
@login_required
def update_notes(app_id):
    application = Application.query.get_or_404(app_id)
    application.internal_notes = (request.form.get("internal_notes") or "").strip() or None
    db.session.commit()
    flash("Internal notes saved.", "success")
    return redirect(url_for("admin.application_details", app_id=app_id))


@admin_bp.route("/applications/<int:app_id>/delete", methods=["POST"])
@login_required
def delete_application(app_id):
    application = Application.query.get_or_404(app_id)
    ref = application.reference
    db.session.delete(application)
    db.session.commit()
    flash(f"Application {ref} deleted.", "success")
    return redirect(url_for("admin.applications"))


@admin_bp.route("/messages")
@login_required
def messages():
    rows = ContactMessage.query.order_by(ContactMessage.id.desc()).all()
    unread = ContactMessage.query.filter_by(is_read=False).count()
    return render_template("admin/messages.html", messages=rows, unread_count=unread)


@admin_bp.route("/messages/<int:msg_id>/read", methods=["POST"])
@login_required
def mark_message_read(msg_id):
    msg = ContactMessage.query.get_or_404(msg_id)
    msg.is_read = True
    db.session.commit()
    return redirect(url_for("admin.messages"))


@admin_bp.route("/messages/<int:msg_id>/delete", methods=["POST"])
@login_required
def delete_message(msg_id):
    msg = ContactMessage.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.", "success")
    return redirect(url_for("admin.messages"))


@admin_bp.route("/faqs")
@login_required
def faqs():
    items = FAQItem.query.order_by(FAQItem.sort_order.asc(), FAQItem.id.asc()).all()
    return render_template("admin/faqs.html", items=items)


@admin_bp.route("/faqs/add", methods=["POST"])
@login_required
def add_faq():
    question = (request.form.get("question") or "").strip()
    answer   = (request.form.get("answer") or "").strip()
    try:
        sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0
    if not question or not answer:
        flash("Question and answer are both required.", "error")
        return redirect(url_for("admin.faqs"))
    db.session.add(FAQItem(question=question, answer=answer, sort_order=sort_order))
    db.session.commit()
    flash("FAQ added.", "success")
    return redirect(url_for("admin.faqs"))


@admin_bp.route("/faqs/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_faq(item_id):
    item = FAQItem.query.get_or_404(item_id)
    question = (request.form.get("question") or "").strip()
    answer   = (request.form.get("answer") or "").strip()
    try:
        sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0
    if not question or not answer:
        flash("Question and answer are both required.", "error")
        return redirect(url_for("admin.faqs"))
    item.question = question
    item.answer = answer
    item.sort_order = sort_order
    db.session.commit()
    flash("FAQ updated.", "success")
    return redirect(url_for("admin.faqs"))


@admin_bp.route("/faqs/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_faq(item_id):
    item = FAQItem.query.get_or_404(item_id)
    item.is_published = not item.is_published
    db.session.commit()
    flash(f"FAQ {'published' if item.is_published else 'hidden'}.", "success")
    return redirect(url_for("admin.faqs"))


@admin_bp.route("/faqs/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_faq(item_id):
    item = FAQItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("FAQ deleted.", "success")
    return redirect(url_for("admin.faqs"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
def website_settings():
    if request.method == "POST":
        for key in ("contact_phone", "whatsapp_number", "hero_image"):
            value = (request.form.get(key) or "").strip() or None
            SiteSettings.set(key, value, db.session)
        db.session.commit()
        flash("Website settings saved.", "success")
        return redirect(url_for("admin.website_settings"))

    return render_template("admin/website_settings.html")


@admin_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password") or ""
        new     = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""

        user = AdminUser.query.get(session.get("admin_id"))
        if not user or not user.check_password(current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new != confirm:
            flash("New passwords do not match.", "error")
        else:
            user.set_password(new)
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for("admin.website_settings"))

    return render_template("admin/change_password.html")


# ---------------- Admin: Rooms ----------------
@admin_bp.route("/rooms")
@login_required
def rooms_admin():
    rows = Room.query.order_by(Room.sort_order.asc(), Room.id.asc()).all()
    return render_template("admin/rooms.html", rooms=rows)


@admin_bp.route("/rooms/add", methods=["POST"])
@login_required
def add_room():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Room name is required.", "error")
        return redirect(url_for("admin.rooms_admin"))

    try:
        capacity = max(1, int(request.form.get("capacity") or 1))
        available = max(0, min(capacity, int(request.form.get("available_beds") or 0)))
        fee = request.form.get("monthly_fee")
        fee = int(fee) if fee else None
        sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        flash("Invalid numeric value.", "error")
        return redirect(url_for("admin.rooms_admin"))

    image_name = None
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        try:
            image_name = save_upload(
                image_file,
                os.path.join(app.config["UPLOAD_ROOT"], "gallery"),
                ALLOWED_IMAGE_EXTS,
                MAX_DOC_SIZE,
            )
        except ValueError as exc:
            flash(f"Image upload failed: {exc}", "error")
            return redirect(url_for("admin.rooms_admin"))

    db.session.add(Room(
        name=name,
        description=(request.form.get("description") or "").strip() or None,
        capacity=capacity,
        available_beds=available,
        monthly_fee=fee,
        fee_public=bool(request.form.get("fee_public")),
        image=image_name,
        is_published=bool(request.form.get("is_published")),
        sort_order=sort_order,
    ))
    db.session.commit()
    flash(f"Room “{name}” added.", "success")
    return redirect(url_for("admin.rooms_admin"))


@admin_bp.route("/rooms/<int:room_id>/edit", methods=["POST"])
@login_required
def edit_room(room_id):
    room = Room.query.get_or_404(room_id)
    room.name = (request.form.get("name") or room.name).strip()
    room.description = (request.form.get("description") or "").strip() or None

    try:
        room.capacity = max(1, int(request.form.get("capacity") or room.capacity))
        room.available_beds = max(
            0, min(room.capacity, int(request.form.get("available_beds") or 0))
        )
        fee = request.form.get("monthly_fee")
        room.monthly_fee = int(fee) if fee else None
        room.sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        flash("Invalid numeric value.", "error")
        return redirect(url_for("admin.rooms_admin"))

    room.fee_public = bool(request.form.get("fee_public"))
    room.is_published = bool(request.form.get("is_published"))

    image_file = request.files.get("image")
    if image_file and image_file.filename:
        try:
            room.image = save_upload(
                image_file,
                os.path.join(app.config["UPLOAD_ROOT"], "gallery"),
                ALLOWED_IMAGE_EXTS,
                MAX_DOC_SIZE,
            )
        except ValueError as exc:
            flash(f"Image upload failed: {exc}", "error")
            return redirect(url_for("admin.rooms_admin"))

    db.session.commit()
    flash(f"Room “{room.name}” updated.", "success")
    return redirect(url_for("admin.rooms_admin"))


@admin_bp.route("/rooms/<int:room_id>/delete", methods=["POST"])
@login_required
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    name = room.name
    db.session.delete(room)
    db.session.commit()
    flash(f"Room “{name}” deleted.", "success")
    return redirect(url_for("admin.rooms_admin"))


# ---------------- Admin: Gallery ----------------
@admin_bp.route("/gallery")
@login_required
def gallery_admin():
    rows = GalleryImage.query.order_by(
        GalleryImage.sort_order.asc(), GalleryImage.id.desc()
    ).all()
    return render_template("admin/gallery.html", images=rows)


@admin_bp.route("/gallery/upload", methods=["POST"])
@login_required
def upload_gallery():
    files = request.files.getlist("images")
    files = [f for f in files if f and f.filename]
    if not files:
        flash("No images selected.", "error")
        return redirect(url_for("admin.gallery_admin"))

    caption = (request.form.get("caption") or "").strip() or None
    category = (request.form.get("category") or "").strip() or None

    try:
        sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0

    saved = 0
    errors = []
    for f in files:
        try:
            name = save_upload(
                f,
                os.path.join(app.config["UPLOAD_ROOT"], "gallery"),
                ALLOWED_IMAGE_EXTS,
                MAX_DOC_SIZE,
            )
            db.session.add(GalleryImage(
                filename=name,
                caption=caption,
                category=category,
                sort_order=sort_order,
                is_published=True,
            ))
            saved += 1
        except ValueError as exc:
            errors.append(f"{f.filename}: {exc}")

    db.session.commit()
    if saved:
        flash(f"{saved} image(s) uploaded.", "success")
    if errors:
        flash_errors(errors)
    return redirect(url_for("admin.gallery_admin"))


@admin_bp.route("/gallery/<int:img_id>/toggle", methods=["POST"])
@login_required
def toggle_gallery(img_id):
    img = GalleryImage.query.get_or_404(img_id)
    img.is_published = not img.is_published
    db.session.commit()
    flash(f"Image {'published' if img.is_published else 'hidden'}.", "success")
    return redirect(url_for("admin.gallery_admin"))


@admin_bp.route("/gallery/<int:img_id>/delete", methods=["POST"])
@login_required
def delete_gallery(img_id):
    img = GalleryImage.query.get_or_404(img_id)
    try:
        path = os.path.join(app.config["UPLOAD_ROOT"], "gallery", img.filename)
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
    db.session.delete(img)
    db.session.commit()
    flash("Image deleted.", "success")
    return redirect(url_for("admin.gallery_admin"))


app.register_blueprint(admin_bp)


# ==================================================================
# TEMPLATE CONTEXT + ERROR HANDLERS
# ==================================================================
@app.context_processor
def inject_globals():
    class _Settings:
        contact_phone = SiteSettings.get("contact_phone")
        whatsapp_number = SiteSettings.get("whatsapp_number")
        hero_image = SiteSettings.get("hero_image")
    return {
        "site_settings": _Settings(),
        "current_year": date.today().year,
    }


@app.errorhandler(404)
def not_found(e):
    return render_template("errors/404.html"), 404


@app.errorhandler(500)
def server_error(e):
    # Log the exception in production
    app.logger.exception("500 error: %s", e)
    try:
        return render_template("errors/500.html"), 500
    except Exception:
        return ("<h1>500 — Server error</h1><p><a href='/'>Home</a></p>", 500)


@app.errorhandler(429)
def too_many_requests(e):
    retry_after = getattr(e, "retry_after", 60)
    resp = app.make_response(
        render_template("errors/429.html", retry_after=retry_after)
        if _template_exists("errors/429.html")
        else ("<h1>429 — Too many requests</h1>"
              "<p>Please wait a moment and try again.</p>")
    )
    resp.status_code = 429
    resp.headers["Retry-After"] = str(retry_after)
    return resp


# ==================================================================
# FIRST-RUN BOOTSTRAP
# ==================================================================
with app.app_context():
    db.create_all()

    if not AdminUser.query.filter_by(username="admin").first():
        default = AdminUser(username="admin")
        default.set_password("changeme123")   # ⚠️ change after first login
        db.session.add(default)
        db.session.commit()
        print("[bootstrap] Created default admin: admin / changeme123")

    if FAQItem.query.count() == 0:
        seed_faqs = [
            ("What facilities are provided?",
             "Three meals a day, clean drinking water, Wi-Fi, electricity and a bed for every resident.", 10),
            ("Where is Baloch Boys Hostel located?",
             "The hostel is located in Makli, Thatta, Sindh, Pakistan.", 20),
            ("How do I apply for admission?",
             "Submit the online admission form on our website. You will receive a unique "
             "reference number by which you can track your application.", 30),
            ("Can I track my application status?",
             "Yes. Visit the Track Application page and enter your reference number along with "
             "the phone number you registered with.", 40),
            ("What documents do I need to bring?",
             "Please bring your CNIC or B-Form (student and guardian), your most recent education "
             "documents, and any documents you uploaded with your application. The hostel "
             "administration may request additional documents during review.", 50),
            ("Are the rooms furnished?",
             "Each resident is provided a bed. Please contact the hostel administration for the "
             "current list of what is included in each room type.", 60),
            ("How do I contact the hostel?",
             "Use the Contact page on this website to send a message. The hostel administration "
             "will reply using the contact details you provide.", 70),
            ("What is your admission process?",
             "Submit the online form, receive a reference number, wait for the administration to "
             "review your application, and once approved your admission is confirmed.", 80),
        ]
        for q, a, order in seed_faqs:
            db.session.add(FAQItem(question=q, answer=a, sort_order=order))
        db.session.commit()
        print(f"[bootstrap] Seeded {len(seed_faqs)} FAQ items.")

    for key in ("contact_phone", "whatsapp_number", "hero_image"):
        if not SiteSettings.query.filter_by(key=key).first():
            db.session.add(SiteSettings(key=key, value=None))
    db.session.commit()


if __name__ == "__main__":
    # Dev server only. For production use the waitress command in the guide below.
    app.run(debug=True, port=5000)