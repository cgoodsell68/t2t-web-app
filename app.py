from flask import Flask, render_template, request, jsonify, session, redirect
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
from datetime import datetime
from functools import wraps
import os
import requests as http_requests
import stripe

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production-please')

# ─────────────────────────────────────────────
#  DATABASE SETUP
# ─────────────────────────────────────────────
database_url = os.environ.get('DATABASE_URL', 'sqlite:///t2t.db')
# Railway/Heroku provide postgres:// but SQLAlchemy needs postgresql://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ─────────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────────

class User(db.Model):
    __tablename__ = 'users'
    id                  = db.Column(db.Integer, primary_key=True)
    email               = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name                = db.Column(db.String(200))
    phone               = db.Column(db.String(50))
    password_hash       = db.Column(db.String(255))
    ghl_contact_id      = db.Column(db.String(100))
    has_seen_onboarding = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    tier                = db.Column(db.Integer, default=0, nullable=False, server_default='0')  # 0=free, 1=Tier1, 2=Tier2
    stripe_customer_id  = db.Column(db.String(100))
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    threads             = db.relationship('Thread', backref='user', lazy=True,
                                          cascade='all, delete-orphan')

    def set_password(self, password):
        import hashlib, secrets
        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256((salt + password).encode()).hexdigest()
        self.password_hash = f"{salt}:{pw_hash}"

    def check_password(self, password):
        if not self.password_hash or ':' not in self.password_hash:
            return False
        import hashlib
        salt, pw_hash = self.password_hash.split(':', 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == pw_hash

    def to_dict(self):
        return {
            'id':                  self.id,
            'name':                self.name,
            'email':               self.email,
            'has_seen_onboarding': bool(self.has_seen_onboarding),
            'tier':                self.tier or 0,
        }


class Thread(db.Model):
    __tablename__ = 'threads'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    title      = db.Column(db.String(200), nullable=False, default='New Conversation')
    mode       = db.Column(db.String(20), default='chat')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages   = db.relationship(
        'Message', backref='thread', lazy=True,
        cascade='all, delete-orphan',
        order_by='Message.created_at'
    )

    def to_dict(self, include_messages=False):
        d = {
            'id':         self.id,
            'title':      self.title,
            'mode':       self.mode,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        if include_messages:
            d['messages'] = [m.to_dict() for m in self.messages]
        return d


class Message(db.Model):
    __tablename__ = 'messages'
    id         = db.Column(db.Integer, primary_key=True)
    thread_id  = db.Column(db.Integer, db.ForeignKey('threads.id'), nullable=False)
    role       = db.Column(db.String(20), nullable=False)   # 'user' | 'assistant'
    content    = db.Column(db.Text, nullable=False)
    mode       = db.Column(db.String(20), default='chat')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         self.id,
            'role':       self.role,
            'content':    self.content,
            'mode':       self.mode,
            'created_at': self.created_at.isoformat(),
        }


# Create tables on startup, and run any needed column migrations
with app.app_context():
    db.create_all()
    # Migration: add has_seen_onboarding if it doesn't exist yet
    for migration_sql in [
        'ALTER TABLE users ADD COLUMN has_seen_onboarding BOOLEAN NOT NULL DEFAULT 0',
        'ALTER TABLE users ADD COLUMN tier INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(100)',
    ]:
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text(migration_sql))
                conn.commit()
        except Exception:
            pass  # Column already exists — safe to ignore


# ─────────────────────────────────────────────
#  GHL CONFIG
# ─────────────────────────────────────────────
GHL_API_KEY     = os.environ.get('GHL_API_KEY', '')
GHL_LOCATION_ID = os.environ.get('GHL_LOCATION_ID', '')
GHL_BASE        = 'https://services.leadconnectorhq.com'


def ghl_headers():
    return {
        'Authorization': f'Bearer {GHL_API_KEY}',
        'Version':       '2021-07-28',
        'Content-Type':  'application/json',
    }


def find_ghl_contact_by_email(email):
    """Search GHL for a contact by email. Returns contact dict or None."""
    try:
        resp = http_requests.get(
            f'{GHL_BASE}/contacts/search',
            headers=ghl_headers(),
            params={'query': email, 'locationId': GHL_LOCATION_ID},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            contacts = data.get('contacts', [])
            # Find exact email match
            for c in contacts:
                if c.get('email', '').lower() == email.lower():
                    return c
        return None
    except Exception:
        return None


def create_ghl_contact(name, email, phone):
    """Create a new contact in GHL. Returns contact dict or None."""
    try:
        first_name = name.split()[0] if name else ''
        last_name  = ' '.join(name.split()[1:]) if len(name.split()) > 1 else ''
        payload = {
            'firstName':  first_name,
            'lastName':   last_name,
            'email':      email,
            'phone':      phone or '',
            'locationId': GHL_LOCATION_ID,
        }
        resp = http_requests.post(
            f'{GHL_BASE}/contacts/',
            headers=ghl_headers(),
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get('contact', data)
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────
#  STRIPE CONFIG
# ─────────────────────────────────────────────
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET  = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
STRIPE_TIER1_PRICE_ID  = 'price_1T4KkTFgw6IwkGiqFr3e1Hyi'   # $67 one-time
STRIPE_TIER2_PRICE_ID  = 'price_1T4KkfFgw6IwkGiqFPAPHzIa'   # $67/month
STRIPE_TIER1_LINK      = 'https://buy.stripe.com/7sYbJ16OO7n04zF39Y8og00'
STRIPE_TIER2_LINK      = 'https://buy.stripe.com/3cIaEXgpofTwaY3eSG8og01'
APP_BASE_URL           = os.environ.get('APP_BASE_URL', 'https://web-production-9a5f2.up.railway.app')


# ─────────────────────────────────────────────
#  OPENAI CLIENT
# ─────────────────────────────────────────────
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))


# ─────────────────────────────────────────────
#  T2T SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are T2T, an expert AI assistant built for training consultants, instructional designers, brand strategists, and career mentors. You serve educators, L&D teams, corporate trainers, independent consultants, and professionals in career transition.

You operate at the intersection of performance consulting, instructional design, and business strategy. You do not give generic answers — you give structured, professional, practitioner-level responses grounded in established frameworks.

─── YOUR CORE CAPABILITIES ───

1. CONSULTING & DISCOVERY INTELLIGENCE
You conduct structured Socratic discovery interviews. You uncover root performance gaps (skills vs systems vs motivation), identify hidden constraints and decision drivers, clarify success metrics before design begins, and distinguish training problems from policy or process problems. You can simulate friendly discovery calls, skeptical executives, budget-resistant clients, and cross-cultural stakeholders.

2. TRAINING NEEDS ANALYSIS (TNA) & PERFORMANCE DIAGNOSIS
You build complete Training Needs Analysis documents including stakeholder alignment, interview protocols, observation checklists, root cause classification (training vs non-training), competency mapping, and KPI alignment. You produce gap analysis tables, decision trees, baseline and target metric plans, ROI projections, and governance dashboards.

3. INSTRUCTIONAL DESIGN & CURRICULUM ARCHITECTURE
You design learning ecosystems aligned to: Knowles (adult learning), Merrill's First Principles, Bloom's Taxonomy, Gagné's 9 Events, ADDIE, Kirkpatrick & Phillips ROI. You convert vague ideas into measurable objectives, sequence content from novice to advanced, and design blended learning (ILT, VILT, microlearning, async, coaching).

4. TURNING IDEAS INTO DELIVERABLES
Given a rough idea, workshop outline, topic, or whiteboard brainstorm, you produce:
- Structured Lesson Plans (business need, learning purpose, Bloom-level objectives, Merrill alignment, session arc, inclusion design, evaluation plan)
- Facilitation Plans (detailed timing, instructions, transitions, delivery logic)
- Participant Materials (workbooks, job aids, reflection templates, role-play scripts, observation rubrics, assessment instruments)
- Slide Structures (8–10 minute lecture bursts, interaction every ≤10 minutes, poll placement, reflection prompts)
- eLearning Modules (storyboards, branching scenarios, simulation design, knowledge checks, microlearning sequences)
- Assessment Systems (diagnostic tools, pre/post instruments, behavior tracking, KPI alignment matrices)
Every activity ties back to a performance objective — no filler.

5. FACILITATION COACHING & METHOD SELECTION
You select the right engagement method for any objective, recommend role-play vs case vs simulation vs jigsaw, design psychologically safe debriefs, plan hybrid/virtual interaction rhythm, and coach on energy, pacing, and tone.

6. EVALUATION & BUSINESS IMPACT DESIGN
You build evaluation systems aligned to Kirkpatrick Levels 1–4 and Phillips ROI. You design executive dashboards, translate training results into business language, build renewal/scale logic, and draft post-program impact reports.

7. CAREER TRANSITION PATH DESIGN
For educators and trainers seeking transition, you map teaching skills to corporate competencies, define niche and value proposition, create 3–12 month upskilling roadmaps, and design consulting packages, corporate training offerings, course creation models, digital products, and retainer models. You also guide brand strategy using StoryBrand frameworks.

8. PROPOSAL & RFP RESPONSE DEVELOPMENT
You analyze RFPs, identify missing information, generate discovery question sets, draft executive summaries, build compliant proposal structures, write evaluation approaches, design sample curriculum sections, and construct pricing rationale.

9. META-LEARNING & REFLECTIVE COACHING
After projects, you prompt structured reflection, identify improvement opportunities, audit alignment with adult learning principles, check inclusion and accessibility compliance, and help build mastery over time.

─── YOUR TONE & APPROACH ───
- Professional, direct, and practitioner-level
- Never generic — always specific, structured, and actionable
- Use frameworks by name when relevant
- Format responses with clear headings, tables, and structure when producing deliverables
- Ask clarifying questions before producing documents if key information is missing
- Always tie outputs back to measurable performance outcomes

You take clients from: Idea → Interview → Diagnosis → Curriculum → Lesson Plan → Facilitation Plan → Materials → Delivery → Evaluation → ROI → Portfolio → Brand → Growth Strategy."""

DOCUMENT_SUFFIX = """

You are in DOCUMENT GENERATION MODE. The user is requesting a complete, professional deliverable.
- Produce the full document — do not truncate, summarize, or say "and so on"
- Use proper headings (##, ###), tables, bullet lists, and numbered sections
- Include all sections a real practitioner would expect
- Make it client-ready and publication-quality
- Length should match the complexity of the request — do not artificially shorten"""

RESEARCH_SUFFIX = """

You are in RESEARCH MODE. You have access to live web search.
- Use web search to find current, accurate information to support your response
- Cite sources inline where relevant
- Combine retrieved information with your expert knowledge
- Produce a structured, well-evidenced response"""

CAREER_CLARITY_PROMPT = """You are the T2T Career Clarity Coach — a specialised AI guide that takes educators through a powerful 8-question journey to reveal exactly how to transition into a corporate training career.

You use the S.K.I.L.L.S. Framework (Spot → Know → Identify → Language → Leverage → Secure), Socratic discovery, and NLP-informed coaching.

─── YOUR OPENING MESSAGE (use this EXACT text for your very first message in a career session) ───

"Welcome. You're about to answer 8 questions that most career coaches never think to ask.

Your answers will shape your personalised **LinkedIn Transformation Plan** and your **90-Day Career Clarity Roadmap** — built entirely from what you tell me.

Take your time. There are no wrong answers — only honest ones.

Let's begin.

**Question 1 of 8:** What subject or level are you currently teaching — and what's the part of it that you love most?"

─── THE 8 QUESTIONS (ask one at a time, always numbered) ───

Q1: What subject or level are you currently teaching — and what's the part of it that you love most?
Q2: What first made you start thinking about a change? What was the moment, or the feeling?
Q3: When you picture yourself in a corporate training role — what does it look like? What are you doing, who's in the room, how does it feel?
Q4: What's your biggest fear about making this transition?
Q5: Have you ever trained adults outside the classroom — even informally, even once?
Q6: What do people — colleagues, students, managers — consistently say you're great at?
Q7: What timeline feels right to you? Are you ready to move in the next 90 days, or building toward something further out?
Q8: If this transition goes perfectly — what does your life and work look like 12 months from now? Be specific.

─── YOUR METHOD AFTER EACH ANSWER ───

1. REFLECT their language back: "What I'm hearing is that [their words]..."
2. CONFIRM or weave into next question naturally
3. DEEPEN if surface answer: "And when you say [X], what do you mean specifically?"
4. Ask the NEXT question — always numbered "**Question X of 8:**"

Only ask ONE question at a time. Never skip ahead.

─── AFTER QUESTION 3 — DOPAMINE HIT (deliver this before Q4) ───

After the user answers Q3, deliver this BEFORE asking Q4:

"⚡ Before I continue — I want to pause and tell you something important.

Based on what you've shared, I can already see [name 3 specific transferable skills using THEIR exact words, reframed in corporate language].

Most teachers completely overlook these. They're presenting themselves as a teacher when they should be positioning as a [suggest a relevant corporate training title].

You are more ready than you think.

**Question 4 of 8:** [Q4 text]"

─── AFTER QUESTION 8 — FULL CAREER CLARITY REPORT ───

After the user answers Q8, produce the complete report using this EXACT structure:

---

# 🎯 Your Career Clarity Report

## What I Heard

[2-3 sentences summarising their journey using THEIR exact words — mirror their language]

---

## ✨ Your 3 Hidden Transferable Skills

[For each of 3 skills drawn from their answers:
**[Skill Name in corporate language]**
- *In the classroom:* what they called it / did
- *In the boardroom:* what companies pay for
- *Why it matters:* one sentence on market value]

---

## 🔗 Your LinkedIn Transformation Plan

### Headline Options (pick one or blend)
[3 specific headline options using their subject area and corporate language]

### About Section
[Full ~150 word About section written in first person using StoryBrand: their journey, the problem they solve, who they serve, their unique credibility, a CTA]

### Skills to Add to Your Profile
[10 specific LinkedIn skills drawn from their background and the S.K.I.L.L.S. framework]

### Featured Section
[3 content/portfolio ideas to build LinkedIn credibility]

---

## 🗓️ Your 90-Day Career Clarity Roadmap

### Week 1–2: Foundations
[3-4 specific actions — update LinkedIn, identify target companies, join L&D communities]

### Week 3–4: Translation
[3-4 specific actions — reach out to contacts, write first LinkedIn post, refine language]

### Month 2: Application
[3-4 specific actions — build a portfolio piece, informational interviews, apply to roles]

### Month 3: Positioning & Launch
[3-4 specific actions — first contract conversation, proposal template, pitch]

---

## 🚀 Your Single Next Step

[One specific, personalised action based on THEIR timeline (Q7) and vision (Q8)]

---

*Ready to go deeper? **T2T Full Access** unlocks curriculum design, proposal writing, training delivery coaching — everything you need to build your practice.*
*[Upgrade to Full Access →]*

---

─── S.K.I.L.L.S. FRAMEWORK ───
Spot → Know → Identify → Language → Leverage → Secure

Teaching → Corporate translation examples:
- "Lesson planning" → "Curriculum architecture" / "Learning journey design"
- "Classroom management" → "Group facilitation" / "Engagement strategy"
- "Assessment design" → "Performance measurement" / "Competency evaluation"
- "Parent communication" → "Stakeholder management"
- "Differentiated instruction" → "Personalised learning design" / "Adaptive facilitation"
- "ESL/EFL teaching" → "Cross-cultural communication training"
- "IEP/ELL support" → "Accessibility & inclusion design"

─── TONE ───
Warm, direct, credible — like a mentor who made this journey themselves.
Mirror their language throughout. Never generic. Build momentum.
The dopamine hit after Q3 should feel like a revelation, not a compliment."""


# ─────────────────────────────────────────────
#  AUTH HELPERS
# ─────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required', 'auth_required': True}), 401
        return f(*args, **kwargs)
    return decorated


def make_thread_title(text):
    """Generate a short title from the first user message."""
    text = text.strip()
    return (text[:60] + '…') if len(text) > 60 else text


# ─────────────────────────────────────────────
#  ROUTES — PAGES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ─────────────────────────────────────────────
#  ROUTES — AUTH
# ─────────────────────────────────────────────

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data     = request.json or {}
    name     = data.get('name', '').strip()
    email    = data.get('email', '').strip().lower()
    phone    = data.get('phone', '').strip()
    password = data.get('password', '')

    if not name or not email or not password:
        return jsonify({'error': 'Name, email, and password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400

    # Check if email already registered locally
    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({'error': 'An account with this email already exists. Please log in.'}), 409

    # Create contact in GHL
    ghl_contact    = create_ghl_contact(name, email, phone)
    ghl_contact_id = ghl_contact.get('id') if ghl_contact else None

    # Create local user
    user = User(
        email          = email,
        name           = name,
        phone          = phone,
        ghl_contact_id = ghl_contact_id,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    return jsonify({'success': True, 'user': user.to_dict()}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data     = request.json or {}
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    # Look up local user
    user = User.query.filter_by(email=email).first()

    if not user:
        # Check if they exist in GHL (registered via another channel)
        ghl_contact = find_ghl_contact_by_email(email)
        if ghl_contact:
            return jsonify({
                'error':        'Account found — please complete sign-up to set your password.',
                'needs_signup': True,
            }), 404
        return jsonify({'error': 'No account found with that email. Please sign up.'}), 404

    if not user.check_password(password):
        return jsonify({'error': 'Incorrect password. Please try again.'}), 401

    session['user_id'] = user.id
    return jsonify({'success': True, 'user': user.to_dict()})


@app.route('/api/complete-onboarding', methods=['POST'])
@login_required
def complete_onboarding():
    user_id = session['user_id']
    user = User.query.get(user_id)
    if user:
        user.has_seen_onboarding = True
        db.session.commit()
    return jsonify({'success': True})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
def me():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'user': None})
    user = User.query.get(user_id)
    if not user:
        session.pop('user_id', None)
        return jsonify({'user': None})
    return jsonify({'user': user.to_dict()})


# ─────────────────────────────────────────────
#  ROUTES — THREADS
# ─────────────────────────────────────────────

@app.route('/api/threads', methods=['GET'])
@login_required
def list_threads():
    user_id = session['user_id']
    threads = (Thread.query
               .filter_by(user_id=user_id)
               .order_by(Thread.updated_at.desc())
               .all())
    return jsonify({'threads': [t.to_dict() for t in threads]})


@app.route('/api/threads', methods=['POST'])
@login_required
def create_thread():
    data    = request.json or {}
    title   = data.get('title', 'New Conversation')
    mode    = data.get('mode', 'chat')
    user_id = session['user_id']
    t = Thread(title=title, mode=mode, user_id=user_id)
    db.session.add(t)
    db.session.commit()
    return jsonify({'thread': t.to_dict()}), 201


@app.route('/api/threads/<int:thread_id>', methods=['GET'])
@login_required
def get_thread(thread_id):
    user_id = session['user_id']
    t = Thread.query.filter_by(id=thread_id, user_id=user_id).first_or_404()
    return jsonify({'thread': t.to_dict(include_messages=True)})


@app.route('/api/threads/<int:thread_id>', methods=['PUT'])
@login_required
def rename_thread(thread_id):
    user_id = session['user_id']
    t = Thread.query.filter_by(id=thread_id, user_id=user_id).first_or_404()
    data = request.json or {}
    if 'title' in data:
        t.title      = data['title'][:200]
        t.updated_at = datetime.utcnow()
        db.session.commit()
    return jsonify({'thread': t.to_dict()})


@app.route('/api/threads/<int:thread_id>', methods=['DELETE'])
@login_required
def delete_thread(thread_id):
    user_id = session['user_id']
    t = Thread.query.filter_by(id=thread_id, user_id=user_id).first_or_404()
    db.session.delete(t)
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────
#  ROUTES — CHAT
# ─────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    data         = request.json
    user_message = data.get('message', '').strip()
    mode         = data.get('mode', 'chat')
    thread_id    = data.get('thread_id')      # None = start a new thread
    user_id      = session['user_id']

    if not user_message:
        return jsonify({'success': False, 'error': 'No message provided'}), 400

    # ── Paywall check for career mode ──
    if mode == 'career':
        user = User.query.get(user_id)
        if not user or user.tier < 1:
            return jsonify({
                'success':  False,
                'paywall':  True,
                'error':    'Career Clarity Coach requires Tier 1 access.',
                'checkout': '/api/checkout/tier1',
            }), 403

    # ── Get or create thread ──
    if thread_id:
        thread = Thread.query.filter_by(id=thread_id, user_id=user_id).first()
        if not thread:
            return jsonify({'success': False, 'error': 'Thread not found'}), 404
    else:
        thread = Thread(
            title   = make_thread_title(user_message),
            mode    = mode,
            user_id = user_id,
        )
        db.session.add(thread)
        db.session.flush()   # get id before commit

    # ── Persist user message ──
    user_msg = Message(thread_id=thread.id, role='user', content=user_message, mode=mode)
    db.session.add(user_msg)

    # ── Build conversation history for the API ──
    history = Message.query.filter_by(thread_id=thread.id).order_by(Message.created_at).all()
    # Include up to last 20 messages (excluding the one we just added)
    past = [{'role': m.role, 'content': m.content} for m in history[-20:]]

    try:
        if mode == 'career':
            # Count how many user messages exist in this thread (excluding current)
            user_msg_count = Message.query.filter_by(
                thread_id=thread.id, role='user'
            ).count()
            # user_msg_count includes the message we just added
            question_number = min(user_msg_count, 8)

            messages = [{'role': 'system', 'content': CAREER_CLARITY_PROMPT}] + past
            completion = client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                max_tokens=3000,
                temperature=0.75,
            )
            assistant_text = completion.choices[0].message.content

            asst_msg = Message(thread_id=thread.id, role='assistant', content=assistant_text, mode=mode)
            db.session.add(asst_msg)
            thread.updated_at = datetime.utcnow()
            db.session.commit()

            return jsonify({
                'success': True,
                'message': assistant_text,
                'mode': mode,
                'thread_id': thread.id,
                'thread': thread.to_dict(),
                'question_number': question_number,
            })

        elif mode == 'research':
            system         = SYSTEM_PROMPT + RESEARCH_SUFFIX
            input_messages = [{'role': 'system', 'content': system}] + past
            response       = client.responses.create(
                model  = 'gpt-4o',
                tools  = [{'type': 'web_search_preview'}],
                input  = input_messages,
            )
            assistant_text = response.output_text

        else:
            system = SYSTEM_PROMPT
            if mode == 'document':
                system += DOCUMENT_SUFFIX

            messages   = [{'role': 'system', 'content': system}] + past
            completion = client.chat.completions.create(
                model       = 'gpt-4o',
                messages    = messages,
                max_tokens  = 4096 if mode == 'document' else 2048,
                temperature = 0.7,
            )
            assistant_text = completion.choices[0].message.content

        # ── Persist assistant reply ──
        asst_msg = Message(thread_id=thread.id, role='assistant', content=assistant_text, mode=mode)
        db.session.add(asst_msg)
        thread.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success':   True,
            'message':   assistant_text,
            'mode':      mode,
            'thread_id': thread.id,
            'thread':    thread.to_dict(),
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/clear', methods=['POST'])
def clear():
    """Legacy endpoint — kept for compatibility."""
    return jsonify({'success': True})


@app.route('/api/career/start', methods=['POST'])
@login_required
def career_start():
    """Create a new career clarity thread and get the opening message from the AI."""
    user_id = session['user_id']
    user    = User.query.get(user_id)

    # Paywall — Tier 1 or above required
    if not user or user.tier < 1:
        return jsonify({
            'success':  False,
            'paywall':  True,
            'error':    'Career Clarity Coach requires Tier 1 access.',
            'checkout': '/api/checkout/tier1',
        }), 403

    thread = Thread(
        title='Career Clarity Journey',
        mode='career',
        user_id=user_id,
    )
    db.session.add(thread)
    db.session.flush()

    # Get opening message from AI
    try:
        messages = [
            {'role': 'system', 'content': CAREER_CLARITY_PROMPT},
            {'role': 'user', 'content': 'START_CAREER_CLARITY_SESSION'},
        ]
        completion = client.chat.completions.create(
            model='gpt-4o',
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        opening_text = completion.choices[0].message.content

        # Save the opening as an assistant message
        asst_msg = Message(
            thread_id=thread.id,
            role='assistant',
            content=opening_text,
            mode='career',
        )
        db.session.add(asst_msg)
        db.session.commit()

        return jsonify({
            'success': True,
            'thread': thread.to_dict(),
            'opening_message': opening_text,
            'question_number': 0,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────
#  ROUTES — STRIPE CHECKOUT & WEBHOOK
# ─────────────────────────────────────────────

@app.route('/api/checkout/tier1')
@login_required
def checkout_tier1():
    """Redirect logged-in user to Stripe payment link with their user ID attached."""
    user_id = session['user_id']
    url = f"{STRIPE_TIER1_LINK}?client_reference_id={user_id}&prefilled_email={_get_user_email(user_id)}"
    return redirect(url)


@app.route('/api/checkout/tier2')
@login_required
def checkout_tier2():
    """Redirect logged-in user to Stripe Tier 2 payment link."""
    user_id = session['user_id']
    url = f"{STRIPE_TIER2_LINK}?client_reference_id={user_id}&prefilled_email={_get_user_email(user_id)}"
    return redirect(url)


def _get_user_email(user_id):
    user = User.query.get(user_id)
    return user.email if user else ''


@app.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """Stripe sends payment events here. We upgrade user tier on success."""
    payload    = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            # Dev mode — trust the payload directly (never in production)
            import json
            event = json.loads(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    event_type = event.get('type') if isinstance(event, dict) else event['type']

    if event_type == 'checkout.session.completed':
        session_obj = event['data']['object']
        client_ref  = session_obj.get('client_reference_id')  # our user_id
        customer_id = session_obj.get('customer')
        mode        = session_obj.get('mode')          # 'payment' or 'subscription'
        price_id    = None

        # Get price from line items
        line_items = session_obj.get('line_items', {}).get('data', [])
        if line_items:
            price_id = line_items[0].get('price', {}).get('id')
        else:
            # Fallback: check metadata or amount
            price_id = session_obj.get('metadata', {}).get('price_id')

        if client_ref:
            try:
                user = User.query.get(int(client_ref))
                if user:
                    if customer_id:
                        user.stripe_customer_id = customer_id
                    # Determine tier from mode
                    if mode == 'subscription':
                        user.tier = 2
                    else:
                        user.tier = 1
                    db.session.commit()

                    # Tag in GHL
                    if user.ghl_contact_id:
                        tag = 'T2T Tier 2' if user.tier == 2 else 'T2T Tier 1'
                        _tag_ghl_contact(user.ghl_contact_id, tag)
            except Exception:
                pass  # Log silently — don't fail the webhook

    elif event_type in ('customer.subscription.deleted', 'customer.subscription.paused'):
        # Downgrade Tier 2 users if subscription cancelled
        sub_obj     = event['data']['object']
        customer_id = sub_obj.get('customer')
        if customer_id:
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if user and user.tier == 2:
                user.tier = 0
                db.session.commit()

    return jsonify({'received': True}), 200


def _tag_ghl_contact(contact_id, tag):
    """Add a tag to a GHL contact."""
    try:
        http_requests.post(
            f'{GHL_BASE}/contacts/{contact_id}/tags',
            headers=ghl_headers(),
            json={'tags': [tag]},
            timeout=10,
        )
    except Exception:
        pass


@app.route('/api/user/tier', methods=['GET'])
@login_required
def get_user_tier():
    """Return the current user's tier."""
    user = User.query.get(session['user_id'])
    return jsonify({'tier': user.tier if user else 0})


# ─────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(
        debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true',
        host  = '0.0.0.0',
        port  = port,
    )
