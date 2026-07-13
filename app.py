"""
FlowStater — Enterprise Intelligence Knowledge Ecosystem
=========================================================
Backend with:
  - Employee ID / password login with 3 access levels
  - Role-based access control (higher level = higher access)
  - Document sharing visible to all users, downloadable
  - Colleagues chat (real-time polling, per-room threads)
  - Decision analysis
  - Approvals queue & executive dashboard
"""

import os
import re
import json
import sqlite3
import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS

# ----------------------------------------------------------------------------
# Optional file parsers
# ----------------------------------------------------------------------------
try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import docx  # python-docx
except Exception:
    docx = None

# ----------------------------------------------------------------------------
# Optional GenAI (used only for decision analysis, NOT for chat)
# ----------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
try:
    import anthropic
    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except Exception:
    _anthropic_client = None

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "knowledge.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
CORS(app)

# ----------------------------------------------------------------------------
# Demo user database  (employee_id -> {password, name, level, role})
# Level 3 = Executive, Level 2 = Manager, Level 1 = Staff
# ----------------------------------------------------------------------------
DEMO_USERS = {
    "22011830": {
        "password": "22011830nat",
        "name": "Natalie Ooi",
        "level": 2,
        "role": "manager",
        "display_level": "Level 2 — Manager",
    },
    "0181460": {
        "password": "0181460nat",
        "name": "Alex Chen",
        "level": 1,
        "role": "staff",
        "display_level": "Level 1 — Staff",
    },
    "2538755": {
        "password": "2538755nat",
        "name": "Jordan Wu",
        "level": 3,
        "role": "executive",
        "display_level": "Level 3 — Executive",
    },
}

# ----------------------------------------------------------------------------
# Access model
# ----------------------------------------------------------------------------
ROLES = {
    "executive": {"level": 3, "classes": ["public", "internal", "confidential", "restricted"]},
    "manager":   {"level": 2, "classes": ["public", "internal", "confidential"]},
    "staff":     {"level": 1, "classes": ["public", "internal"]},
    "guest":     {"level": 0, "classes": ["public"]},
}

DOC_TYPES = ["MoM", "SOP", "Email", "MessageThread", "File"]

# Document category mapping (for auto-categorisation)
CATEGORY_MAP = {
    "MoM":           "Meeting Notes",
    "SOP":           "Policies & Procedures",
    "Email":         "Communications",
    "MessageThread": "Communications",
    "File":          "General Files",
}


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            doc_type TEXT,
            classification TEXT DEFAULT 'internal',
            owner TEXT,
            owner_name TEXT,
            content TEXT,
            filename TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            question TEXT,
            author TEXT,
            role TEXT,
            verdict TEXT,
            analysis_json TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            sender TEXT,
            text TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS colleague_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL DEFAULT 'general',
            sender_id TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            title TEXT,
            requested_by TEXT,
            assigned_to_role TEXT,
            urgency TEXT,
            due_by TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            description TEXT,
            owner TEXT,
            due_by TEXT,
            status TEXT DEFAULT 'open',
            source TEXT,
            created_at TEXT
        );
        """
    )
    db.commit()

    # Seed demo data
    cur = db.execute("SELECT COUNT(*) AS c FROM documents")
    if cur.fetchone()["c"] == 0:
        now = datetime.datetime.utcnow().isoformat()
        seed_docs = [
            ("SOP-014 Vendor Onboarding", "SOP", "internal",
             "All new vendors MUST complete a security review before any contract is signed. "
             "Contracts above $50,000 require executive approval. Payment terms must not exceed Net-30. "
             "Any deviation requires written sign-off from the Finance manager."),
            ("MoM - Q2 Leadership Sync", "MoM", "confidential",
             "Action: Sarah to finalize vendor shortlist by 2026-07-05. "
             "Action: Ahmad to prepare budget impact report by 2026-07-03. "
             "Decision pending: whether to migrate CRM to new provider. "
             "Risk raised: timeline may slip if security review is skipped."),
            ("Email - Finance re: New CRM vendor", "Email", "confidential",
             "Team, the proposed CRM vendor quoted $72,000/year on Net-45 terms. "
             "We need a decision quickly as the current license expires end of July. "
             "Note: security review has not yet been scheduled."),
            ("Thread - #ops migration", "MessageThread", "internal",
             "Lee: can we just skip the security review to save time? "
             "Sarah: that's risky, SOP-014 requires it. "
             "Ahmad: budget is also over the $50k exec threshold."),
        ]
        for title, dtype, cls, content in seed_docs:
            db.execute(
                "INSERT INTO documents (title, doc_type, classification, owner, owner_name, content, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (title, dtype, cls, "seed", "System", content, now),
            )
        db.execute(
            "INSERT INTO tasks (decision_id, description, owner, due_by, status, source, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (None, "Finalize vendor shortlist", "Sarah", "2026-07-05", "open", "MoM - Q2 Leadership Sync", now),
        )
        db.execute(
            "INSERT INTO tasks (decision_id, description, owner, due_by, status, source, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (None, "Prepare budget impact report", "Ahmad", "2026-07-03", "open", "MoM - Q2 Leadership Sync", now),
        )
        db.commit()

    # Seed colleague chat messages if empty
    cur2 = db.execute("SELECT COUNT(*) AS c FROM colleague_messages")
    if cur2.fetchone()["c"] == 0:
        now = datetime.datetime.utcnow().isoformat()
        seed_msgs = [
            ("general", "2538755", "Jordan Wu",
             "Welcome to the FlowStater team chat! Use this space for quick updates and collaboration."),
            ("general", "22011830", "Natalie Ooi",
             "Thanks Jordan! Don't forget the Q2 vendor review deadline is end of July."),
            ("ops", "0181460", "Alex Chen",
             "Starting the CRM migration planning thread here. Who's joining the kickoff call?"),
            ("ops", "22011830", "Natalie Ooi",
             "I'll be there. Can someone pull the SOP-014 checklist before the call?"),
        ]
        for room, sid, sname, text in seed_msgs:
            db.execute(
                "INSERT INTO colleague_messages (room, sender_id, sender_name, text, created_at)"
                " VALUES (?,?,?,?,?)",
                (room, sid, sname, text, now),
            )
        db.commit()
    db.close()


# ----------------------------------------------------------------------------
# Auth routes
# ----------------------------------------------------------------------------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    emp_id = str(data.get("employee_id", "")).strip()
    password = str(data.get("password", "")).strip()

    user = DEMO_USERS.get(emp_id)
    if not user or user["password"] != password:
        return jsonify({"error": "Invalid employee ID or password."}), 401

    return jsonify({
        "success": True,
        "employee_id": emp_id,
        "name": user["name"],
        "role": user["role"],
        "level": user["level"],
        "display_level": user["display_level"],
        "clearance": ROLES[user["role"]],
    })


@app.route("/api/me")
def api_me():
    emp_id = request.headers.get("X-User", "")
    user_info = DEMO_USERS.get(emp_id)
    if user_info:
        role = user_info["role"]
        name = user_info["name"]
    else:
        role = "guest"
        name = "Guest"
    return jsonify({
        "user": emp_id,
        "name": name,
        "role": role,
        "clearance": ROLES.get(role, ROLES["guest"]),
        "roles": list(ROLES.keys())
    })


def current_user():
    emp_id = request.headers.get("X-User", "demo")
    user_info = DEMO_USERS.get(emp_id)
    if user_info:
        return emp_id, user_info["role"], user_info["name"]
    return emp_id, request.headers.get("X-Role", "guest"), "Guest"


def allowed_classes(role):
    return ROLES.get(role, ROLES["guest"])["classes"]


def visible_documents(db, role):
    classes = allowed_classes(role)
    placeholders = ",".join("?" for _ in classes)
    rows = db.execute(
        f"SELECT * FROM documents WHERE classification IN ({placeholders}) ORDER BY id DESC",
        classes,
    ).fetchall()
    return [dict(r) for r in rows]


# ----------------------------------------------------------------------------
# Text extraction from uploads
# ----------------------------------------------------------------------------
def extract_text(filepath, filename):
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext == "pdf" and PyPDF2:
            text = []
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text() or "")
            return "\n".join(text)
        if ext == "docx" and docx:
            d = docx.Document(filepath)
            return "\n".join(p.text for p in d.paragraphs)
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"[Could not parse file: {e}]"


# ----------------------------------------------------------------------------
# Analysis helpers
# ----------------------------------------------------------------------------
ANALYSIS_SCHEMA = {
    "verdict": "GO | CAUTION | NO-GO",
    "confidence": "0-100",
    "summary": "one paragraph",
    "sop_compliance": [{"rule": "...", "status": "compliant|violated|unclear", "evidence": "..."}],
    "inconsistencies": ["..."],
    "vague_statements": ["..."],
    "risks": [{"risk": "...", "severity": "low|medium|high"}],
    "recommended_next_steps": ["..."],
    "optimal_execution_window": "human-readable timing recommendation",
    "action_items": [{"description": "...", "owner": "...", "due_by": "YYYY-MM-DD"}],
}


def build_context(documents, limit_chars=12000):
    chunks = []
    for d in documents:
        chunks.append(f"### [{d['doc_type']}] {d['title']} (classification: {d['classification']})\n{d['content']}")
    ctx = "\n\n".join(chunks)
    return ctx[:limit_chars]


def analyze_with_claude(question, documents):
    context = build_context(documents)
    system = (
        "You are an enterprise decision-intelligence agent. Using ONLY the provided company "
        "knowledge (MoMs, SOPs, emails, threads, files), analyze the user's proposed decision. "
        "Check SOP compliance, detect inconsistencies across sources, flag vague statements, "
        "highlight risky decisions, and give a clear go/no-go verdict with next steps and the "
        "optimal time to execute. Respond with STRICT JSON only, matching this schema:\n"
        + json.dumps(ANALYSIS_SCHEMA, indent=2)
    )
    user = f"COMPANY KNOWLEDGE:\n{context}\n\nPROPOSED DECISION:\n{question}\n\nReturn JSON only."
    msg = _anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(raw)


def analyze_locally(question, documents):
    corpus = " ".join(d["content"] for d in documents).lower()
    q = question.lower()
    risks, inconsistencies, vague, sop = [], [], [], []
    next_steps = []

    rules = re.findall(r"[^.]*\b(?:must|require[sd]?|shall|not exceed|above \$[\d,]+)\b[^.]*\.", corpus)
    money = re.findall(r"\$\s?([\d,]+)", question + " " + corpus)
    amounts = [int(m.replace(",", "")) for m in money if m.replace(",", "").isdigit()]
    max_amount = max(amounts) if amounts else 0

    if "security review" in corpus:
        if "skip" in corpus or "not yet" in corpus or "not been scheduled" in corpus or "skip" in q:
            sop.append({"rule": "Security review required before contract", "status": "violated",
                        "evidence": "Sources indicate the security review was skipped or not scheduled."})
            risks.append({"risk": "Proceeding without the mandatory security review", "severity": "high"})
        else:
            sop.append({"rule": "Security review required before contract", "status": "unclear",
                        "evidence": "No confirmation that the security review is complete."})

    if max_amount >= 50000:
        sop.append({"rule": "Spend above $50,000 needs executive approval", "status": "violated"
                    if "executive approval" not in q else "compliant",
                    "evidence": f"Detected amount ${max_amount:,} exceeds the $50,000 threshold."})
        risks.append({"risk": "Budget exceeds approval threshold", "severity": "high"})
        next_steps.append("Obtain executive sign-off for spend above $50,000.")

    if "net-30" in corpus and ("net-45" in corpus or "net-45" in q):
        inconsistencies.append("SOP caps payment terms at Net-30, but a source proposes Net-45.")
        sop.append({"rule": "Payment terms must not exceed Net-30", "status": "violated",
                    "evidence": "A vendor quote uses Net-45 terms."})

    vague_terms = ["asap", "quickly", "soon", "maybe", "probably", "some", "a few", "etc", "tbd"]
    for t in vague_terms:
        if t in q or t in corpus:
            vague.append(f"Ambiguous term detected: '{t}' — quantify the timeline/scope.")
    vague = vague[:4]

    if "expire" in corpus or "slip" in corpus or "deadline" in q:
        risks.append({"risk": "Timeline pressure may force shortcuts", "severity": "medium"})

    high = sum(1 for r in risks if r["severity"] == "high")
    violated = sum(1 for s in sop if s["status"] == "violated")
    if high >= 1 or violated >= 1:
        verdict, conf = "NO-GO", 35
    elif risks or inconsistencies or vague:
        verdict, conf = "CAUTION", 60
    else:
        verdict, conf = "GO", 85

    if not next_steps:
        next_steps = ["Confirm all referenced SOP requirements are satisfied.",
                      "Document the decision rationale and circulate for sign-off."]
    if violated:
        next_steps.insert(0, "Resolve every SOP violation before proceeding.")

    today = datetime.date.today()
    window = ("Hold execution until blocking items are cleared (est. 1-2 weeks)."
              if verdict != "GO"
              else f"Safe to execute now; ideally before {today + datetime.timedelta(days=14)}.")

    action_items = [
        {"description": s, "owner": "Manager", "due_by": str(today + datetime.timedelta(days=7))}
        for s in next_steps[:3]
    ]

    return {
        "verdict": verdict,
        "confidence": conf,
        "summary": (f"Analyzed {len(documents)} source document(s). "
                    f"Found {violated} SOP issue(s), {len(inconsistencies)} inconsistency(ies), "
                    f"{len(risks)} risk(s). Verdict: {verdict}."),
        "sop_compliance": sop or [{"rule": "No explicit SOP rules matched", "status": "unclear", "evidence": ""}],
        "inconsistencies": inconsistencies,
        "vague_statements": vague,
        "risks": risks,
        "recommended_next_steps": next_steps,
        "optimal_execution_window": window,
        "action_items": action_items,
        "engine": "local-fallback",
    }


def run_analysis(question, documents):
    if _anthropic_client:
        try:
            result = analyze_with_claude(question, documents)
            result["engine"] = CLAUDE_MODEL
            return result
        except Exception as e:
            fallback = analyze_locally(question, documents)
            fallback["engine"] = f"local-fallback (Claude error: {e})"
            return fallback
    return analyze_locally(question, documents)


# ----------------------------------------------------------------------------
# Routes — Frontend
# ----------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ----------------------------------------------------------------------------
# Routes — Documents (shared, downloadable, auto-categorised)
# ----------------------------------------------------------------------------
@app.route("/api/documents", methods=["GET"])
def list_documents():
    _, role, _ = current_user()
    db = get_db()
    docs = visible_documents(db, role)
    for d in docs:
        d["preview"] = (d["content"] or "")[:200]
        d["category"] = CATEGORY_MAP.get(d["doc_type"], "General Files")
    return jsonify({"documents": docs, "your_clearance": allowed_classes(role)})


@app.route("/api/documents/search", methods=["GET"])
def search_documents():
    _, role, _ = current_user()
    q = request.args.get("q", "").lower().strip()
    category = request.args.get("category", "").strip()
    db = get_db()
    docs = visible_documents(db, role)
    if q:
        docs = [d for d in docs if q in (d["title"] + " " + (d["content"] or "")).lower()]
    for d in docs:
        d["category"] = CATEGORY_MAP.get(d["doc_type"], "General Files")
        idx = (d["content"] or "").lower().find(q)
        snippet = (d["content"] or "")[max(0, idx - 60): idx + 140] if idx >= 0 else (d["content"] or "")[:160]
        d["snippet"] = snippet
    if category:
        docs = [d for d in docs if d["category"] == category]
    return jsonify({"results": docs, "count": len(docs)})


@app.route("/api/documents/categories", methods=["GET"])
def list_categories():
    _, role, _ = current_user()
    db = get_db()
    docs = visible_documents(db, role)
    categories = {}
    for d in docs:
        cat = CATEGORY_MAP.get(d["doc_type"], "General Files")
        categories[cat] = categories.get(cat, 0) + 1
    return jsonify({"categories": categories})


@app.route("/api/documents/<int:doc_id>/download", methods=["GET"])
def download_document(doc_id):
    _, role, _ = current_user()
    db = get_db()
    row = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    doc = dict(row)
    if doc["classification"] not in allowed_classes(role):
        return jsonify({"error": "Access denied"}), 403
    from flask import Response
    content = doc["content"] or ""
    filename = doc.get("filename") or f"{doc['title'].replace(' ', '_')}.txt"
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.route("/api/documents", methods=["POST"])
def upload_document():
    emp_id, role, name = current_user()
    db = get_db()
    now = datetime.datetime.utcnow().isoformat()

    if request.files.get("file"):
        f = request.files["file"]
        dest = UPLOAD_DIR / f.filename
        f.save(dest)
        content = extract_text(dest, f.filename)
        title = request.form.get("title") or f.filename
        doc_type = request.form.get("doc_type", "File")
        classification = request.form.get("classification", "internal")
        filename = f.filename
    else:
        data = request.get_json(force=True)
        content = data.get("content", "")
        title = data.get("title", "Untitled")
        doc_type = data.get("doc_type", "File")
        classification = data.get("classification", "internal")
        filename = None

    if doc_type not in DOC_TYPES:
        doc_type = "File"
    cur = db.execute(
        "INSERT INTO documents (title, doc_type, classification, owner, owner_name, content, filename, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (title, doc_type, classification, emp_id, name, content, filename, now),
    )
    db.commit()
    category = CATEGORY_MAP.get(doc_type, "General Files")
    return jsonify({"id": cur.lastrowid, "title": title, "doc_type": doc_type,
                    "classification": classification, "category": category,
                    "chars": len(content)}), 201


# ----------------------------------------------------------------------------
# Routes — Colleague Chat
# ----------------------------------------------------------------------------
CHAT_ROOMS = {
    "general": "# General",
    "ops":     "⚙ Operations",
    "finance": "💰 Finance",
    "hr":      "👥 HR",
}


@app.route("/api/colleague-chat/rooms", methods=["GET"])
def list_rooms():
    return jsonify({"rooms": [{"id": k, "name": v} for k, v in CHAT_ROOMS.items()]})


@app.route("/api/colleague-chat/<room>/messages", methods=["GET"])
def get_room_messages(room):
    if room not in CHAT_ROOMS:
        return jsonify({"error": "Room not found"}), 404
    since_id = request.args.get("since", 0, type=int)
    db = get_db()
    rows = db.execute(
        "SELECT * FROM colleague_messages WHERE room=? AND id>? ORDER BY id ASC LIMIT 100",
        (room, since_id)
    ).fetchall()
    return jsonify({"messages": [dict(r) for r in rows], "room": room})


@app.route("/api/colleague-chat/<room>/messages", methods=["POST"])
def post_room_message(room):
    if room not in CHAT_ROOMS:
        return jsonify({"error": "Room not found"}), 404
    emp_id, role, name = current_user()
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        "INSERT INTO colleague_messages (room, sender_id, sender_name, text, created_at) VALUES (?,?,?,?,?)",
        (room, emp_id, name, text, now)
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "room": room, "sender_id": emp_id,
                    "sender_name": name, "text": text, "created_at": now}), 201


# ----------------------------------------------------------------------------
# Routes — Decisions / Analysis
# ----------------------------------------------------------------------------
@app.route("/api/decisions", methods=["POST"])
def analyze_decision():
    emp_id, role, name = current_user()
    data = request.get_json(force=True)
    question = data.get("question", "").strip()
    title = data.get("title") or (question[:60] + ("..." if len(question) > 60 else ""))
    if not question:
        return jsonify({"error": "question is required"}), 400

    db = get_db()
    docs = visible_documents(db, role)
    result = run_analysis(question, docs)
    now = datetime.datetime.utcnow().isoformat()

    cur = db.execute(
        "INSERT INTO decisions (title, question, author, role, verdict, analysis_json, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (title, question, emp_id, role, result.get("verdict"), json.dumps(result), now),
    )
    decision_id = cur.lastrowid

    for item in result.get("action_items", []):
        db.execute(
            "INSERT INTO tasks (decision_id, description, owner, due_by, status, source, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (decision_id, item.get("description"), item.get("owner", "Unassigned"),
             item.get("due_by"), "open", "AI action agent", now),
        )
    db.commit()
    result["decision_id"] = decision_id
    result["title"] = title
    result["sources_considered"] = len(docs)
    return jsonify(result)


@app.route("/api/decisions", methods=["GET"])
def list_decisions():
    db = get_db()
    rows = db.execute("SELECT id, title, verdict, author, role, created_at FROM decisions ORDER BY id DESC").fetchall()
    return jsonify({"decisions": [dict(r) for r in rows]})


@app.route("/api/decisions/<int:did>", methods=["GET"])
def get_decision(did):
    db = get_db()
    row = db.execute("SELECT * FROM decisions WHERE id=?", (did,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    d = dict(row)
    d["analysis"] = json.loads(d.pop("analysis_json"))
    msgs = db.execute("SELECT * FROM messages WHERE decision_id=? ORDER BY id", (did,)).fetchall()
    d["messages"] = [dict(m) for m in msgs]
    return jsonify(d)


@app.route("/api/decisions/<int:did>/chat", methods=["POST"])
def decision_chat(did):
    emp_id, role, name = current_user()
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    db = get_db()
    decision = db.execute("SELECT * FROM decisions WHERE id=?", (did,)).fetchone()
    if not decision:
        return jsonify({"error": "decision not found"}), 404
    now = datetime.datetime.utcnow().isoformat()
    db.execute("INSERT INTO messages (decision_id, sender, text, created_at) VALUES (?,?,?,?)",
               (did, emp_id, text, now))

    analysis = json.loads(decision["analysis_json"])
    docs = visible_documents(db, role)
    if _anthropic_client:
        try:
            sys = ("You are an enterprise decision assistant. Answer concisely, grounded in the "
                   "prior analysis and company knowledge. Decision under review: "
                   + decision["question"] + "\nPrior analysis: " + json.dumps(analysis))
            msg = _anthropic_client.messages.create(
                model=CLAUDE_MODEL, max_tokens=600, system=sys,
                messages=[{"role": "user", "content": text}],
            )
            reply = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        except Exception as e:
            reply = f"(local) Based on the analysis, verdict is {analysis.get('verdict')}. {analysis.get('summary')}"
    else:
        reply = (f"Verdict: {analysis.get('verdict')} ({analysis.get('confidence')}% confidence). "
                 f"{analysis.get('summary')} "
                 f"Top next step: {(analysis.get('recommended_next_steps') or ['n/a'])[0]}")
    db.execute("INSERT INTO messages (decision_id, sender, text, created_at) VALUES (?,?,?,?)",
               (did, "AI", reply, now))
    db.commit()
    return jsonify({"reply": reply})


# ----------------------------------------------------------------------------
# Routes — Approvals
# ----------------------------------------------------------------------------
@app.route("/api/decisions/<int:did>/dispatch", methods=["POST"])
def dispatch_actions(did):
    emp_id, role, name = current_user()
    db = get_db()
    decision = db.execute("SELECT * FROM decisions WHERE id=?", (did,)).fetchone()
    if not decision:
        return jsonify({"error": "decision not found"}), 404
    analysis = json.loads(decision["analysis_json"])
    verdict = analysis.get("verdict", "CAUTION")
    urgency = {"NO-GO": "high", "CAUTION": "medium", "GO": "low"}.get(verdict, "medium")
    due = str(datetime.date.today() + datetime.timedelta(days=3 if urgency == "high" else 7))
    now = datetime.datetime.utcnow().isoformat()

    db.execute(
        "INSERT INTO approvals (decision_id, title, requested_by, assigned_to_role, urgency, due_by, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (did, decision["title"], emp_id, "manager", urgency, due, "pending", now),
    )
    db.commit()
    notification = (f"Manager notified: decision '{decision['title']}' (verdict {verdict}) "
                    f"routed for approval. Urgency: {urgency}. Due by {due}.")
    return jsonify({"dispatched": True, "notification": notification,
                    "approval_urgency": urgency, "due_by": due})


@app.route("/api/approvals", methods=["GET"])
def list_approvals():
    emp_id, role, name = current_user()
    db = get_db()
    rows = db.execute("SELECT * FROM approvals ORDER BY "
                      "CASE urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id DESC").fetchall()
    return jsonify({"approvals": [dict(r) for r in rows], "can_approve": role in ("manager", "executive")})


@app.route("/api/approvals/<int:aid>", methods=["POST"])
def act_on_approval(aid):
    emp_id, role, name = current_user()
    if role not in ("manager", "executive"):
        return jsonify({"error": "Only managers/executives can approve."}), 403
    data = request.get_json(force=True)
    status = data.get("status", "approved")
    db = get_db()
    db.execute("UPDATE approvals SET status=? WHERE id=?", (status, aid))
    db.commit()
    return jsonify({"id": aid, "status": status})


# ----------------------------------------------------------------------------
# Routes — Dashboard
# ----------------------------------------------------------------------------
@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    emp_id, role, name = current_user()
    db = get_db()
    tasks = [dict(t) for t in db.execute(
        "SELECT * FROM tasks WHERE status='open' ORDER BY due_by").fetchall()]
    approvals = [dict(a) for a in db.execute(
        "SELECT * FROM approvals WHERE status='pending' ORDER BY "
        "CASE urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END").fetchall()]
    decisions = [dict(d) for d in db.execute(
        "SELECT id, title, verdict, created_at FROM decisions ORDER BY id DESC LIMIT 5").fetchall()]
    docs = visible_documents(db, role)
    verdict_counts = {"GO": 0, "CAUTION": 0, "NO-GO": 0}
    for d in db.execute("SELECT verdict FROM decisions").fetchall():
        if d["verdict"] in verdict_counts:
            verdict_counts[d["verdict"]] += 1
    return jsonify({
        "pending_tasks": tasks,
        "pending_approvals": approvals,
        "recent_decisions": decisions,
        "document_count": len(docs),
        "verdict_counts": verdict_counts,
        "ai_enabled": bool(_anthropic_client),
    })


if __name__ == "__main__":
    init_db()
    print("=" * 64)
    print(" FlowStater — Enterprise Intelligence Knowledge Ecosystem")
    print(" GenAI engine:", CLAUDE_MODEL if _anthropic_client else "LOCAL FALLBACK (no ANTHROPIC_API_KEY)")
    print(" Open: http://localhost:5000")
    print("=" * 64)
    app.run(host="0.0.0.0", port=5000, debug=True)
