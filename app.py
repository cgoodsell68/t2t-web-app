from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from openai import OpenAI
from datetime import datetime
import os

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


class Thread(db.Model):
    __tablename__ = 'threads'
    id         = db.Column(db.Integer, primary_key=True)
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


# Create tables on startup
with app.app_context():
    db.create_all()

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


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

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
#  ROUTES — THREADS
# ─────────────────────────────────────────────

@app.route('/api/threads', methods=['GET'])
def list_threads():
    threads = Thread.query.order_by(Thread.updated_at.desc()).all()
    return jsonify({'threads': [t.to_dict() for t in threads]})


@app.route('/api/threads', methods=['POST'])
def create_thread():
    data  = request.json or {}
    title = data.get('title', 'New Conversation')
    mode  = data.get('mode', 'chat')
    t = Thread(title=title, mode=mode)
    db.session.add(t)
    db.session.commit()
    return jsonify({'thread': t.to_dict()}), 201


@app.route('/api/threads/<int:thread_id>', methods=['GET'])
def get_thread(thread_id):
    t = Thread.query.get_or_404(thread_id)
    return jsonify({'thread': t.to_dict(include_messages=True)})


@app.route('/api/threads/<int:thread_id>', methods=['PUT'])
def rename_thread(thread_id):
    t = Thread.query.get_or_404(thread_id)
    data = request.json or {}
    if 'title' in data:
        t.title = data['title'][:200]
        t.updated_at = datetime.utcnow()
        db.session.commit()
    return jsonify({'thread': t.to_dict()})


@app.route('/api/threads/<int:thread_id>', methods=['DELETE'])
def delete_thread(thread_id):
    t = Thread.query.get_or_404(thread_id)
    db.session.delete(t)
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────
#  ROUTES — CHAT
# ─────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
def chat():
    data         = request.json
    user_message = data.get('message', '').strip()
    mode         = data.get('mode', 'chat')
    thread_id    = data.get('thread_id')      # None = start a new thread

    if not user_message:
        return jsonify({'success': False, 'error': 'No message provided'}), 400

    # ── Get or create thread ──
    if thread_id:
        thread = Thread.query.get(thread_id)
        if not thread:
            return jsonify({'success': False, 'error': 'Thread not found'}), 404
    else:
        thread = Thread(
            title=make_thread_title(user_message),
            mode=mode,
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
        if mode == 'research':
            system = SYSTEM_PROMPT + RESEARCH_SUFFIX
            input_messages = [{'role': 'system', 'content': system}] + past
            response = client.responses.create(
                model='gpt-4o',
                tools=[{'type': 'web_search_preview'}],
                input=input_messages,
            )
            assistant_text = response.output_text

        else:
            system = SYSTEM_PROMPT
            if mode == 'document':
                system += DOCUMENT_SUFFIX

            messages = [{'role': 'system', 'content': system}] + past
            completion = client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                max_tokens=4096 if mode == 'document' else 2048,
                temperature=0.7,
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
    """Legacy endpoint — kept for compatibility. Frontend now uses thread system."""
    return jsonify({'success': True})


# ─────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true',
        host='0.0.0.0',
        port=port,
    )
