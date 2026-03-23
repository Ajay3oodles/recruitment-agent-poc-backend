"""
One-time script to generate a PDF summary of the changes made.
Run: python generate_summary_pdf.py
"""
from fpdf import FPDF
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "Changes_Summary.pdf")


class SummaryPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, "Ontario Tech Recruitment Chatbot - Changes Summary", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 102, 204)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(0, 70, 140)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 102, 204)
        self.line(10, self.get_y(), 120, self.get_y())
        self.ln(3)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(40, 40, 40)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text, indent=15):
        x = self.get_x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(50, 50, 50)
        self.set_x(x + indent)
        self.cell(5, 5.5, chr(8226), new_x="END")
        self.multi_cell(0, 5.5, f"  {text}")
        self.ln(1)

    def key_value(self, key, value, indent=15):
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(50, 50, 50)
        self.cell(self.get_string_width(key + ": ") + 2, 5.5, f"{key}: ", new_x="END")
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, value)
        self.ln(1)

    def code_block(self, text):
        self.set_font("Courier", "", 8.5)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 4.5, text, fill=True)
        self.ln(3)

    def table_header(self, cols, widths):
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(0, 70, 140)
        self.set_text_color(255, 255, 255)
        for i, col in enumerate(cols):
            self.cell(widths[i], 7, col, border=1, fill=True, align="C")
        self.ln()

    def table_row(self, cols, widths):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(50, 50, 50)
        self.set_fill_color(250, 250, 250)
        for i, col in enumerate(cols):
            self.cell(widths[i], 6.5, col, border=1, align="L")
        self.ln()


def build_pdf():
    pdf = SummaryPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ═══════════════════════════════════════════════════════════
    # PAGE 1 — CHANGE 1: CONVERSATIONAL FLOW PROMPT SYSTEM
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(0, 50, 100)
    pdf.cell(0, 12, "CHANGE 1: Conversational Flow Prompt System", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.body_text(
        "We redesigned the chatbot's prompt system from a simple Q&A bot into a full "
        "lead-capture concierge. Instead of just answering questions, the bot now follows "
        "a structured conversational flow that progressively qualifies visitors and captures "
        "lead information naturally."
    )

    # --- What Changed ---
    pdf.section_title("Files Modified")

    pdf.sub_title("1. chatbot/services/prompt_builder.py (Complete Rewrite)")
    pdf.body_text("This file contains ALL the LLM prompts. It was rewritten to include:")
    pdf.bullet("System prompt with core identity, goals, and behaviour rules")
    pdf.bullet("Intent detection logic (classify user in first 2-4 turns)")
    pdf.bullet("Progressive lead capture rules (3 tiers)")
    pdf.bullet("Timezone handling for meeting scheduling")
    pdf.bullet("Lead scoring signals")
    pdf.bullet("Structured JSON response format with lead_data extraction")
    pdf.bullet("New build_lead_context() helper function")

    pdf.sub_title("2. chatbot/services/prompt_service.py (Updated)")
    pdf.body_text("The main chat handler now manages a Lead lifecycle per session:")
    pdf.bullet("Creates/links a Lead record to each session automatically")
    pdf.bullet("Passes already-collected lead data to the prompt (so LLM doesn't re-ask)")
    pdf.bullet("Parses lead_data from LLM response and updates Lead progressively")
    pdf.bullet("Never overwrites existing data with null")

    pdf.sub_title("3. chatbot/services/watsonx.py (Updated)")
    pdf.body_text("generate_answer() updated to:")
    pdf.bullet("Accept lead_context parameter")
    pdf.bullet("Return lead_data dict alongside answer and summary")

    pdf.sub_title("4. chatbot/models.py (Updated by user)")
    pdf.body_text("New Lead model and Session.thread_id field were added:")
    pdf.bullet("Lead model: first_name, email, phone, ip_address, lead_type, intent_score, meeting_date, meeting_time, conversation_summary")
    pdf.bullet("Session.thread_id: for IBM Watson Orchestrator thread linking")

    pdf.sub_title("5. New Migration: 0002_session_thread_id_lead.py")
    pdf.body_text("Adds thread_id to Session table and creates the Lead table in PostgreSQL.")

    # --- Conversational Flow ---
    pdf.add_page()
    pdf.section_title("Conversational Flow Design")

    pdf.body_text("The bot follows this flow for every conversation:")

    pdf.sub_title("Step 1: Entry + Intent Detection (Turns 1-2)")
    pdf.body_text(
        'On the first message, the bot naturally asks what the user is exploring. '
        'It classifies the user into one of 6 categories: student_undergrad, student_grad, '
        'student_international, research_industry, lifelong_learning, or other.'
    )

    pdf.sub_title("Step 2: Value Delivery (Turns 2-4)")
    pdf.body_text(
        "The bot answers the user's question using CMS content from pgvector. "
        "It provides program details, deadlines, requirements, etc. "
        "NO personal information is requested at this stage."
    )

    pdf.sub_title("Step 3: Progressive Lead Capture")

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 7, "Tier 1 - Name (Low Friction)", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet('After 2-3 exchanges, casually asks: "By the way, what should I call you?"')
    pdf.bullet("If declined: waits 2 more exchanges, asks once more. If declined again: stops.")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Tier 2 - Email (After Value Delivered)", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet('Framed as benefit: "I can email you a personalized summary - would you like that?"')
    pdf.bullet("If declined: waits 2 more exchanges, tries different value proposition once. Then stops.")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Tier 3 - Phone + Meeting (High Intent Only)", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet("Only after main query is resolved")
    pdf.bullet('Asks: "Would you like to schedule a call with our admissions advisors?"')
    pdf.bullet("If agreed: collects phone number -> preferred date -> preferred time")

    pdf.sub_title("Step 4: Timezone-Aware Meeting Scheduling")
    pdf.body_text(
        "Business hours: 10 AM - 6 PM Eastern Time (Canada). "
        "The bot converts times to user's timezone (detected from frontend IP). "
        "Accepts flexible date inputs like 'tomorrow', 'this Monday', 'next week'."
    )

    # --- Lead Scoring ---
    pdf.sub_title("Lead Scoring (Tracked Internally)")

    widths = [110, 30]
    pdf.table_header(["Signal", "Points"], widths)
    pdf.table_row(["Asked about admission process or requirements", "+30"], widths)
    pdf.table_row(["Asked about deadlines", "+20"], widths)
    pdf.table_row(["Asked about specific program", "+20"], widths)
    pdf.table_row(["Asked about campus life, housing, fees", "+10"], widths)
    pdf.table_row(["Provided email", "+50"], widths)
    pdf.table_row(["Multiple session turns (engaged)", "+25"], widths)
    pdf.table_row(["Expressed timeline (Fall 2026, next year)", "+30"], widths)
    pdf.table_row(["Agreed to schedule a meeting", "+40"], widths)
    pdf.ln(4)

    # --- JSON Response ---
    pdf.sub_title("LLM Response Format")
    pdf.body_text("Every LLM response now returns this structured JSON:")
    pdf.code_block(
        '{\n'
        '  "answer": "conversational response to the user",\n'
        '  "summary": "1-2 sentence summary of conversation so far",\n'
        '  "lead_data": {\n'
        '    "name": "extracted name or null",\n'
        '    "email": "extracted email or null",\n'
        '    "phone": "extracted phone or null",\n'
        '    "lead_type": "student_undergrad | student_grad | ...",\n'
        '    "intent_score": 0,\n'
        '    "meeting_date": "YYYY-MM-DD or null",\n'
        '    "meeting_time": "HH:MM or null",\n'
        '    "conversation_summary": "brief summary"\n'
        '  }\n'
        '}'
    )

    # ═══════════════════════════════════════════════════════════
    # PAGE — CHANGE 2: SESSION END & LEAD EXTRACTION
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(0, 50, 100)
    pdf.cell(0, 12, "CHANGE 2: Session End & Lead Extraction Strategy", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.body_text(
        "When we switch to the IBM Watson Orchestrate agent flow, we need a way to "
        "detect when a conversation has ended so we can make a final LLM call to extract "
        "a full lead summary. This is the strategy we discussed."
    )

    pdf.section_title("The Problem")
    pdf.body_text(
        "In the agent flow, Watson Orchestrate manages the conversation thread. "
        "We need to know WHEN the conversation is done so we can:\n"
        "1. Fetch the full thread from Watson\n"
        "2. Run one LLM call to extract all lead details\n"
        "3. Save the Lead record to our database\n"
        "4. Mark the session as inactive"
    )

    pdf.section_title("The Solution: Dual Trigger Approach")

    pdf.sub_title("Trigger 1: Frontend Close Event (Primary)")
    pdf.body_text(
        "When the user closes the chat widget or navigates away from the page, "
        "the frontend sends a POST request to /api/chat-bot/v1/chat/close/ with "
        "the session_id. This is the most reliable trigger for intentional exits."
    )
    pdf.body_text("Frontend implementation needed:")
    pdf.bullet("Listen for chat widget close button click")
    pdf.bullet("Listen for browser beforeunload event (tab/window close)")
    pdf.bullet("Send POST { session_id: X } to the close endpoint")
    pdf.bullet("Use navigator.sendBeacon() for reliability on page unload")

    pdf.sub_title("Trigger 2: Backend Idle Timeout (Fallback)")
    pdf.body_text(
        "A scheduled task (APScheduler, already running) checks every 10-15 minutes "
        "for sessions where the last message is older than 15 minutes AND no lead "
        "summary has been extracted yet. This catches cases where the user just "
        "closes the browser without triggering the frontend event."
    )
    pdf.body_text("Implementation:")
    pdf.bullet("APScheduler job runs every 10-15 minutes")
    pdf.bullet("Queries: sessions where last_chat > 15 min ago AND is_active=True AND no lead summary")
    pdf.bullet("For each stale session: triggers the same extraction flow")
    pdf.bullet("Marks session as is_active=False after extraction")

    pdf.section_title("What Happens on Session End")
    pdf.body_text("Regardless of which trigger fires, the same flow runs:")

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 7, "Step 1: Fetch Conversation", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet("Agent flow: fetch full thread from Watson Orchestrate API")
    pdf.bullet("Direct flow: fetch all Chat records from our DB for that session")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Step 2: LLM Extraction Call", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet("Send entire conversation to LLM with an extraction prompt")
    pdf.bullet("LLM returns: name, email, phone, program interest, intent, sentiment, lead_score, summary")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Step 3: Save to Lead Model", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet("Update or create Lead record with extracted data")
    pdf.bullet("Set conversation_summary field")
    pdf.bullet("Calculate final intent_score")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Step 4: Close Session", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet("Set session.is_active = False")
    pdf.bullet("Lead is now ready for CRM sync / follow-up")

    # --- Comparison Table ---
    pdf.ln(3)
    pdf.section_title("Trigger Comparison")

    widths = [45, 55, 45, 45]
    pdf.table_header(["Trigger", "How", "Pros", "Cons"], widths)
    pdf.table_row(["Frontend Close", "POST /chat/close/", "Explicit, fast", "Misses tab closes"], widths)
    pdf.table_row(["Idle Timeout", "Scheduler (15 min)", "Catches everything", "Slight delay"], widths)
    pdf.table_row(["Both (recommended)", "Close + scheduler", "Full coverage", "More code"], widths)

    # --- Existing Code ---
    pdf.ln(4)
    pdf.section_title("What Already Exists")
    pdf.bullet("close_session_view in chatbot/views/prompt_view.py (endpoint ready)")
    pdf.bullet("extract_lead_from_session() in chatbot/services/agent_service.py (extraction logic)")
    pdf.bullet("APScheduler configured in chatbot/scheduler.py (scheduler running)")
    pdf.bullet("Lead model in chatbot/models.py (database table created)")

    pdf.section_title("What Still Needs to Be Built")
    pdf.bullet("Scheduler task for idle session detection (query stale sessions, trigger extraction)")
    pdf.bullet("Frontend: sendBeacon() call on widget close / beforeunload")
    pdf.bullet("Update extract_lead_from_session() to work with direct flow (not just agent flow)")
    pdf.bullet("Watson Orchestrate agent configuration (URL + Agent ID in .env)")

    # ═══════════════════════════════════════════════════════════
    # PAGE — ARCHITECTURE OVERVIEW
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(0, 50, 100)
    pdf.cell(0, 12, "Architecture Overview", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.section_title("Two Flows — Same API Surface")

    pdf.sub_title("Flow A: Direct LLM (Current - Active)")
    pdf.body_text(
        "Frontend -> prompt_view.py -> prompt_service.py -> watsonx.py -> IBM LLM\n"
        "Prompt building + pgvector retrieval + lead capture all happen in our backend.\n"
        "The prompt_builder.py system prompt drives the conversation flow."
    )

    pdf.sub_title("Flow B: Watson Orchestrate Agent (Skeleton Ready)")
    pdf.body_text(
        "Frontend -> prompt_view.py -> agent_service.py -> watson_orchestrate.py -> Watson Agent\n"
        "Watson handles: search, context, LLM call, answer.\n"
        "Our backend only manages: session, thread linking, lead extraction on close."
    )

    pdf.body_text(
        "The view (prompt_view.py) auto-switches between flows based on whether "
        "WATSON_ORCHESTRATE_URL and WATSON_ORCHESTRATE_AGENT_ID are set in .env. "
        "Frontend code stays exactly the same for both flows."
    )

    pdf.section_title("Data Model")

    pdf.sub_title("Session")
    pdf.bullet("session_name, session_token (UUID), is_active")
    pdf.bullet("thread_id (NEW - links to Watson Orchestrate thread)")
    pdf.bullet("metadata (JSON - stores lead_id FK)")

    pdf.sub_title("Chat")
    pdf.bullet("session (FK), role (user/bot), message, summary")
    pdf.bullet("Ordered by created_at")

    pdf.sub_title("Lead (NEW)")
    pdf.bullet("first_name, email, phone, ip_address")
    pdf.bullet("lead_type (undergrad/grad/international/research/lifelong/other)")
    pdf.bullet("intent_score (0-100, decimal)")
    pdf.bullet("meeting_date, meeting_time")
    pdf.bullet("conversation_summary")
    pdf.bullet("is_synced (for CRM integration later)")
    pdf.bullet("is_active")

    pdf.section_title("Key Endpoints")

    widths = [35, 70, 85]
    pdf.table_header(["Method", "Endpoint", "Purpose"], widths)
    pdf.table_row(["POST", "/api/chat-bot/v1/chat/", "Send message (auto-routes flow A/B)"], widths)
    pdf.table_row(["POST", "/api/chat-bot/v1/chat/close/", "End session + extract lead"], widths)
    pdf.table_row(["GET", "/api/health/", "System health check"], widths)
    pdf.table_row(["GET", "/api/pages/", "List indexed CMS pages"], widths)

    # --- Save ---
    pdf.output(OUTPUT_PATH)
    print(f"PDF saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
