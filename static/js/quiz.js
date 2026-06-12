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

function onNameInput() {
  // reserved for future use
}


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

  // HoF score preview
  const hofPreview = document.getElementById('hof-score-preview');
  if (hofPreview && data.hof_score !== undefined) {
    hofPreview.textContent = `${data.hof_score}-point`;
  }

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

async function downloadCertificate() {
  const name = document.getElementById('shared-name').value.trim();
  const status = document.getElementById('cert-status');

  if (!name) {
    status.textContent = 'Please enter your name so we can put it on the certificate!';
    status.className = 'cert-status err';
    return;
  }

  status.textContent = 'Generating your certificate... 🖨️';
  status.className = 'cert-status';

  try {
    const res = await fetch('/api/download-certificate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });

    if (!res.ok) {
      const data = await res.json();
      status.textContent = `❌ ${data.error || 'Something went wrong'}`;
      status.className = 'cert-status err';
      return;
    }

    // Trigger download
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `GuidanceQuiz_Certificate_${name.replace(/\s+/g, '_')}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    status.textContent = '✅ Certificate downloaded! Go forth and brag.';
    status.className = 'cert-status ok';
  } catch (err) {
    status.textContent = '❌ Download failed. Please try again.';
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

// ============================================================
//  Hall of Fame
// ============================================================

const DIFF_LABELS = {
  'Guidance Guardian': 'guardian',
  'Guidance Champion': 'champion',
  'Guidance God': 'god'
};

const RANK_MEDALS = ['🥇', '🥈', '🥉'];

function showHallOfFame() {
  showScreen('screen-hof');
  loadHoF();
}

async function loadHoF() {
  document.getElementById('hof-loading').style.display = 'block';
  document.getElementById('hof-table-wrap').style.display = 'none';
  document.getElementById('hof-empty').style.display = 'none';

  try {
    const res = await fetch('/api/hof');
    const data = await res.json();

    document.getElementById('hof-loading').style.display = 'none';

    if (!data.entries || data.entries.length === 0) {
      document.getElementById('hof-empty').style.display = 'block';
      return;
    }

    const tbody = document.getElementById('hof-tbody');
    tbody.innerHTML = '';

    data.entries.forEach((e, i) => {
      const rank = i + 1;
      const medal = RANK_MEDALS[i] || `#${rank}`;
      const diffKey = DIFF_LABELS[e.difficulty] || 'guardian';
      const diffClass = `hof-diff-${diffKey}`;
      const rankClass = rank <= 3 ? `hof-rank-${rank}` : '';
      const date = e.submitted_at ? e.submitted_at.split(' ')[0] : '';

      tbody.innerHTML += `
        <tr>
          <td class="hof-rank ${rankClass}">${medal}</td>
          <td><strong>${escapeHtml(e.name)}</strong></td>
          <td class="hof-hof-score">${e.hof_score}</td>
          <td>${e.score_pct}% &nbsp;<span style="color:#999;font-size:12px;">(${e.correct}/${e.total})</span></td>
          <td><span class="hof-diff-badge ${diffClass}">${escapeHtml(e.difficulty)}</span></td>
          <td style="color:#999;font-size:12px;">${date}</td>
        </tr>
      `;
    });

    document.getElementById('hof-table-wrap').style.display = 'block';

    const totalText = data.total > 20
      ? `Showing top 20 of ${data.total} total entries`
      : `${data.total} engineer${data.total === 1 ? '' : 's'} on the board`;
    document.getElementById('hof-total-text').textContent = totalText;

  } catch (err) {
    document.getElementById('hof-loading').textContent = 'Failed to load — the Hall of Fame is having an existential crisis. Try refreshing.';
  }
}

async function submitToHoF() {
  const name = document.getElementById('shared-name').value.trim();
  const status = document.getElementById('hof-submit-status');

  if (!name) {
    status.textContent = 'You need to enter a name — anonymous glory is still just mediocrity.';
    status.className = 'cert-status err';
    return;
  }

  status.textContent = 'Submitting your legendary score...';
  status.className = 'cert-status';

  try {
    const res = await fetch('/api/hof-submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const data = await res.json();

    if (data.success) {
      const rankMsg = data.rank === 1
        ? "🥇 YOU'RE NUMBER ONE! Top of the leaderboard — frame this moment."
        : data.rank <= 3
        ? `🏅 Rank #${data.rank}! Podium finish. The guidance gods smile upon you.`
        : data.rank <= 10
        ? `⭐ Rank #${data.rank} — Top 10! Not bad at all, hotshot.`
        : `📋 Rank #${data.rank} — you're on the board! Every legend starts somewhere.`;

      status.textContent = `✅ Score of ${data.hof_score} submitted! ${rankMsg}`;
      status.className = 'cert-status ok';

      // Disable the button to prevent double submission
      const hofBtn = document.getElementById('btn-hof-submit');
      if (hofBtn) { hofBtn.disabled = true; hofBtn.textContent = '✅ Submitted!'; }
    } else {
      status.textContent = `❌ ${data.error}`;
      status.className = 'cert-status err';
    }
  } catch (err) {
    status.textContent = '❌ Failed to submit. Please try again.';
    status.className = 'cert-status err';
  }
}
