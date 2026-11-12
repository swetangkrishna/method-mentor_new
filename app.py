"""Gradio entry point for the private, free Hugging Face testing Space."""
import json
import os
from pathlib import Path

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("RAG_EMBED_DEVICE", "cpu")
os.environ.setdefault("RAG_LOG_STATUS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# ZeroGPU requires a decorated function even for an external-API app.
# It is deliberately never called: Azure handles generation, CPU handles RAG.
if os.environ.get("SPACE_ID"):
    import spaces  # Must precede imports that can load Torch.

    @spaces.GPU
    def _unused_gpu_registration():
        pass

import gradio as gr

from scenarios import SCENARIOS, SURVEY_QUESTIONS
from space_bridge import BridgeError, SpaceBridge


def prepare_environment():
    """Materialize Space secrets privately, outside the source repository."""
    data = Path(os.environ.get("METHOD_MENTOR_DATA_DIR", "/tmp/method-mentor-runtime"))
    data.mkdir(mode=0o700, parents=True, exist_ok=True)
    data.chmod(0o700)
    os.environ.setdefault("DB_PATH", str(data / "test-sessions.db"))
    os.environ.setdefault("WEB_SESSIONS_DIR", str(data / "sessions"))
    if os.environ.get("STUDY_PROTOCOL_JSON"):
        try:
            protocol = json.loads(os.environ["STUDY_PROTOCOL_JSON"])
            if not isinstance(protocol, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise RuntimeError("STUDY_PROTOCOL_JSON must contain a study configuration object") from None
        target = data / "study-protocol.json"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(protocol, stream)
        target.chmod(0o600)
        os.environ["STUDY_PROTOCOL_FILE"] = str(target)
    if os.environ.get("PARTICIPANTS_JSON"):
        try:
            accounts = json.loads(os.environ["PARTICIPANTS_JSON"])
            if not isinstance(accounts, dict) or not accounts or any(
                not isinstance(k, str) or not 1 <= len(k) <= 100
                or not isinstance(v, dict) or not isinstance(v.get("password_hash"), str)
                or not v["password_hash"]
                for k, v in accounts.items()
            ):
                raise ValueError()
        except (ValueError, TypeError):
            raise RuntimeError("PARTICIPANTS_JSON must contain hashed participant accounts") from None
        target = data / "participants.json"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(accounts, stream)
        target.chmod(0o600)
        os.environ["PARTICIPANTS_FILE"] = str(target)
    if not os.environ.get("PARTICIPANTS_FILE"):
        raise RuntimeError("Set PARTICIPANTS_JSON in Space secrets before starting")
    return data


def build_demo(bridge):
    """Use authenticated server-side identities for every session action."""
    def invoke(method, request, *args):
        username = getattr(request, "username", None)
        if not username:
            raise gr.Error("Please sign in again.")
        try:
            return method(username, *args)
        except BridgeError as error:
            raise gr.Error(str(error)) from None

    def start(scenario_id, sid, request: gr.Request):
        # Recover an existing active conversation for this account.
        if study_enabled:
            sessions = invoke(bridge.sessions, request)["sessions"]

            active = next(
                (
                    s for s in sessions
                    if not s["ended"] and not s["read_only"]
                ),
                None
            )

            if active:
                current = invoke(
                    bridge.resume,
                    request,
                    active["session_id"]
                )

                return (
                    current["session_id"],
                    current["session_id"],
                    current["history"],
                    "Your existing conversation has been recovered.",
                    "",
                    "",
                    False,
                    None, None, None, None, None,
                    ""
                )

        elif sid:
            current = invoke(bridge.resume, request, sid)

            if not current["ended"]:
                return (
                    sid, sid, current["history"],
                    "Conversation resumed.",
                    "", "",
                    False, None, None, None, None, None, ""
                )

        # In formal studies, do not start another intervention.
        if study_enabled and not rehearsal:
            sessions = invoke(bridge.sessions, request)["sessions"]

            if any(not s["read_only"] for s in sessions):
                raise gr.Error(
                    "You have already completed your study conversation. "
                    "Use 'Find my conversations' to open it and complete "
                    "any remaining assessments."
                )

        # Start a new conversation when permitted.
        result = invoke(bridge.start, request, scenario_id)

        sid = result["session_id"]
        current = invoke(bridge.resume, request, sid)

        return (
            sid,
            sid,
            current["history"],
            "Conversation resumed." if result.get("resumed")
            else "Conversation started.",
            "",
            "",
            False,
            None, None, None, None, None,
            ""
        )

    def send(message, sid, request: gr.Request):
        from reply_flow import submit_reply
        history, text, status = submit_reply(bridge, getattr(request, "username", None), sid, message)
        return gr.skip() if history is None else history, text, status

    def resume(sid, request: gr.Request):
        current = invoke(bridge.resume, request, sid.strip())
        status = "Conversation ended. You can leave feedback or copy your transcript." if current["ended"] else "Conversation resumed."
        if current.get("survey_result"):
            status = "Conversation ended and feedback saved. You can copy your transcript."
        if current.get("read_only"):status="Saved conversation from an earlier version (read-only). You can copy its transcript or start a new self-test."
        return (current["session_id"], current["history"], status, "",
                False, None, None, None, None, None, "")

    def find_sessions(request: gr.Request):
        result=invoke(bridge.sessions,request)['sessions']
        choices=[(r['updated'][:16]+' — '+('earlier version, read-only' if r['read_only'] else 'ended' if r['ended'] else 'active')+' — '+r['session_id'],r['session_id']) for r in result]
        return gr.Dropdown(choices=choices,value=choices[0][1] if choices else None), ('Select a saved conversation, then open it.' if choices else 'No saved conversations for this account.')

    def open_saved(code, request: gr.Request):
        result=resume(code or '',request)
        return (result[0],result[0],*result[1:])

    def end(sid, solved, request: gr.Request):
        invoke(bridge.end, request, sid, solved)
        return "Conversation ended. Please leave feedback below."

    def feedback(sid, q1, q2, q3, q4, q5, comment, request: gr.Request):
        scores = (q1, q2, q3, q4, q5)
        if any(x is None for x in scores):
            raise gr.Error("Please answer all five rating questions.")
        survey = {f"Q{i}": {"score": int(score), "comment": ""}
                  for i, score in enumerate(scores, 1)}
        survey["Q_open"] = {"score": None, "comment": comment[:12000]}
        invoke(bridge.survey, request, sid, survey)
        return "Thank you. Your feedback has been saved for this test session."

    def transcript(sid, request: gr.Request):
        return invoke(bridge.transcript, request, sid)

    study_enabled = os.environ.get('STUDY_ENABLED') == '1'
    rehearsal = False
    initial_assessment = True
    if study_enabled:
        from study_protocol import load_protocol
        protocol = load_protocol()
        rehearsal = protocol['mode'] != 'formal'
        initial_assessment = protocol.get('initial_assessment', True)

    def info(request: gr.Request):
        result = invoke(bridge.study_info, request)
        return (result['information'] + '\n\n' + result.get('policy_learning_notice','') + '\n\nResearcher contact: ' + result['contact'] +
                '\n\nRetention: ' + str(result['retention_days']) + ' days. Version: ' + result['consent_version'])

    def enroll(consent, text, confidence, request: gr.Request):
        return invoke(bridge.study_enroll, request, consent, text, int(confidence))['status']

    def consent_only(consent, request: gr.Request):
        return invoke(bridge.study_enroll, request, consent, None, None)['status']

    def post(sid, text, confidence, q1,q2,q3,q4,q5,q6,q7,q8,q9,q10, request: gr.Request):
        values = [q1,q2,q3,q4,q5,q6,q7,q8,q9,q10]
        if any(v is None for v in values): raise gr.Error('Answer all ten usability questions.')
        return invoke(bridge.study_post, request, sid, text, int(confidence), [int(v) for v in values])['status']

    def withdraw(confirm, request: gr.Request):
        return invoke(bridge.study_withdraw, request, confirm)['status']

    with gr.Blocks(title="Method Mentor") as demo:
        gr.Markdown("# Method Mentor\nDiscuss your research methods with Aoife.")
        gr.Markdown("**Study rehearsal:** use sample research information only. These records are excluded from formal study analysis and policy training. Read the information and save your consent before starting."
                    if rehearsal else "**Research study:** read the information and save your consent before starting."
                    if study_enabled else "**Login required · test version.** Sessions may disappear when the host restarts. Copy your transcript before leaving. Use sample research information while testing.")
        gr.HTML('<a href="/logout">Sign out</a>')
        sid = gr.State("")
        if study_enabled:
            with gr.Accordion('My saved conversations', open=True):
                find_button=gr.Button('Find my conversations')
                saved_choice=gr.Dropdown(choices=[],label='Saved conversation',interactive=True)
                open_button=gr.Button('Open selected conversation')
        if study_enabled:
            from study_protocol import ASSESSMENT_PROMPT, SUS_ITEMS
            with gr.Accordion('Before the conversation', open=True):
                study_information = gr.Textbox(label='Participant information', lines=10, interactive=False)
                information_button = gr.Button('Read study information')
                consent = gr.Checkbox(label=('I have read the rehearsal information and agree to recording my sample inputs for system testing.'
                                            if rehearsal else 'I have read the participant information and voluntarily consent to this study.'), value=False)
                if initial_assessment:
                    pre = gr.Textbox(label='Initial reasoning assessment', info=ASSESSMENT_PROMPT, lines=6, max_length=12000)
                    pre_confidence = gr.Slider(0,10,step=1,value=0,label='Confidence in your methodological reasoning (0–10)')
                enroll_button = gr.Button('Save consent and initial assessment' if initial_assessment else 'Save consent')
                enrollment_status = gr.Textbox(label='Participation status', interactive=False)

        with gr.Row():
            scenario = gr.Dropdown(
                [("My own research project", "FREEFORM")] +
                [(f"{s['id']}: {s['topic']}", s["id"]) for s in SCENARIOS.values()],
                value="FREEFORM", label="Conversation topic")
            start_button = gr.Button("Start conversation", variant="primary")
        status = gr.Textbox(label="Session status", value="Choose a topic and start.", interactive=False)
        chat = gr.Chatbot(label="Conversation with Aoife", height=460, render_markdown=False,
                          buttons=["copy_all"], allow_file_downloads=False, feedback_options=None)
        message = gr.Textbox(label="Your reply", lines=3, max_length=12000,
                             placeholder="Describe your research question or respond to Aoife…")
        with gr.Row():
            send_button = gr.Button("Send reply", variant="primary")
            end_button = gr.Button("End conversation")
        solved = gr.Checkbox(label="I can now explain my choice of research method", value=False)
        with gr.Accordion("Feedback", open=False):
            gr.Markdown("After ending your conversation, rate your experience.")
            ratings = [gr.Radio([1, 2, 3, 4, 5], label=q["question"], info=q["scale"])
                       for q in SURVEY_QUESTIONS if q["id"] != "Q_open"]
            comment = gr.Textbox(label="Anything else you would like to share?", lines=3, max_length=12000)
            feedback_button = gr.Button("Save feedback")
        with gr.Accordion("Keep or resume this conversation", open=False):
            session_code = gr.Textbox(label="Session code", buttons=["copy"],
                                      info=("Save this code to resume your study conversation." if study_enabled else
                                            "Save this code to resume after refreshing. It expires if the host restarts."))
            resume_button = gr.Button("Resume using this code")
            export_button = gr.Button("Prepare my transcript")
            transcript_text = gr.Textbox(label="Your transcript", lines=12, interactive=False, buttons=["copy"])
        if study_enabled:
            with gr.Accordion('After the conversation', open=False):
                post_text = gr.Textbox(label='Final reasoning assessment', info=ASSESSMENT_PROMPT, lines=6, max_length=12000)
                post_confidence = gr.Slider(0,10,step=1,value=0,label='Confidence in your methodological reasoning (0–10)')
                usability = [gr.Radio([1,2,3,4,5], label=text, info='1 strongly disagree — 5 strongly agree') for text in SUS_ITEMS]
                post_button = gr.Button('Save final assessment and usability questionnaire')
                assessment_status = gr.Textbox(label='Assessment status', interactive=False)
            with gr.Accordion('Withdraw from this study', open=False):
                gr.Markdown('You may stop participating. Withdrawal deletes active study records. Contact the researcher about backup retention. This cannot be undone in the app.')
                withdrawal_confirm = gr.Checkbox(label='I confirm that I want to withdraw and delete my active study records.',value=False)
                withdraw_button = gr.Button('Withdraw')
        event = dict(concurrency_limit=1, concurrency_id="mentor", api_visibility="undocumented")
        if study_enabled:
            find_button.click(find_sessions, [], [saved_choice,status], api_name='my_sessions', **event)
            open_button.click(open_saved, [saved_choice], [sid,session_code,chat,status,message,solved,*ratings,comment], api_name='open_saved', **event)
            information_button.click(info, [], study_information, api_name='study_information', **event)
            if initial_assessment:
                enroll_button.click(enroll, [consent,pre,pre_confidence], enrollment_status, api_name='study_enroll', **event)
            else:
                enroll_button.click(consent_only, [consent], enrollment_status, api_name='study_enroll', **event)
            post_button.click(post, [sid,post_text,post_confidence,*usability], assessment_status, api_name='study_post', **event)
            withdraw_button.click(withdraw, withdrawal_confirm, enrollment_status, api_name='study_withdraw', **event)
        feedback_fields = [solved, *ratings, comment]
        start_button.click(start, [scenario, sid], [sid, session_code, chat, status, message, transcript_text, *feedback_fields], api_name="start", **event)
        send_button.click(send, [message, sid], [chat, message, status], api_name="reply", **event)
        message.submit(send, [message, sid], [chat, message, status], api_name="reply_enter", **event)
        end_button.click(end, [sid, solved], status, api_name="end", **event)
        feedback_button.click(feedback, [sid, *ratings, comment], status, api_name="feedback", **event)
        resume_button.click(resume, session_code, [sid, chat, status, transcript_text, *feedback_fields], api_name="resume", **event)
        export_button.click(transcript, sid, transcript_text, api_name="transcript", **event)
    return demo.queue(max_size=12, default_concurrency_limit=1)


if __name__ == "__main__":
    runtime_dir = prepare_environment()
    if os.environ.get("RAG_PRIVATE_SOURCE") == "1":
        from student_assets import prepare_private_rag
        prepare_private_rag(runtime_dir)
    bridge = SpaceBridge()
    demo = build_demo(bridge)
    demo.launch(auth=bridge.auth, auth_message="Sign in with your Method Mentor test account.",
                server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")),
                share=False, show_error=False, ssr_mode=False, mcp_server=False,
                enable_monitoring=False, run_history=False, footer_links=[],
                blocked_paths=[str(Path(__file__).resolve().parent), str(runtime_dir.resolve())])
