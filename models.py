"""
Baloch Boys Hostel — minimal data models for Stage 6.
Covers: Application (admission submissions) and AdminUser (login for Stage 8).
Room, GalleryImage, SiteSettings arrive in Stage 9.
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ----------------------------------------------------------------
# Application — one row per submitted admission form
# ----------------------------------------------------------------
class Application(db.Model):
    __tablename__ = "applications"

    id = db.Column(db.Integer, primary_key=True)

    # Public reference — format BBH-YYMM-XXXXXX
    reference = db.Column(db.String(24), unique=True, nullable=False, index=True)

    # Step 1 — Student
    full_name        = db.Column(db.String(120), nullable=False)
    father_name      = db.Column(db.String(120), nullable=False)
    date_of_birth    = db.Column(db.Date, nullable=False)
    cnic             = db.Column(db.String(20), nullable=False)
    phone            = db.Column(db.String(20), nullable=False, index=True)
    whatsapp         = db.Column(db.String(20), nullable=True)

    # Step 2 — Education
    institution_name     = db.Column(db.String(200), nullable=False)
    class_degree         = db.Column(db.String(100), nullable=False)
    institution_location = db.Column(db.String(160), nullable=False)

    # Step 3 — Guardian
    guardian_name         = db.Column(db.String(120), nullable=False)
    guardian_contact      = db.Column(db.String(20), nullable=False)
    guardian_relationship = db.Column(db.String(40), nullable=False)
    guardian_address      = db.Column(db.Text, nullable=False)

    # Step 4 — Accommodation
    preferred_room          = db.Column(db.String(80), nullable=False)
    expected_joining        = db.Column(db.Date, nullable=False)
    monthly_budget          = db.Column(db.Integer, nullable=True)
    additional_requirements = db.Column(db.Text, nullable=True)

    # Lifecycle
    STATUSES = ("submitted", "under_review", "approved", "rejected", "confirmed")
    status = db.Column(db.String(20), nullable=False, default="submitted", index=True)

    # Internal — never shown to applicants
    internal_notes = db.Column(db.Text, nullable=True)

    # Documents: comma-separated relative filenames under
    # static/uploads/applications/<reference>/
    documents = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                          onupdate=datetime.utcnow, nullable=False)

    def status_label(self):
        return {
            "submitted":    "Application Submitted",
            "under_review": "Under Review",
            "approved":     "Approved",
            "rejected":     "Rejected",
            "confirmed":    "Admission Confirmed",
        }.get(self.status, "Submitted")

    def __repr__(self):
        return f"<Application {self.reference} {self.full_name}>"


# ----------------------------------------------------------------
# AdminUser — minimal auth for admin pages (Stage 8 expands UI)
# ----------------------------------------------------------------
class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def __repr__(self):
        return f"<AdminUser {self.username}>"
    # ----------------------------------------------------------------
# ContactMessage — contact form submissions
# ----------------------------------------------------------------
class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name    = db.Column(db.String(120), nullable=False)
    email   = db.Column(db.String(160), nullable=True)
    phone   = db.Column(db.String(20),  nullable=True)
    subject = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text,        nullable=False)

    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ContactMessage {self.id} {self.subject[:40]}>"


# ----------------------------------------------------------------
# FAQItem — editable frequently asked questions
# ----------------------------------------------------------------
class FAQItem(db.Model):
    __tablename__ = "faq_items"

    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(300), nullable=False)
    answer   = db.Column(db.Text,        nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False, index=True)
    is_published = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<FAQItem {self.id} {self.question[:40]}>"

    # ----------------------------------------------------------------
# Room — public accommodation info (no occupant details ever)
# ----------------------------------------------------------------
class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=True)

    capacity = db.Column(db.Integer, nullable=False, default=1)
    available_beds = db.Column(db.Integer, nullable=False, default=0)

    monthly_fee = db.Column(db.Integer, nullable=True)
    fee_public = db.Column(db.Boolean, default=False, nullable=False)

    image = db.Column(db.String(200), nullable=True)  # filename in static/uploads/gallery/
    is_published = db.Column(db.Boolean, default=True, nullable=False, index=True)

    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def is_available(self):
        return (self.available_beds or 0) > 0

    def __repr__(self):
        return f"<Room {self.name} {self.available_beds}/{self.capacity}>"


# ----------------------------------------------------------------
# GalleryImage — admin-managed photos
# ----------------------------------------------------------------
class GalleryImage(db.Model):
    __tablename__ = "gallery_images"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    caption = db.Column(db.String(200), nullable=True)
    category = db.Column(db.String(40), nullable=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_published = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<GalleryImage {self.filename}>"


# ----------------------------------------------------------------
# SiteSettings — key/value config
# ----------------------------------------------------------------
class SiteSettings(db.Model):
    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                          onupdate=datetime.utcnow, nullable=False)

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key, value, session):
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            row = cls(key=key, value=value)
            session.add(row)
        return row

    def __repr__(self):
        return f"<SiteSettings {self.key}={self.value!r}>"