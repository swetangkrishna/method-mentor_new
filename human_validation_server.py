"""
human_validation_server.py

Flask server — human plays the learner, agent plays the teacher.
All sessions, turns, skill uses, surveys, and rewards saved to SQLite.

Run:
    python human_validation_server.py
    Open: http://localhost:6767
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent))

from skill_loader import load_all_skills
from scenarios import SCENARIOS, SURVEY_QUESTIONS
from agent import agent_turn
from reward import calculate_reward, skill_sequence_stats, _band
from database import Database
from model_config import get_config
from stage_tracker import StageTracker
from stages import FINAL_STAGE, stage_name

app    = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "pedagogy-rl-2025")

SKILLS = load_all_skills()
DB     = Database()
CFG    = get_config()

# In-memory session store (complement to DB for live state)
SESSIONS: dict = {}


# ── HTML pages ────────────────────────────────────────────────────────────────

def _scenario_page() -> str:
    cards = ""
    for key, sc in SCENARIOS.items():
        role_color = "#e1f5ee" if sc["role"] == "tutor" else "#eeedfe"
        role_text  = "#085041" if sc["role"] == "tutor" else "#3c3489"
        cards += f"""
<div class="card" onclick="location.href='/chat/{sc['id']}'">
  <div class="card-top">
    <h2>{sc['topic']}</h2>
    <span class="badge" style="background:{role_color};color:{role_text}">{sc['role'].title()}</span>
    <span class="badge muted">max {sc['max_turns']} turns</span>
  </div>
  <p>{sc['task_description']}</p>
</div>"""

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pedagogical RL — Human Validation</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f5f0;color:#1a1a18;min-height:100vh}}
.container{{max-width:740px;margin:0 auto;padding:48px 24px}}
h1{{font-size:22px;font-weight:600;margin-bottom:6px}}
.sub{{font-size:13px;color:#666;line-height:1.6;margin-bottom:28px}}
.info{{background:#fef3e2;border:1px solid #f9d68a;border-radius:10px;
       padding:14px 18px;font-size:13px;color:#633806;line-height:1.6;margin-bottom:28px}}
.info strong{{display:block;margin-bottom:4px;font-size:14px}}
.card{{background:#fff;border:1px solid #e2e0d8;border-radius:12px;
       padding:20px 24px;margin-bottom:14px;cursor:pointer;transition:box-shadow .15s}}
.card:hover{{box-shadow:0 4px 16px rgba(0,0,0,.08);border-color:#b5b2a8}}
.card-top{{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}}
.card h2{{font-size:15px;font-weight:500;flex:1}}
.card p{{font-size:13px;color:#666;line-height:1.5}}
.badge{{font-size:11px;font-weight:500;padding:2px 9px;border-radius:10px}}
.muted{{background:#f1efe8;color:#5f5e5a}}
.nav{{display:flex;gap:12px;margin-bottom:24px}}
.nav a{{font-size:13px;color:#666;text-decoration:none;padding:6px 14px;
        border:1px solid #e2e0d8;border-radius:8px;background:#fff}}
.nav a:hover{{background:#f5f5f0}}
</style></head><body>
<div class="container">
<h1>Pedagogical RL — Human Validation</h1>
<p class="sub">You play the learner. The AI agent plays the teacher using its 16-skill pedagogical library.</p>
<div class="info">
  <strong>Your role as learner</strong>
  Chat naturally. Be confused where it makes sense. Push back if explanations don't land.
  When you feel you've achieved the learning goal, click "I've got it".
  After the chat, fill a short survey — your rating becomes part of the RL reward signal.
</div>
<div class="nav">
  <a href="/results">📊 Results dashboard</a>
  <a href="/api/db-stats">🗄 DB stats</a>
</div>
<p style="font-size:13px;color:#666;margin-bottom:14px">Choose a scenario:</p>
{cards}
</div></body></html>"""


def _chat_page(sc: dict) -> str:
    survey_html = _build_survey_html()
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{sc['topic']} — Pedagogy RL</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f5f0;color:#1a1a18;height:100vh;display:flex;flex-direction:column}}
.hdr{{background:#fff;border-bottom:1px solid #e2e0d8;padding:12px 20px;
      display:flex;align-items:center;gap:12px;flex-shrink:0}}
.hdr-info h1{{font-size:14px;font-weight:500}}
.hdr-info p{{font-size:11px;color:#888}}
#turnCounter{{margin-left:auto;font-size:12px;color:#888}}
#statusPill{{font-size:11px;font-weight:500;padding:3px 10px;border-radius:10px;
            background:#e1f5ee;color:#085041}}
.goal{{background:#fef3e2;border-bottom:1px solid #f9d68a;padding:9px 20px;
       font-size:12px;color:#633806;line-height:1.5;flex-shrink:0}}
.messages{{flex:1;overflow-y:auto;padding:18px 20px;display:flex;flex-direction:column;gap:12px}}
.msg{{display:flex;gap:9px;max-width:680px}}
.msg.agent{{align-self:flex-start}}
.msg.user{{align-self:flex-end;flex-direction:row-reverse}}
.av{{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;
     justify-content:center;font-size:12px;font-weight:600;flex-shrink:0;margin-top:2px}}
.av.agent{{background:#e6f1fb;color:#0c447c}}
.av.user{{background:#eeedfe;color:#3c3489}}
.bubble{{padding:10px 14px;border-radius:14px;font-size:13.5px;line-height:1.6;max-width:540px}}
.agent .bubble{{background:#fff;border:1px solid #e2e0d8;border-top-left-radius:4px}}
.user  .bubble{{background:#1a1a18;color:#f5f5f0;border-top-right-radius:4px}}
.skill-tag{{font-size:10px;color:#aaa;margin-top:3px;padding-left:39px}}
.thinking{{opacity:.5;font-style:italic}}
.input-area{{background:#fff;border-top:1px solid #e2e0d8;padding:14px 20px;flex-shrink:0}}
.input-row{{display:flex;gap:9px;align-items:flex-end}}
textarea{{flex:1;border:1px solid #e2e0d8;border-radius:10px;padding:9px 13px;
          font-size:13.5px;font-family:inherit;resize:none;min-height:42px;
          max-height:110px;outline:none;transition:border-color .15s}}
textarea:focus{{border-color:#1a1a18}}
button{{padding:9px 18px;border-radius:10px;font-size:13.5px;font-weight:500;
        cursor:pointer;border:none;transition:opacity .15s}}
button:disabled{{opacity:.4;cursor:default}}
.btn-send{{background:#1a1a18;color:#f5f5f0}}
.btn-send:hover:not(:disabled){{opacity:.85}}
.action-row{{margin-top:9px;display:flex;gap:8px;flex-wrap:wrap}}
.btn-ok{{background:#e1f5ee;color:#085041;border:1px solid #9fe1cb;padding:7px 14px}}
.btn-end{{background:#f1efe8;color:#5f5e5a;border:1px solid #d4d2ca;padding:7px 14px}}
.overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);
          z-index:100;align-items:center;justify-content:center}}
.overlay.show{{display:flex}}
.box{{background:#fff;border-radius:14px;padding:26px 30px;max-width:540px;
      width:90%;max-height:90vh;overflow-y:auto}}
.box h2{{font-size:17px;font-weight:600;margin-bottom:6px}}
.box .intro{{font-size:12.5px;color:#666;margin-bottom:22px;line-height:1.5}}
.q-block{{margin-bottom:18px}}
.q-block label{{display:block;font-size:13.5px;font-weight:500;margin-bottom:7px;line-height:1.4}}
.rating-row{{display:flex;gap:7px}}
.rb{{width:42px;height:42px;border-radius:8px;border:1px solid #e2e0d8;
     background:#fff;font-size:15px;font-weight:500;cursor:pointer;transition:all .15s}}
.rb.sel{{background:#1a1a18;color:#fff;border-color:#1a1a18}}
.rb:hover:not(.sel){{background:#f5f5f0}}
.scale-lbl{{display:flex;justify-content:space-between;font-size:10px;color:#888;margin-top:3px}}
textarea.oq{{width:100%;border:1px solid #e2e0d8;border-radius:8px;padding:9px 12px;
             font-size:13px;font-family:inherit;min-height:72px;resize:vertical;outline:none}}
textarea.oq:focus{{border-color:#1a1a18}}
.btn-submit{{width:100%;margin-top:6px;padding:13px;background:#1a1a18;color:#fff;font-size:14px}}
.result-box{{text-align:center;max-width:440px}}
.result-box h2{{font-size:19px;font-weight:600;margin-bottom:8px}}
.big-reward{{font-size:52px;font-weight:700;margin:14px 0 4px}}
.band{{font-size:14px;font-weight:500;margin-bottom:18px}}
.breakdown{{text-align:left;font-size:12.5px;color:#555;background:#f5f5f0;
            border-radius:8px;padding:12px 16px}}
.breakdown div{{margin-bottom:3px}}
.btn-done{{margin-top:18px;background:#1a1a18;color:#fff;padding:11px 26px;font-size:13.5px}}
</style></head>
<body data-scenario="{sc['id']}">
<div class="hdr">
  <div class="hdr-info">
    <h1>{sc['topic']}</h1>
    <p>{sc['role'].title()} · {sc['id']}</p>
  </div>
  <span id="turnCounter">Turn 0 / {sc['max_turns']}</span>
  <span id="statusPill">Active</span>
</div>
<div class="goal"><strong>Your goal:</strong> {sc['learner_persona']['learning_goal']}</div>
<div class="messages" id="messages"></div>
<div class="input-area">
  <div class="input-row">
    <textarea id="inp" placeholder="Type your message…" rows="1"
              onkeydown="handleKey(event)"></textarea>
    <button class="btn-send" id="sendBtn" onclick="send()">Send</button>
  </div>
  <div class="action-row">
    <button class="btn-ok"  onclick="endSession(true)">✓ I've got it — task complete</button>
    <button class="btn-end" onclick="endSession(false)">End session</button>
  </div>
</div>

<div class="overlay" id="surveyOverlay">
  <div class="box">
    <h2>Session feedback</h2>
    <p class="intro">Rate your experience honestly — this becomes part of the RL reward signal.</p>
    <form id="surveyForm">
      {survey_html}
      <button type="button" class="btn-submit" id="submitBtn" onclick="submitSurvey()">
        Submit feedback
      </button>
    </form>
  </div>
</div>

<div class="overlay" id="resultOverlay">
  <div class="box result-box">
    <h2>Session saved ✓</h2>
    <div class="big-reward" id="rewardVal">—</div>
    <div class="band" id="rewardBand">—</div>
    <div class="breakdown" id="breakdown"></div>
    <button class="btn-done" onclick="location.href='/'">← Choose another scenario</button>
    <button class="btn-done" style="margin-left:8px;background:#e6f1fb;color:#0c447c"
            onclick="location.href='/results'">📊 See all results</button>
  </div>
</div>

<script>
const scenarioId = document.body.dataset.scenario;
const maxTurns   = {sc['max_turns']};
let sessionId = null, turnCount = 0, ended = false;
const ratings = {{}};

async function startSession() {{
  const r = await post('/api/start', {{scenario_id: scenarioId}});
  sessionId = r.session_id;
  addMsg('agent', r.agent_message, r.skill_used);
  turnCount = 1; updateCounter();
}}

function addMsg(role, text, skill) {{
  const msgs = document.getElementById('messages');
  const wrap = Object.assign(document.createElement('div'), {{className:`msg ${{role}}`}});
  const av   = Object.assign(document.createElement('div'), {{className:`av ${{role}}`, textContent: role==='agent'?'AI':'You'}});
  const bub  = Object.assign(document.createElement('div'), {{className:'bubble', textContent:text}});
  wrap.append(av, bub); msgs.appendChild(wrap);
  if (role==='agent' && skill) {{
    const tag = Object.assign(document.createElement('div'), {{className:'skill-tag', textContent:`skill: ${{skill}}`}});
    msgs.appendChild(tag);
  }}
  msgs.scrollTop = msgs.scrollHeight;
}}

function showThinking() {{
  const msgs = document.getElementById('messages');
  const d = document.createElement('div');
  d.className='msg agent'; d.id='thinking';
  d.innerHTML='<div class="av agent">AI</div><div class="bubble thinking">Thinking…</div>';
  msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight;
}}

function updateCounter() {{
  document.getElementById('turnCounter').textContent = `Turn ${{turnCount}} / ${{maxTurns}}`;
}}

function handleKey(e) {{ if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();send();}} }}

async function send() {{
  if(ended) return;
  const inp  = document.getElementById('inp');
  const text = inp.value.trim();
  if(!text) return;
  document.getElementById('sendBtn').disabled = true;
  inp.value = ''; inp.style.height='42px';
  addMsg('user', text);
  showThinking();
  try {{
    const r = await post('/api/message', {{session_id:sessionId, message:text}});
    document.getElementById('thinking')?.remove();
    if(r.error) {{ addMsg('agent', 'Error: '+r.error, null); }}
    else {{
      addMsg('agent', r.agent_message, r.skill_used);
      turnCount = r.turn_count; updateCounter();
      if(r.max_turns_reached) {{ document.getElementById('statusPill').textContent='Max turns'; endSession(false); }}
    }}
  }} catch(e) {{
    document.getElementById('thinking')?.remove();
    addMsg('agent', 'Network error — try again.', null);
  }}
  document.getElementById('sendBtn').disabled = false;
  document.getElementById('inp').focus();
}}

async function endSession(solved) {{
  if(ended) return; ended = true;
  document.getElementById('sendBtn').disabled = true;
  document.querySelectorAll('.btn-ok,.btn-end').forEach(b=>b.disabled=true);
  document.getElementById('statusPill').textContent = solved ? 'Complete' : 'Ended';
  await post('/api/end', {{session_id:sessionId, task_solved:solved}});
  document.getElementById('surveyOverlay').classList.add('show');
}}

function selectRating(qId, val) {{
  ratings[qId] = val;
  document.querySelectorAll(`.rg-${{qId}}`).forEach(b=>b.classList.toggle('sel', +b.dataset.v===val));
}}

async function submitSurvey() {{
  for(const q of ['Q1','Q2','Q3','Q4','Q5']) {{
    if(!ratings[q]) {{ alert('Please rate question '+q); return; }}
  }}
  const survey = {{}};
  for(const q of ['Q1','Q2','Q3','Q4','Q5']) survey[q] = {{score:ratings[q], comment:''}};
  survey['Q_open'] = {{score:null, comment: document.getElementById('Q_open_txt')?.value||''}};
  document.getElementById('submitBtn').disabled = true;
  const r = await post('/api/survey', {{session_id:sessionId, survey}});
  document.getElementById('surveyOverlay').classList.remove('show');
  document.getElementById('rewardVal').textContent  = r.reward.reward.toFixed(3);
  document.getElementById('rewardBand').textContent = r.reward_band;
  document.getElementById('breakdown').innerHTML =
    `<div>Task solved: ${{r.task_solved?'✓ Yes':'✗ No'}}</div>`+
    `<div>Turns: ${{r.turns_used}} / ${{maxTurns}}</div>`+
    `<div>Survey mean: ${{r.reward.components.survey_score_raw_mean.toFixed(1)}} / 5</div>`+
    `<div>Efficiency: ${{(r.reward.components.efficiency_score*100).toFixed(0)}}%</div>`+
    `<div style="margin-top:8px;font-size:11px;color:#aaa">Run ID: ${{r.run_id}}</div>`;
  document.getElementById('resultOverlay').classList.add('show');
}}

async function post(url, body) {{
  const r = await fetch(url, {{method:'POST',
    headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(body)}});
  return r.json();
}}

document.getElementById('inp').addEventListener('input', function(){{
  this.style.height='auto'; this.style.height=Math.min(this.scrollHeight,110)+'px';
}});

startSession();
</script></body></html>"""


def _results_page() -> str:
    rows = DB.session_summary_table()
    table_rows = ""
    for r in rows:
        reward = f"{r['total_reward']:.3f}" if r['total_reward'] is not None else "—"
        survey = f"{r['mean_survey']:.1f}" if r['mean_survey'] is not None else "—"
        mode_badge = "🤖" if r['mode'] == 'automated' else "👤"
        table_rows += (
            f"<tr>"
            f"<td>{mode_badge} {r['mode']}</td>"
            f"<td>{r['scenario_id']}</td>"
            f"<td>{'✓' if r['task_solved'] else '✗'}</td>"
            f"<td>{r['total_turns']}</td>"
            f"<td><strong>{reward}</strong></td>"
            f"<td>{r['reward_band'] or '—'}</td>"
            f"<td>{survey}</td>"
            f"<td style='font-size:11px;color:#888'>{r['model'] or '—'}</td>"
            f"<td style='font-size:10px;color:#aaa'>{r['started_at'][:16] if r['started_at'] else ''}</td>"
            f"</tr>"
        )
    skill_freq = DB.skill_frequency()
    skill_rows = ""
    for sf in skill_freq:
        avg = f"{sf['avg_reward']:.3f}" if sf['avg_reward'] else "—"
        skill_rows += f"<tr><td>{sf['skill_name']}</td><td>{sf['uses']}</td><td>{avg}</td></tr>"

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><title>Results — Pedagogy RL</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#f5f5f0;color:#1a1a18}}
.container{{max-width:1100px;margin:0 auto;padding:36px 24px}}
h1{{font-size:20px;font-weight:600;margin-bottom:4px}}
.sub{{font-size:13px;color:#666;margin-bottom:28px}}
.nav a{{font-size:13px;color:#666;text-decoration:none;padding:6px 14px;
        border:1px solid #e2e0d8;border-radius:8px;background:#fff;margin-right:8px}}
.nav{{margin-bottom:24px}}
h2{{font-size:15px;font-weight:500;margin:28px 0 12px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;
       overflow:hidden;border:1px solid #e2e0d8;font-size:13px}}
th{{padding:9px 12px;text-align:left;font-weight:500;font-size:11px;color:#888;
    border-bottom:1px solid #e2e0d8;background:#fafaf8;text-transform:uppercase}}
td{{padding:9px 12px;border-bottom:1px solid #f0ede8;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#fafaf8}}
.empty{{text-align:center;padding:32px;color:#aaa;font-size:13px}}
</style></head><body>
<div class="container">
<h1>Results Dashboard</h1>
<p class="sub">All sessions from the SQLite database — automated (🤖) and human validation (👤)</p>
<div class="nav">
  <a href="/">← Scenarios</a>
  <a href="/api/db-stats">DB stats JSON</a>
  <a href="/api/results">Results JSON</a>
</div>

<h2>Sessions ({len(rows)})</h2>
<table>
<thead><tr>
  <th>Mode</th><th>Scenario</th><th>Solved</th><th>Turns</th>
  <th>Reward</th><th>Band</th><th>Survey</th><th>Model</th><th>Time</th>
</tr></thead>
<tbody>
{"".join(table_rows) if table_rows else '<tr><td colspan="9" class="empty">No completed sessions yet. Run an experiment or start a chat session.</td></tr>'}
</tbody></table>

<h2>Skill Usage (across all sessions)</h2>
<table>
<thead><tr><th>Skill</th><th>Uses</th><th>Avg reward</th></tr></thead>
<tbody>
{"".join(skill_rows) if skill_rows else '<tr><td colspan="3" class="empty">No skill data yet.</td></tr>'}
</tbody></table>
</div></body></html>"""


def _build_survey_html() -> str:
    blocks = []
    for q in SURVEY_QUESTIONS:
        if q["scale"] == "open text":
            blocks.append(f"""
<div class="q-block">
  <label>{q['question']}</label>
  <textarea class="oq" id="Q_open_txt" placeholder="Your thoughts…"></textarea>
</div>""")
        else:
            parts = q["scale"].split(" to ")
            lo = parts[0].strip() if parts else ""
            hi = parts[1].strip() if len(parts) > 1 else ""
            btns = "".join(
                f'<button type="button" class="rb rg-{q["id"]}" data-v="{i}" '
                f'onclick="selectRating(\'{q["id"]}\',{i})">{i}</button>'
                for i in range(1, 6)
            )
            blocks.append(f"""
<div class="q-block">
  <label>{q['question']}</label>
  <div class="rating-row">{btns}</div>
  <div class="scale-lbl"><span>{lo}</span><span>{hi}</span></div>
</div>""")
    return "\n".join(blocks)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return _scenario_page()


@app.route("/results")
def results_page():
    return _results_page()


@app.route("/chat/<scenario_id>")
def chat(scenario_id: str):
    sc = next((s for s in SCENARIOS.values() if s["id"] == scenario_id), None)
    if not sc:
        return f"Scenario '{scenario_id}' not found.", 404
    return _chat_page(sc)


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.json
    sc   = next((s for s in SCENARIOS.values() if s["id"] == data.get("scenario_id")), None)
    if not sc:
        return jsonify({"error": "Scenario not found"}), 404

    ts         = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    session_id = f"HV_{sc['id']}_{ts}_{uuid.uuid4().hex[:6]}"

    DB.create_session(
        session_id    = session_id,
        scenario_id   = sc["id"],
        scenario_topic= sc["topic"],
        mode          = "human_validation",
        backend       = CFG["backend"],
        model         = CFG["model"],
        max_turns     = sc["max_turns"],
        persona_name  = sc["learner_persona"]["name"],
    )

    # Agent goes first — now stage-aware
    history: list     = []
    skill_seq: list   = []
    tracker = StageTracker()
    comfort_zone = sc.get("stage_profile", {}).get("comfort_zone")
    stage4_alts  = sc.get("stage_profile", {}).get("stage4_alternatives")

    stage_context  = tracker.build_stage_context(
        comfort_zone=comfort_zone, stage4_alternatives=stage4_alts)
    expected_stage = tracker.expected_stage()
    stage_before   = tracker.current_stage

    ar = agent_turn(SKILLS, sc, history, [], 1,
                    stage_context=stage_context, expected_stage=expected_stage)
    history.append({"role": "assistant", "content": ar["response"]})
    skill_seq.append(ar["skill_name"])

    stage_now = tracker.advance(
        ar["declared_stage"], ar["stage_complete"],
        response_text=ar["response"], stage4_alternatives=stage4_alts)

    t_id = DB.log_turn(session_id, 1, "agent", ar["response"],
                       agent_declared_solved=ar["task_solved"])
    DB.log_skill_use(session_id, t_id, 1, ar["skill_name"], ar["reasoning"])
    try:
        DB.log_stage(session_id, t_id, 1, stage_now,
                     declared=ar["declared_stage"], expected=expected_stage,
                     stage_before=stage_before, stage_complete=ar["stage_complete"],
                     advanced=(stage_now > stage_before), forced=False,
                     header_dropped=ar.get("stage_header_dropped", False),
                     skill=ar["skill_name"], reasoning=ar["reasoning"],
                     stage4_presented=tracker.stage4_alternatives_presented)
    except Exception:
        pass

    SESSIONS[session_id] = {
        "session_id":  session_id,
        "scenario":    sc,
        "history":     history,
        "skill_seq":   skill_seq,
        "turn_count":  1,
        "task_solved": False,
        "ended":       False,
        "tracker":     tracker,
        "comfort_zone": comfort_zone,
        "stage4_alts": stage4_alts,
    }

    return jsonify({
        "session_id":   session_id,
        "agent_message": ar["response"],
        "skill_used":   ar["skill_name"],
        "turn_count":   1,
        "stage":        stage_now,
        "stage_name":   stage_name(stage_now),
        "final_stage":  FINAL_STAGE,
    })


@app.route("/api/message", methods=["POST"])
def api_message():
    data       = request.json
    session_id = data.get("session_id")
    msg        = data.get("message", "").strip()
    sess       = SESSIONS.get(session_id)
    if not sess: return jsonify({"error": "Session not found"}), 404
    if sess["ended"]: return jsonify({"error": "Session ended"}), 400

    sc      = sess["scenario"]
    history = sess["history"]
    history.append({"role": "user", "content": msg})
    DB.log_turn(session_id, sess["turn_count"], "human", msg)
    sess["turn_count"] += 1

    if sess["turn_count"] > sc["max_turns"]:
        sess["ended"] = True
        return jsonify({"agent_message": "Max turns reached — please submit feedback.",
                        "skill_used": None, "turn_count": sess["turn_count"],
                        "max_turns_reached": True})

    ar = agent_turn(SKILLS, sc, history, sess["skill_seq"], sess["turn_count"],
                    stage_context=tracker.build_stage_context(
                        comfort_zone=sess["comfort_zone"],
                        stage4_alternatives=sess["stage4_alts"]),
                    expected_stage=tracker.expected_stage())
    history.append({"role": "assistant", "content": ar["response"]})
    sess["skill_seq"].append(ar["skill_name"])

    forced_before = tracker.forced_advances
    stage_before  = tracker.current_stage
    stage_now = tracker.advance(
        ar["declared_stage"], ar["stage_complete"],
        response_text=ar["response"], stage4_alternatives=sess["stage4_alts"])
    was_forced = tracker.forced_advances > forced_before

    t_id = DB.log_turn(session_id, sess["turn_count"], "agent", ar["response"],
                       agent_declared_solved=ar["task_solved"])
    DB.log_skill_use(session_id, t_id, sess["turn_count"], ar["skill_name"], ar["reasoning"])
    try:
        DB.log_stage(session_id, t_id, sess["turn_count"], stage_now,
                     declared=ar["declared_stage"], expected=tracker.current_stage,
                     stage_before=stage_before, stage_complete=ar["stage_complete"],
                     advanced=(stage_now > stage_before), forced=was_forced,
                     header_dropped=ar.get("stage_header_dropped", False),
                     skill=ar["skill_name"], reasoning=ar["reasoning"],
                     stage4_presented=tracker.stage4_alternatives_presented)
    except Exception:
        pass

    if ar["task_solved"]:
        sess["task_solved"] = True

    return jsonify({
        "agent_message":        ar["response"],
        "skill_used":           ar["skill_name"],
        "turn_count":           sess["turn_count"],
        "max_turns_reached":    sess["turn_count"] >= sc["max_turns"],
        "agent_declared_solved": ar["task_solved"],
        "stage":                stage_now,
        "stage_name":           stage_name(stage_now),
        "final_stage":          FINAL_STAGE,
        "stage_forced":         was_forced,
    })


@app.route("/api/end", methods=["POST"])
def api_end():
    data       = request.json
    session_id = data.get("session_id")
    sess       = SESSIONS.get(session_id)
    if not sess: return jsonify({"error": "Session not found"}), 404
    sess["task_solved"] = data.get("task_solved", False) or sess["task_solved"]
    sess["ended"]       = True
    return jsonify({"status": "ended", "task_solved": sess["task_solved"]})


@app.route("/api/survey", methods=["POST"])
def api_survey():
    data       = request.json
    session_id = data.get("session_id")
    survey     = data.get("survey", {})
    sess       = SESSIONS.get(session_id)
    if not sess: return jsonify({"error": "Session not found"}), 404

    sc          = sess["scenario"]
    turns_used  = sess["turn_count"]
    task_solved = sess["task_solved"]

    DB.log_survey(session_id, survey, respondent_type="human")
    reward = calculate_reward(task_solved, survey, turns_used, sc["max_turns"])
    DB.log_reward(session_id, reward)
    DB.complete_session(session_id, task_solved, turns_used)

    return jsonify({
        "run_id":       session_id,
        "reward":       reward,
        "reward_band":  reward["reward_band"],
        "task_solved":  task_solved,
        "turns_used":   turns_used,
    })


@app.route("/api/results")
def api_results():
    return jsonify({"sessions": DB.session_summary_table()})


@app.route("/api/db-stats")
def api_db_stats():
    cur = DB.conn.cursor()
    stats = {}
    for tbl in ["sessions", "turns", "skill_uses", "survey_responses", "rewards"]:
        stats[tbl] = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    stats["skill_frequency"] = DB.skill_frequency()
    return jsonify(stats)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from model_config import print_config
    from api_client import check_ollama_running, check_hf_model, _get_hf_token

    port = int(os.environ.get("PORT", 6767))
    print(f"\n{'='*58}\nPedagogical RL — Human Validation Server\n{'='*58}")
    print_config()

    b = CFG["backend"]
    if b == "huggingface":
        try:
            tok = _get_hf_token(CFG)
            st  = check_hf_model(CFG["model"], tok)
            print(f"[ok] HF token found | model: {'ready' if st['loaded'] else 'cold start'}")
        except RuntimeError as e:
            print(f"[ERROR] {e}"); raise SystemExit(1)
    elif b == "ollama":
        st = check_ollama_running()
        if not st["running"]:
            print(f"[ERROR] Ollama not running.\n  Fix: ollama serve"); raise SystemExit(1)
        m = CFG["model"]
        print(f"[ok] Ollama — '{m}' {'ready' if any(m in x for x in st['models']) else 'NOT pulled'}")
    elif b == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[ERROR] ANTHROPIC_API_KEY not set."); raise SystemExit(1)
        print("[ok] Anthropic key found")

    print(f"\nSkills: {len(SKILLS)}  |  Scenarios: {[s['id'] for s in SCENARIOS.values()]}")
    print(f"DB: {DB.conn}\nOpen: http://localhost:{port}\n{'='*58}\n")
    app.run(debug=False, port=port, host="0.0.0.0")