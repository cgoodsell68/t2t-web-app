// ── T2T Frontend App ──

const modeDescriptions = {
  chat:     'Ask anything — consulting advice, career guidance, framework explanations, or coaching.',
  document: 'Describe what you need and T2T will generate a complete, professional deliverable.',
  research: 'T2T searches the web in real time to support your query with current evidence.',
  career:   '8 guided questions → your personalised LinkedIn plan and 90-day career roadmap.',
};

const modeBadges = {
  chat:     '💬 Chat Mode',
  document: '📄 Document Mode',
  research: '🔍 Research Mode',
  career:   '🎯 Career Clarity',
};

const thinkingLabels = {
  chat:     'T2T is thinking…',
  document: 'Generating your document…',
  research: 'Searching the web…',
  career:   'Your coach is thinking…',
};

let currentMode     = 'chat';
let currentThreadId = null;
let isLoading       = false;
let currentUser     = null;

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
const sidebarEl        = document.getElementById('sidebar');
const overlayEl        = document.getElementById('sidebarOverlay');
const hamburgerEl      = document.getElementById('hamburger');
const mainAppEl        = document.getElementById('mainApp');
const authOverlayEl    = document.getElementById('authOverlay');
const userNameEl       = document.getElementById('userNameDisplay');
const logoutBtn        = document.getElementById('logoutBtn');

// ── Auth: Login / Signup Panels ──
const loginPanel    = document.getElementById('loginPanel');
const signupPanel   = document.getElementById('signupPanel');
const loginEmailEl  = document.getElementById('loginEmail');
const loginPassEl   = document.getElementById('loginPassword');
const loginBtn      = document.getElementById('loginBtn');
const loginErrorEl  = document.getElementById('loginError');
const signupNameEl  = document.getElementById('signupName');
const signupEmailEl = document.getElementById('signupEmail');
const signupPhoneEl = document.getElementById('signupPhone');
const signupPassEl  = document.getElementById('signupPassword');
const signupBtn     = document.getElementById('signupBtn');
const signupErrorEl = document.getElementById('signupError');

// Toggle between login and signup panels
document.getElementById('showSignup').addEventListener('click', (e) => {
  e.preventDefault();
  loginPanel.style.display  = 'none';
  signupPanel.style.display = 'block';
  loginErrorEl.style.display = 'none';
});

document.getElementById('showLogin').addEventListener('click', (e) => {
  e.preventDefault();
  signupPanel.style.display = 'none';
  loginPanel.style.display  = 'block';
  signupErrorEl.style.display = 'none';
});

// ── Onboarding Modal ──
const onboardingOverlayEl = document.getElementById('onboardingOverlay');
const onboardingNextBtn   = document.getElementById('onboardingNext');
const onboardingSkipBtn   = document.getElementById('onboardingSkip');
const onboardingSlides    = document.querySelectorAll('.onboarding-slide');
const onboardingDots      = document.querySelectorAll('.onboarding-dot');
let currentSlide = 0;
const TOTAL_SLIDES = onboardingSlides.length;

function showOnboarding() {
  currentSlide = 0;
  updateSlide();
  onboardingOverlayEl.style.display = 'flex';
}

function hideOnboarding() {
  onboardingOverlayEl.style.display = 'none';
  completeOnboarding();
}

function updateSlide() {
  onboardingSlides.forEach((s, i) => s.classList.toggle('active', i === currentSlide));
  onboardingDots.forEach((d, i) => d.classList.toggle('active', i === currentSlide));
  onboardingNextBtn.textContent = currentSlide === TOTAL_SLIDES - 1 ? 'Get Started ✦' : 'Next →';
}

onboardingNextBtn.addEventListener('click', () => {
  if (currentSlide < TOTAL_SLIDES - 1) {
    currentSlide++;
    updateSlide();
  } else {
    hideOnboarding();
  }
});

onboardingSkipBtn.addEventListener('click', hideOnboarding);

// Clicking dots jumps to that slide
onboardingDots.forEach((dot, i) => {
  dot.addEventListener('click', () => { currentSlide = i; updateSlide(); });
});

async function completeOnboarding() {
  try {
    await fetch('/api/complete-onboarding', { method: 'POST' });
  } catch (e) {
    // Non-blocking — if it fails, it'll just show again next time
  }
}

// ── Auth: Show / Hide Screens ──
function showApp(user) {
  currentUser = user;
  authOverlayEl.style.display = 'none';
  mainAppEl.style.display     = 'flex';
  userNameEl.textContent      = user.name || user.email;
  loadThreads();
  // Show onboarding for brand-new users who haven't seen it yet
  if (user.has_seen_onboarding === false) {
    showOnboarding();
  }
}

function showAuth() {
  mainAppEl.style.display     = 'none';
  authOverlayEl.style.display = 'flex';
  currentUser = null;
}

function showAuthError(el, msg) {
  el.textContent    = msg;
  el.style.display  = 'block';
}

// ── Auth: Login ──
loginBtn.addEventListener('click', handleLogin);
loginPassEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleLogin(); });
loginEmailEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') loginPassEl.focus(); });

async function handleLogin() {
  const email    = loginEmailEl.value.trim();
  const password = loginPassEl.value;
  if (!email || !password) {
    showAuthError(loginErrorEl, 'Please enter your email and password.');
    return;
  }
  loginErrorEl.style.display = 'none';
  loginBtn.disabled = true;
  loginBtn.textContent = 'Signing in…';

  try {
    const res  = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();

    if (data.success) {
      showApp(data.user);
    } else if (data.needs_signup) {
      // Pre-fill email and switch to signup
      signupEmailEl.value = email;
      signupPanel.style.display = 'block';
      loginPanel.style.display  = 'none';
      showAuthError(signupErrorEl, data.error);
    } else {
      showAuthError(loginErrorEl, data.error || 'Login failed. Please try again.');
    }
  } catch {
    showAuthError(loginErrorEl, 'Network error — please try again.');
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = 'Sign In';
  }
}

// ── Auth: Signup ──
signupBtn.addEventListener('click', handleSignup);
signupPassEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSignup(); });

async function handleSignup() {
  const name     = signupNameEl.value.trim();
  const email    = signupEmailEl.value.trim();
  const phone    = signupPhoneEl.value.trim();
  const password = signupPassEl.value;

  if (!name || !email || !password) {
    showAuthError(signupErrorEl, 'Please fill in all required fields.');
    return;
  }
  signupErrorEl.style.display = 'none';
  signupBtn.disabled = true;
  signupBtn.textContent = 'Creating account…';

  try {
    const res  = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, phone, password }),
    });
    const data = await res.json();

    if (data.success) {
      showApp(data.user);
    } else {
      showAuthError(signupErrorEl, data.error || 'Sign-up failed. Please try again.');
    }
  } catch {
    showAuthError(signupErrorEl, 'Network error — please try again.');
  } finally {
    signupBtn.disabled = false;
    signupBtn.textContent = 'Create Account';
  }
}

// ── Auth: Logout ──
logoutBtn.addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  startNewConversation();
  showAuth();
  // Reset login form
  loginEmailEl.value = '';
  loginPassEl.value  = '';
  loginErrorEl.style.display = 'none';
  loginPanel.style.display   = 'block';
  signupPanel.style.display  = 'none';
});

// ── Auth: Check session on load ──
async function initAuth() {
  try {
    const res  = await fetch('/api/auth/me');
    const data = await res.json();
    if (data.user) {
      showApp(data.user);
    } else {
      showAuth();
    }
  } catch {
    showAuth();
  }
}

// ── Hamburger / Sidebar Toggle ──
function openSidebar()  { sidebarEl.classList.add('open');    overlayEl.classList.add('active'); }
function closeSidebar() { sidebarEl.classList.remove('open'); overlayEl.classList.remove('active'); }
function toggleSidebar() { sidebarEl.classList.contains('open') ? closeSidebar() : openSidebar(); }

hamburgerEl.addEventListener('click', toggleSidebar);
overlayEl.addEventListener('click', closeSidebar);

document.querySelectorAll('.mode-btn, .starter-btn').forEach(el => {
  el.addEventListener('click', () => { if (window.innerWidth <= 768) closeSidebar(); });
});

// ── Configure marked.js ──
marked.setOptions({ breaks: true, gfm: true });

// ── Mode Switching ──
function setMode(mode) {
  if (mode === 'career') {
    showCareerHook();
    return;
  }
  setActiveMode(mode);
  showCareerProgress(false);
}

function setActiveMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
  modeBadgeEl.textContent = modeBadges[mode] || mode;
  modeDescEl.textContent  = modeDescriptions[mode] || '';
}

document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    setMode(btn.dataset.mode);
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
  showCareerProgress(false);
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

    // Handle auth expiry
    if (res.status === 401) {
      showAuth();
      addMessage('assistant', '⚠️ Your session expired — please sign in again.', currentMode);
      setLoading(false);
      return;
    }

    const data = await res.json();

    if (data.success) {
      if (!currentThreadId) {
        currentThreadId = data.thread_id;
      }
      await loadThreads();
      updateActiveThread(currentThreadId);
      if (data.thread) {
        threadTitleEl.textContent = data.thread.title;
      }
      addMessage('assistant', data.message, data.mode);
      // Update career progress if in career mode
      if (data.mode === 'career' && data.question_number !== undefined) {
        careerQuestionNumber = data.question_number;
        updateCareerProgress(data.question_number);
        showCareerProgress(true);
      }
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
    badge.textContent = { chat: '💬 Chat', document: '📄 Document', research: '🔍 Research', career: '🎯 Career Clarity' }[mode] || mode;
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
    if (res.status === 401) return; // not logged in yet
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
      item.addEventListener('click', () => { loadThread(thread.id); if (window.innerWidth <= 768) closeSidebar(); });
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

    // Restore career progress bar if this is a career thread
    if (t.mode === 'career') {
      setActiveMode('career');
      const userMsgCount = t.messages.filter(m => m.role === 'user').length;
      careerQuestionNumber = Math.min(userMsgCount, 8);
      updateCareerProgress(careerQuestionNumber);
      showCareerProgress(true);
    } else {
      showCareerProgress(false);
      setActiveMode(t.mode || 'chat');
    }
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

// ─── CAREER CLARITY MODE ───

let careerQuestionNumber = 0;

function showCareerHook() {
  document.getElementById('career-hook-overlay').classList.remove('hidden');
}

function hideCareerHook() {
  document.getElementById('career-hook-overlay').classList.add('hidden');
}

async function startCareerJourney() {
  hideCareerHook();

  // Switch mode visually
  setActiveMode('career');
  updateCareerProgress(0);
  showCareerProgress(true);

  try {
    const resp = await fetch('/api/career/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    // Handle auth expiry
    if (resp.status === 401) {
      showAuth();
      showCareerProgress(false);
      return;
    }

    const data = await resp.json();

    // Handle paywall
    if (resp.status === 403 && data.paywall) {
      showCareerProgress(false);
      showPaywall();
      return;
    }

    if (data.success) {
      currentThreadId = data.thread.id;
      careerQuestionNumber = 0;

      // Clear chat and show opening message
      messagesEl.innerHTML = '';
      welcomeEl.style.display = 'none';
      appendMessage('assistant', data.opening_message, 'career');
      updateCareerProgress(0);

      // Update thread list and title
      threadTitleEl.textContent = data.thread.title;
      loadThreads();
      updateActiveThread(data.thread.id);
    } else {
      addMessage('assistant', `⚠️ Error: ${data.error || 'Failed to start career session. Please try again.'}`, 'career');
    }
  } catch (err) {
    addMessage('assistant', '⚠️ Network error — please check your connection and try again.', 'career');
  }
}

function appendMessage(role, text, mode) {
  // Alias for addMessage — used by startCareerJourney
  addMessage(role, text, mode);
}

function updateCareerProgress(questionNum) {
  const fill  = document.getElementById('career-progress-fill');
  const label = document.getElementById('career-progress-label');
  if (!fill || !label) return;

  if (questionNum >= 8) {
    fill.style.width    = '100%';
    label.textContent   = '✅ Report Complete';
    label.style.color   = 'var(--accent2)';
  } else if (questionNum === 0) {
    fill.style.width    = '0%';
    label.textContent   = 'Starting your journey…';
    label.style.color   = '';
  } else {
    const pct           = (questionNum / 8) * 100;
    fill.style.width    = pct + '%';
    label.textContent   = `Question ${questionNum} of 8`;
    label.style.color   = '';
  }
}

function showCareerProgress(show) {
  const bar = document.getElementById('career-progress-bar');
  if (!bar) return;
  if (show) {
    bar.classList.remove('hidden');
  } else {
    bar.classList.add('hidden');
  }
}

// ─────────────────────────────────────────────
//  PAYWALL
// ─────────────────────────────────────────────

function showPaywall() {
  const overlay = document.getElementById('paywall-overlay');
  if (overlay) overlay.classList.remove('hidden');
}

function hidePaywall() {
  const overlay = document.getElementById('paywall-overlay');
  if (overlay) overlay.classList.add('hidden');
}

function goToCheckout() {
  // Redirect to Stripe via our server (passes user ID automatically)
  window.location.href = '/api/checkout/tier1';
}

// ── Init ──
initAuth();
