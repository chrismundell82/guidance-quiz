// ============================================================
//  AtkinsRéalis Guidance Notes Quiz — Frontend Logic
// ============================================================

let questions = [];
let currentIndex = 0;
let answers = {};
let quizResult = null;

const DIFFICULTY_LABELS = {
  guardian: 'Guidance Guardian 🛡️',
  champion: 'Guidance Champion ⚔️',
  god: 'Guidance God ⚡'
};

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) {
    el.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

async function startQuiz() {
  const difficulty = document.querySelector('input[name="difficulty"]:checked').value;
  const count = parseInt(document.querySelector('input[name="count"]:checked').value);

  showScreen('screen-loading');

  try {
    const res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ difficulty, count })
    });
    const data = await res.json();

    if (!data.questions || !data.questions.length) {
      alert('No questions found! The guidance notes have escaped. Please try again.');
      showScreen('screen-setup');
      return;
    }

    questions = data.questions;
    currentIndex = 0;
    answers = {};

    document.getElementById('q-total').textContent = questions.length;
    document.getElementById('quiz-diff-badge').textContent = DIFFICULTY_LABELS[difficulty] || difficulty;

    renderQuestion(0);
    showScreen('screen-quiz');
  } catch (err) {
    console.error(err);
    alert('Something went wrong. The guidance notes are rebelling. Please try again.');
    showScreen('screen-setup');
  }
}

function renderQuestion(index) {
  const q = questions[index];
  if (!q) return;

  document.getElementById('q-current').textContent = index + 1;
  document.getElementById('question-label').textContent = `Question ${index + 1}`;
  document.getElementById('question-text').textContent = q.question;

  const total = questions.length;
  document.getElementById('progress-fill').style.width = `${((index + 1) / total) * 100}%`;

  const optList = document.getElementById('options-list');
  optList.innerHTML = '';

  q.options.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'option-btn' + (answers[index] === opt.key ? ' selected' : '');
    btn.setAttribute('data-key', opt.key);
    btn.innerHTML = `<span class="option-key">${opt.key}</span><span>${escapeHtml(opt.text)}</span>`;
    btn.addEventListener('click', () => selectOption(index, opt.key));
    optList.appendChild(btn);
  });

  // Navigation buttons
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  const btnSubmit = document.getElementById('btn-submit');

  btnPrev.disabled = index === 0;

  if (index === questions.length - 1) {
    btnNext.style.display = 'none';
    btnSubmit.style.display = 'inline-flex';
  } else {
    btnNext.style.display = 'inline-flex';
    btnSubmit.style.display = 'none';
  }
}

function selectOption(questionIndex, key) {
  answers[questionIndex] = key;
  document.querySelectorAll('.option-btn').forEach(btn => {
    btn.classList.toggle('selected', btn.getAttribute('data-key') === key);
  });
}

function nextQuestion() {
  if (currentIndex < questions.length - 1) {
    currentIndex++;
    renderQuestion(currentIndex);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

function prevQuestion() {
  if (currentIndex > 0) {
    currentIndex--;
    renderQuestion(currentIndex);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}

async function submitQuiz() {
  // Check for unanswered questions
  const unanswered = questions.filter((_, i) => !answers[i]);
  if (unanswered.length > 0) {
    const go = confirm(`You've left ${unanswered.length} question(s) unanswered. That's very on-brand for a Monday. Submit anyway?`);
    if (!go) return;
  }

  showScreen('screen-loading');

  try {
    const res = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers })
    });
    const data = await res.json();
    quizResult = data;
    renderResults(data);
    showScreen('screen-results');
    setTimeout(() => launchFireworks(data.verdict), 400);
  } catch (err) {
    console.error(err);
    alert('Something exploded. Probably a web panel. Please try again.');
    showScreen('screen-quiz');
  }
}

function renderResults(data) {
  // Badge
  const badge = document.getElementById('results-badge');
  const titles = {
    outstanding: '🏆 Outstanding Engineer!',
    satisfactory: '👍 Satisfactory Performance',
    poor: '😬 Needs Improvement'
  };
  badge.textContent = titles[data.verdict] || '';
  badge.className = `results-badge ${data.verdict}`;

  // Image
  document.getElementById('results-image').src = `/static/images/${data.image}`;

  // Title
  const diffName = data.difficulty || '';
  document.getElementById('results-title').textContent = diffName + ' Complete!';

  // Score
  document.getElementById('results-score').innerHTML =
    `${data.pct}<span>%</span><br><span style="font-size:0.4em;font-weight:400;">${data.score} / ${data.total} correct</span>`;

  // Message
  document.getElementById('results-message').textContent = data.message;

  // Breakdown
  const breakdown = document.getElementById('results-breakdown');
  if (data.results && data.results.length) {
    const list = data.results.map((r, i) => {
      const cls = r.is_correct ? 'correct' : 'wrong';
      const userOpt = r.options.find(o => o.key === r.user);
      const corrOpt = r.options.find(o => o.key === r.correct);
      return `<div class="breakdown-item ${cls}">
        <div class="bi-q">${i + 1}. ${escapeHtml(r.question)}</div>
        <div class="bi-ans">
          ${r.is_correct
            ? `✅ Correct: ${escapeHtml(corrOpt ? corrOpt.text : r.correct)}`
            : `❌ You answered: ${escapeHtml(userOpt ? userOpt.text : (r.user || 'Not answered'))} &nbsp;|&nbsp; ✅ Correct: ${escapeHtml(corrOpt ? corrOpt.text : r.correct)}`
          }
        </div>
      </div>`;
    }).join('');

    breakdown.innerHTML = `
      <div class="breakdown-title" onclick="toggleBreakdown(this)">
        📋 See Question Breakdown <span id="breakdown-arrow">▼</span>
      </div>
      <div class="breakdown-list" id="breakdown-list">${list}</div>
    `;
  }
}

function toggleBreakdown(el) {
  const list = document.getElementById('breakdown-list');
  const arrow = document.getElementById('breakdown-arrow');
  if (list) {
    list.classList.toggle('open');
    if (arrow) arrow.textContent = list.classList.contains('open') ? '▲' : '▼';
  }
}

function launchFireworks(verdict) {
  if (verdict === 'poor') return; // No fireworks for shame

  const container = document.getElementById('fireworks-container');
  container.innerHTML = '';

  const colours = ['#E4002B', '#002147', '#FFD700', '#00C851', '#FF6D00', '#AA00FF'];
  const count = verdict === 'outstanding' ? 80 : 40;

  for (let i = 0; i < count; i++) {
    setTimeout(() => {
      const dot = document.createElement('div');
      dot.className = 'firework';
      const startX = 10 + Math.random() * 80;
      const startY = 10 + Math.random() * 60;
      const tx = (Math.random() - 0.5) * 300 + 'px';
      const ty = (Math.random() - 0.5) * 300 + 'px';
      dot.style.cssText = `
        left: ${startX}%;
        top: ${startY}%;
        background: ${colours[Math.floor(Math.random() * colours.length)]};
        --tx: ${tx};
        --ty: ${ty};
        width: ${4 + Math.random() * 8}px;
        height: ${4 + Math.random() * 8}px;
        animation-duration: ${0.8 + Math.random() * 0.8}s;
        animation-delay: ${Math.random() * 0.6}s;
      `;
      container.appendChild(dot);
    }, Math.random() * 800);
  }

  setTimeout(() => { container.innerHTML = ''; }, 3000);
}

async function sendCertificate() {
  const name = document.getElementById('cert-name').value.trim();
  const email = document.getElementById('cert-email').value.trim();
  const status = document.getElementById('cert-status');

  if (!email) {
    status.textContent = 'Please enter your email address, clever clogs.';
    status.className = 'cert-status err';
    return;
  }

  status.textContent = 'Dispatching your certificate via carrier pigeon... (actually SMTP)';
  status.className = 'cert-status';

  try {
    const res = await fetch('/api/send-certificate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email })
    });
    const data = await res.json();
    if (data.success) {
      status.textContent = '✅ Certificate sent! Check your inbox (and spam, just in case).';
      status.className = 'cert-status ok';
    } else {
      status.textContent = `❌ Couldn't send: ${data.error || 'Unknown error. The email gods are unhappy.'}`;
      status.className = 'cert-status err';
    }
  } catch (err) {
    status.textContent = '❌ Network error. Please try again.';
    status.className = 'cert-status err';
  }
}

function retakeQuiz() {
  questions = [];
  answers = {};
  currentIndex = 0;
  quizResult = null;
  showScreen('screen-setup');
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
