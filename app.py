import os
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session


# Load environment variables from .env if present
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
DB_DIR = os.path.join(BASE_DIR, "db")
DB_PATH = os.path.join(DB_DIR, "app.db")
ALLOWED_EXTENSIONS = {"pdf"}

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# --- SQLAlchemy setup ---
DATABASE_URI = "sqlite:///" + DB_PATH
engine = create_engine(
    DATABASE_URI,
    connect_args={"check_same_thread": False},
)
Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    upload_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    pages = relationship("Page", back_populates="document", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)
    document = relationship("Document", back_populates="pages")


Base.metadata.create_all(engine)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf_local(file_path: str) -> List[str]:
    from pypdf import PdfReader

    pages_text: List[str] = []
    reader = PdfReader(file_path)
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages_text.append(text.strip())
    return pages_text


def extract_text_via_mistral_ocr(file_path: str) -> Optional[List[str]]:
    # Stub for phase 3 (OCR). Return None to fall back to local extraction.
    return None


def save_document_and_pages(filename: str, pages_text: List[str]) -> int:
    session = SessionLocal()
    try:
        document = Document(filename=filename)
        session.add(document)
        session.flush()  # populate document.id

        for index, content in enumerate(pages_text):
            page = Page(document_id=document.id, page_number=index + 1, content=content)
            session.add(page)

        session.commit()
        return document.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.route("/", methods=["GET"])
def index():
    session = SessionLocal()
    try:
        recent_docs = (
            session.query(Document)
            .order_by(Document.upload_timestamp.desc())
            .limit(10)
            .all()
        )
        doc_pages_count = {}
        for d in recent_docs:
            count = session.query(Page).filter(Page.document_id == d.id).count()
            doc_pages_count[d.id] = count
    finally:
        session.close()
    return render_template("index.html", recent_docs=recent_docs, doc_pages_count=doc_pages_count)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("لم يتم اختيار ملف")
        return redirect(url_for("index"))

    uploaded_file = request.files["file"]
    if uploaded_file.filename == "":
        flash("اسم الملف فارغ")
        return redirect(url_for("index"))

    if not allowed_file(uploaded_file.filename):
        flash("الرجاء رفع ملف PDF فقط")
        return redirect(url_for("index"))

    filename = secure_filename(uploaded_file.filename)
    save_path = os.path.join(UPLOADS_DIR, filename)
    uploaded_file.save(save_path)

    # Try OCR first (planned in phase 3), then fall back to local extraction
    pages_text = extract_text_via_mistral_ocr(save_path)
    if pages_text is None or all((t or "").strip() == "" for t in pages_text):
        pages_text = extract_text_from_pdf_local(save_path)

    if not pages_text:
        pages_text = [""]

    _doc_id = save_document_and_pages(filename, pages_text)
    flash("تم رفع الملف ومعالجته بنجاح")
    return redirect(url_for("index"))


@app.route("/search", methods=["GET", "POST"])
def search():
    flash("البحث الدلالي سيتاح بعد إضافة FAISS في المرحلة 2")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

