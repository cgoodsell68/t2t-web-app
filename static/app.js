// ── T2T Frontend App ──

const modeDescriptions = {
  chat:     'Ask anything — consulting advice, career guidance, framework explanations, or coaching.',
  document: 'Describe what you need and T2T will generate a complete, professional deliverable.',
  research: 'T2T searches the web in real time to support your query with current evidence.',
};

const modeBadges = {
  chat:     '💬 Chat Mode',
  document: '📄 Document Mode',
  research: '🔍 Research Mode',
};

const thinkingLabels = {
  chat:     'T2T is thinking…',
  document: 'Generating your document…',
  research: 'Searching the web…',
};

let currentMode     = 'chat';
let currentThreadId = null;   // null = start a fresh thread on next message
let isLoading       = false;

// ── Elements ──
const messagesEl       = document.getElementById('messages');
const inputEl          = document.getElementById('userInput');
const sendBtn          = document.getElementById('sendBtn');
const clearBtn         = document.getElementById('clearBtn');
const exportBtn        = document.getElementById('exportBtn');
const thinkingEl       = document.getElementById('thinking');
const thinkingLabel    = document.getElementById('thinkingLabel');
const modeBadgeEl      = document.getElementById('currentModeBadge');
const modeDescEl       = document.getElementById('modeDescription');
const welcomeEl        = document.getElementById('welcomeScreen');
const threadListEl     = document.getElementById('threadList');
const threadTitleEl    = document.getElementById('currentThreadTitle');

// ── Configure marked.js ──
marked.setOptions({ breaks: true, gfm: true });

// ── Mode Switching ──
document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentMode = btn.dataset.mode;
    modeBadgeEl.textContent = modeBadges[currentMode];
    modeDescEl.textContent  = modeDescriptions[currentMode];
  });
});

// ── Quick Starters ──
document.querySelectorAll('.starter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const prompt = btn.dataset.prompt;
    inputEl.value = prompt;
    inputEl.focus();
    autoResize();
    updateSendBtn();
    if (!prompt.endsWith(': ')) {
      sendMessage();
    }
  });
});

// ── Input Handling ──
inputEl.addEventListener('input', () => { autoResize(); updateSendBtn(); });
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!isLoading) sendMessage();
  }
});

function autoResize() {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + 'px';
}

function updateSendBtn() {
  sendBtn.disabled = inputEl.value.trim().length === 0 || isLoading;
}

sendBtn.addEventListener('click', () => { if (!isLoading) sendMessage(); });

// ── New Conversation ──
clearBtn.addEventListener('click', startNewConversation);

function startNewConversation() {
  currentThreadId = null;
  messagesEl.innerHTML = '';
  messagesEl.appendChild(welcomeEl);
  welcomeEl.style.display = 'flex';
  threadTitleEl.textContent = '';
  document.querySelectorAll('.thread-item').forEach(el => el.classList.remove('active'));
}

// ── Export ──
exportBtn.addEventListener('click', exportConversation);

function exportConversation() {
  const messages = document.querySelectorAll('.message');
  if (!messages.length) return;

  let md = '# T2T Conversation Export\n\n';
  messages.forEach(msg => {
    const role  = msg.classList.contains('user') ? '**You**' : '**T2T**';
    const badge = msg.querySelector('.msg-mode-badge');
    const text  = msg.querySelector('.bubble-text');
    if (badge) md += `_${badge.textContent}_\n\n`;
    md += `### ${role}\n\n${text ? text.getAttribute('data-raw') || text.innerText : ''}\n\n---\n\n`;
  });

  const blob = new Blob([md], { type: 'text/markdown' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `t2t-conversation-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Send Message ──
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || isLoading) return;

  hideWelcome();
  addMessage('user', text, currentMode);

  inputEl.value = '';
  autoResize();
  setLoading(true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message:   text,
        mode:      currentMode,
        thread_id: currentThreadId,
      }),
    });

    const data = await res.json();

    if (data.success) {
      // Update thread tracking
      if (!currentThreadId) {
        currentThreadId = data.thread_id;
      }
      // Refresh thread list and highlight active thread
      await loadThreads();
      updateActiveThread(currentThreadId);
      if (data.thread) {
        threadTitleEl.textContent = data.thread.title;
      }
      addMessage('assistant', data.message, data.mode);
    } else {
      addMessage('assistant', `⚠️ Error: ${data.error || 'Something went wrong. Please try again.'}`, currentMode);
    }
  } catch (err) {
    addMessage('assistant', '⚠️ Network error — please check your connection and try again.', currentMode);
  } finally {
    setLoading(false);
  }
}

// ── Render Message ──
function addMessage(role, text, mode) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? 'YOU' : 'T2T';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (role === 'assistant') {
    const badge = document.createElement('span');
    badge.className = `msg-mode-badge ${mode}`;
    badge.textContent = { chat: '💬 Chat', document: '📄 Document', research: '🔍 Research' }[mode] || mode;
    bubble.appendChild(badge);
  }

  const content = document.createElement('div');
  content.className = 'bubble-text';
  content.setAttribute('data-raw', text);

  if (role === 'assistant') {
    content.innerHTML = marked.parse(text);
  } else {
    content.textContent = text;
  }

  bubble.appendChild(content);
  msg.appendChild(avatar);
  msg.appendChild(bubble);
  messagesEl.appendChild(msg);
  scrollToBottom();
}

// ── Thread List ──
async function loadThreads() {
  try {
    const res     = await fetch('/api/threads');
    const data    = await res.json();
    const threads = data.threads || [];

    threadListEl.innerHTML = '';

    if (threads.length === 0) {
      threadListEl.innerHTML = '<p class="thread-empty">No conversations yet</p>';
      return;
    }

    threads.forEach(thread => {
      const item = document.createElement('div');
      item.className = 'thread-item';
      item.dataset.id = thread.id;
      if (thread.id === currentThreadId) item.classList.add('active');

      const title = document.createElement('span');
      title.className = 'thread-title';
      title.textContent = thread.title;

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'thread-delete';
      deleteBtn.title = 'Delete this conversation';
      deleteBtn.textContent = '×';
      deleteBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await deleteThread(thread.id);
      });

      item.appendChild(title);
      item.appendChild(deleteBtn);
      item.addEventListener('click', () => loadThread(thread.id));
      threadListEl.appendChild(item);
    });
  } catch (err) {
    console.error('Failed to load threads:', err);
  }
}

async function loadThread(threadId) {
  try {
    const res  = await fetch(`/api/threads/${threadId}`);
    const data = await res.json();
    const t    = data.thread;

    currentThreadId = threadId;
    threadTitleEl.textContent = t.title;

    messagesEl.innerHTML = '';
    welcomeEl.style.display = 'none';

    t.messages.forEach(m => addMessage(m.role, m.content, m.mode));
    updateActiveThread(threadId);
    scrollToBottom();
  } catch (err) {
    console.error('Failed to load thread:', err);
  }
}

async function deleteThread(threadId) {
  try {
    await fetch(`/api/threads/${threadId}`, { method: 'DELETE' });
    if (threadId === currentThreadId) {
      startNewConversation();
    }
    await loadThreads();
  } catch (err) {
    console.error('Failed to delete thread:', err);
  }
}

function updateActiveThread(threadId) {
  document.querySelectorAll('.thread-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.id) === threadId);
  });
}

// ── Helpers ──
function hideWelcome() {
  if (welcomeEl && welcomeEl.parentNode) {
    welcomeEl.style.display = 'none';
  }
}

function setLoading(loading) {
  isLoading = loading;
  thinkingEl.style.display = loading ? 'flex' : 'none';
  thinkingLabel.textContent = thinkingLabels[currentMode];
  updateSendBtn();
  if (loading) scrollToBottom();
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Init ──
loadThreads();
