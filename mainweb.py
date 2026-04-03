import concurrent.futures
import json
import os
import re
import smtplib
import zipfile
from datetime import datetime
from email.message import EmailMessage
from io import BytesIO

import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from PyPDF2 import PdfMerger
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


st.set_page_config(page_title="PaperPort Public", layout="wide")

LEVELS = st.secrets["LEVELS"]
DOWNLOAD_DIR = st.secrets["DOWNLOAD_DIR"]
HEADERS = json.loads(st.secrets["HEADERS"])
SESSIONS_ALL = st.secrets["SESSIONS_ALL"]
ACCESS_STUDENT_ID_PREFIX = str(st.secrets.get("ACCESS_STUDENT_ID_PREFIX", "")).strip()
ACCESS_TEACHER_EMAIL_DOMAINS = tuple(
    str(domain).strip().lower()
    for domain in st.secrets.get("ACCESS_TEACHER_EMAIL_DOMAINS", [])
    if str(domain).strip()
)

IGCSE_SUBJECTS = json.loads(st.secrets["IGCSE_SUBJECTS"])
ALEVEL_SUBJECTS = json.loads(st.secrets["ALEVEL_SUBJECTS"])

DATA_FILE = "data.json"
REQUESTS_FILE = "custom_school_requests.json"
DEFAULT_FONT_PATH = "Poppins-Bold.ttf"
GENERAL_COVER_PATH = "GENERAL_COVER.png"

SESSION_OPTIONS = {
    "FEB/MAR": "m",
    "MAY/JUN": "s",
    "OCT/NOV": "w",
}

PAPER_TYPE_OPTIONS = {
    "Question Paper": "qp",
    "Mark Scheme": "ms",
    "Insert": "in",
    "Grade Thresholds": "gt",
}


st.markdown(
    """
<style>
.stApp {
    background: #ffffff;
    color: #000000;
}
.stButton > button, .stDownloadButton > button {
    background: #163a8c;
    color: #ffffff;
    border: 1px solid #163a8c;
    border-radius: 12px;
    font-weight: 600;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: #102d6f;
    border-color: #102d6f;
    color: #ffffff;
}
.page-card {
    background: #ffffff;
    border: 1px solid #d7deed;
    border-radius: 18px;
    padding: 22px;
}
.download-card {
    background: #f4f7ff;
    border: 1px solid #c7d5fb;
    border-radius: 16px;
    padding: 18px;
}
</style>
""",
    unsafe_allow_html=True,
)


def ensure_json_file(path, default_content):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_content, f, indent=4)


ensure_json_file(DATA_FILE, {"total_downloads": 0, "logs": []})
ensure_json_file(REQUESTS_FILE, {"requests": []})

if "public_general_zip_bytes" not in st.session_state:
    st.session_state["public_general_zip_bytes"] = None
if "public_general_zip_name" not in st.session_state:
    st.session_state["public_general_zip_name"] = None
if "startup_popup_seen" not in st.session_state:
    st.session_state["startup_popup_seen"] = False
if "access_verification_value" not in st.session_state:
    st.session_state["access_verification_value"] = ""


def register_cover_font():
    if os.path.exists(DEFAULT_FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont("PoppinsBoldPublic", DEFAULT_FONT_PATH))
            return "PoppinsBoldPublic"
        except Exception:
            pass
    return "Helvetica-Bold"


COVER_FONT_NAME = register_cover_font()


@st.dialog("Welcome to PaperPort")
def show_startup_popup():
    st.markdown(
        """
**You are accessing the Custom School Past Paper Compiler.**

To proceed, verification is required.

Type your ID card number if you are a student, or your email address if you are a teacher.
"""
    )

    verification_value = st.text_input(
        "Student ID card number or teacher email",
        value=st.session_state["access_verification_value"],
        placeholder="Enter ID card number or email",
    )
    st.session_state["access_verification_value"] = verification_value

    if st.button("Verify School Access", use_container_width=True):
        cleaned_value = verification_value.strip()

        if not cleaned_value:
            st.error("Please enter your ID card number or teacher email to continue.")
            return

        if not ACCESS_STUDENT_ID_PREFIX or not ACCESS_TEACHER_EMAIL_DOMAINS:
            st.error(
                "Access verification is not configured. Please add ACCESS_STUDENT_ID_PREFIX "
                "and ACCESS_TEACHER_EMAIL_DOMAINS to Streamlit secrets."
            )
            return

        normalized_value = cleaned_value.lower()

        if "@" in normalized_value:
            if not normalized_value.endswith(ACCESS_TEACHER_EMAIL_DOMAINS):
                allowed_domains_text = " or ".join(ACCESS_TEACHER_EMAIL_DOMAINS)
                st.error(f"Teacher email must end with {allowed_domains_text}.")
                return
        else:
            student_digits = re.sub(r"\D", "", cleaned_value)
            required_digits = len(ACCESS_STUDENT_ID_PREFIX)
            if len(student_digits) < required_digits:
                st.error(f"Student ID must include at least the first {required_digits} digits.")
                return
            if student_digits[:required_digits] != ACCESS_STUDENT_ID_PREFIX:
                st.error(
                    f"Student ID must begin with {ACCESS_STUDENT_ID_PREFIX} in the first "
                    f"{required_digits} digits."
                )
                return
            cleaned_value = student_digits[:required_digits]

        st.session_state["access_verification_value"] = cleaned_value
        st.session_state["startup_popup_seen"] = True
        st.rerun()

    if st.button("Use the General/Public Version of PaperPort", use_container_width=True):
        components.html(
            """
<script>
window.open("https://paperport.streamlit.app/", "_self");
</script>
""",
            height=0,
        )


def update_data_log(level, subject_name, subject_code, num_papers, success_count, fail_count):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["total_downloads"] += 1
    data["logs"].append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "subject_name": subject_name,
            "subject_code": subject_code,
            "papers_selected": num_papers,
            "success": success_count,
            "failed": fail_count,
        }
    )

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def save_school_request(payload):
    with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["requests"].append(payload)

    with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def send_school_request_notification(payload):
    required_keys = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "NOTIFICATION_EMAIL_TO",
    ]
    missing_keys = [key for key in required_keys if key not in st.secrets]
    if missing_keys:
        return False, f"Missing email secrets: {', '.join(missing_keys)}"

    smtp_host = st.secrets["SMTP_HOST"]
    smtp_port = int(st.secrets["SMTP_PORT"])
    smtp_username = st.secrets["SMTP_USERNAME"]
    smtp_password = st.secrets["SMTP_PASSWORD"]
    notification_to = st.secrets["NOTIFICATION_EMAIL_TO"]
    notification_from = st.secrets.get("NOTIFICATION_EMAIL_FROM", smtp_username)
    use_tls = str(st.secrets.get("SMTP_USE_TLS", "true")).lower() == "true"

    message = EmailMessage()
    message["Subject"] = f"New PaperPort school request: {payload['school_name']}"
    message["From"] = notification_from
    message["To"] = notification_to
    message.set_content(
        "\n".join(
            [
                "A new custom school merger request was submitted.",
                "",
                f"Timestamp: {payload['timestamp']}",
                f"School Name: {payload['school_name']}",
                f"Contact Person: {payload['contact_name']}",
                f"Contact Email: {payload['contact_email']}",
                f"Country: {payload['country']}",
                "",
                "Notes:",
                payload["notes"] or "(No extra notes provided)",
            ]
        )
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(message)

    return True, None


def send_requester_confirmation_email(payload):
    required_keys = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
    ]
    missing_keys = [key for key in required_keys if key not in st.secrets]
    if missing_keys:
        return False, f"Missing email secrets: {', '.join(missing_keys)}"

    smtp_host = st.secrets["SMTP_HOST"]
    smtp_port = int(st.secrets["SMTP_PORT"])
    smtp_username = st.secrets["SMTP_USERNAME"]
    smtp_password = st.secrets["SMTP_PASSWORD"]
    notification_from = st.secrets.get("NOTIFICATION_EMAIL_FROM", smtp_username)
    use_tls = str(st.secrets.get("SMTP_USE_TLS", "true")).lower() == "true"

    message = EmailMessage()
    message["Subject"] = "PaperPort request received"
    message["From"] = notification_from
    message["To"] = payload["contact_email"]
    message.set_content(
        "\n".join(
            [
                f"Hello {payload['contact_name']},",
                "",
                "Thank you for submitting a request for a custom school past paper merger through PaperPort.",
                "We have received your request successfully and will contact you shortly.",
                "",
                "Please note that this service is provided free of cost for schools.",
                "",
                "This email was generated automatically to confirm that your request has been received.",
                "You do not need to reply unless you want to add more information.",
                "",
                "Best regards,",
                "Fernando Gabriel Morera",
                "PaperPort",
            ]
        )
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(message)

    return True, None


def format_papers(text):
    cleaned = re.sub(r"\D", "", text)
    groups = [cleaned[i : i + 2] for i in range(0, len(cleaned), 2)]
    return " ".join([g for g in groups if g])


def build_cover_lines(subject_name, paper_type_short, paper_no, level, subject_code):
    heading_level = "A-LEVEL" if level == "A Level" else "IGCSE"
    heading = f"{heading_level} {subject_code}"

    if paper_type_short == "gt":
        paper_line = "GRADE THRESHOLDS"
    else:
        paper_labels = {
            "qp": "QUESTION PAPER",
            "ms": "MARK SCHEME",
            "in": "INSERT",
        }
        paper_line = f"{paper_labels.get(paper_type_short, paper_type_short.upper())} {paper_no}"

    return heading, subject_name.upper(), paper_line


def create_public_cover_pdf(level, subject_name, subject_code, paper_type_short, paper_no):
    if not GENERAL_COVER_PATH or not os.path.exists(GENERAL_COVER_PATH):
        return None

    packet = BytesIO()
    page_width, page_height = A4
    cover = canvas.Canvas(packet, pagesize=A4)

    try:
        with Image.open(GENERAL_COVER_PATH) as img:
            img_width, img_height = img.size
    except Exception:
        return None

    page_ratio = page_width / page_height
    image_ratio = img_width / img_height if img_height else page_ratio

    if image_ratio > page_ratio:
        draw_height = page_height
        draw_width = draw_height * image_ratio
    else:
        draw_width = page_width
        draw_height = draw_width / image_ratio if image_ratio else page_height

    x = (page_width - draw_width) / 2
    y = (page_height - draw_height) / 2

    cover.drawImage(
        ImageReader(GENERAL_COVER_PATH),
        x,
        y,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
    )
    heading, title, paper_line = build_cover_lines(
        subject_name, paper_type_short, paper_no, level, subject_code
    )

    left_margin = 70
    title_y = 560
    line_gap = 64

    cover.setFillColor(white)
    cover.setFont(COVER_FONT_NAME, 30)
    cover.drawString(left_margin, title_y, heading[:24])

    cover.setFont(COVER_FONT_NAME, 38)
    cover.drawString(left_margin, title_y - line_gap, title[:22])

    cover.setFont(COVER_FONT_NAME, 24)
    cover.drawString(left_margin, title_y - (line_gap * 2), paper_line[:24])

    cover.showPage()
    cover.save()
    packet.seek(0)
    return packet


def download_paper(args):
    subject_code, session, year_suffix, paper_type_short, paper_no = args

    if paper_type_short == "gt":
        filename = f"{subject_code}_{session}{year_suffix}_gt.pdf"
    else:
        filename = f"{subject_code}_{session}{year_suffix}_{paper_type_short}_{paper_no}.pdf"

    url = f"https://pastpapers.papacambridge.com/directories/CAIE/CAIE-pastpapers/upload/{filename}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
        if response.status_code == 200 and response.content.startswith(b"%PDF"):
            return paper_no, filename, BytesIO(response.content)
        return paper_no, filename, None
    except Exception:
        return paper_no, filename, None


def render_home_page():
    st.markdown(
        """
<div class="page-card">
<h3 style="margin-top:0;">Public General Paper Compiler</h3>
<p style="margin-bottom:0;">Download and merge CAIE papers with a public general cover design.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")

    level_choice = st.radio("Select Level", ["IGCSE", "A Level"], horizontal=True)
    subjects = IGCSE_SUBJECTS if level_choice == "IGCSE" else ALEVEL_SUBJECTS
    subject_name = st.selectbox("Select Subject", sorted(subjects.keys()))
    subject_code = subjects[subject_name]

    st.info(f"Selected: **{subject_name}** | Code: `{subject_code}`")

    current_year = int(datetime.now().year)
    col1, col2 = st.columns(2)
    with col1:
        year_start = st.number_input("Start Year", 2002, current_year, current_year - 5)
    with col2:
        year_end = st.number_input("End Year", 2002, current_year, current_year)

    session_labels = list(SESSION_OPTIONS.keys())
    selected_session_labels = st.multiselect("Select Sessions", session_labels, default=session_labels)
    sessions = [SESSION_OPTIONS[label] for label in selected_session_labels]

    paper_type = st.selectbox("Paper Type", list(PAPER_TYPE_OPTIONS.keys()))
    paper_type_short = PAPER_TYPE_OPTIONS[paper_type]

    if paper_type_short != "gt":
        paper_input_raw = st.text_input("Enter Paper Numbers (example: 12 22 32)", "12 22 32 42")
    else:
        paper_input_raw = ""

    paper_input = format_papers(paper_input_raw)
    paper_numbers = [p.strip() for p in paper_input.split() if p.strip()]

    if st.button("Generate Public General Pack"):
        st.session_state["public_general_zip_bytes"] = None
        st.session_state["public_general_zip_name"] = None

        if paper_type_short != "gt" and not paper_numbers:
            st.error("Please enter at least one paper number.")
            return
        if not sessions:
            st.error("Please select at least one session.")
            return
        if not os.path.exists(GENERAL_COVER_PATH):
            st.error(f"Cover image not found: {GENERAL_COVER_PATH}")
            return

        tasks = []
        for year in range(year_start, year_end + 1):
            year_suffix = str(year)[2:]
            for session in sessions:
                if paper_type_short == "gt":
                    tasks.append((subject_code, session, year_suffix, paper_type_short, None))
                else:
                    for paper_no in paper_numbers:
                        tasks.append((subject_code, session, year_suffix, paper_type_short, paper_no))

        downloaded_by_number = {num: [] for num in paper_numbers}
        gt_downloads = []
        downloaded, failed = [], []

        st.write("### Download Progress")
        status_placeholder = st.empty()
        progress = st.progress(0)

        total_tasks = len(tasks)
        completed = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(download_paper, task): task for task in tasks}
            for future in concurrent.futures.as_completed(futures):
                paper_no, filename, content = future.result()

                if content:
                    content.seek(0)
                    if paper_type_short == "gt":
                        gt_downloads.append(content)
                    else:
                        downloaded_by_number[paper_no].append(content)
                    downloaded.append(filename)
                else:
                    failed.append(filename)

                completed += 1
                progress.progress(completed / total_tasks)
                status_placeholder.caption(f"Processed {completed}/{total_tasks} files")

        if not downloaded:
            st.warning("No valid PDFs were downloaded, so no merged files were created.")
            return

        output_zip = BytesIO()
        with zipfile.ZipFile(output_zip, "w") as zf:
            if paper_type_short == "gt":
                merger = PdfMerger()
                cover_pdf = create_public_cover_pdf(level_choice, subject_name, subject_code, paper_type_short, None)
                if cover_pdf:
                    merger.append(cover_pdf)
                for pdf in gt_downloads:
                    pdf.seek(0)
                    merger.append(pdf)
                merged_pdf = BytesIO()
                merger.write(merged_pdf)
                merger.close()
                merged_pdf.seek(0)
                zf.writestr(
                    f"{level_choice}_{subject_code}_Grade_Thresholds_Public_General.pdf",
                    merged_pdf.getvalue(),
                )
            else:
                for num in paper_numbers:
                    pdf_list = downloaded_by_number.get(num, [])
                    if not pdf_list:
                        continue

                    merger = PdfMerger()
                    cover_pdf = create_public_cover_pdf(
                        level_choice, subject_name, subject_code, paper_type_short, num
                    )
                    if cover_pdf:
                        merger.append(cover_pdf)
                    for pdf in pdf_list:
                        pdf.seek(0)
                        merger.append(pdf)
                    merged_pdf = BytesIO()
                    merger.write(merged_pdf)
                    merger.close()
                    merged_pdf.seek(0)
                    zf.writestr(
                        f"{level_choice}_{subject_code}_Paper_{num}_Public_General.pdf",
                        merged_pdf.getvalue(),
                    )

        output_zip.seek(0)
        update_data_log(
            level_choice,
            subject_name,
            subject_code,
            len(paper_numbers) if paper_type_short != "gt" else 1,
            len(downloaded),
            len(failed),
        )

        st.session_state["public_general_zip_bytes"] = output_zip.getvalue()
        st.session_state["public_general_zip_name"] = f"{level_choice}_{subject_code}_public_general_pack.zip"
        st.success(f"Downloaded {len(downloaded)} papers. {len(failed)} failed.")

    if st.session_state["public_general_zip_bytes"]:
        st.write("")
        st.markdown(
            """
<div class="download-card">
<strong>Your ZIP is ready.</strong><br>
Use the blue button below to download the generated public general pack.
</div>
""",
            unsafe_allow_html=True,
        )
        st.download_button(
            "Download Public General ZIP",
            st.session_state["public_general_zip_bytes"],
            file_name=st.session_state["public_general_zip_name"],
            mime="application/zip",
            use_container_width=True,
            key="public_general_zip_download",
        )



def render_about_page():
    st.markdown(
        """
<div class="page-card">
<h3 style="margin-top:0;">About The Public General Version</h3>
<p>This version is designed for general public use with a clean branded cover style and a simpler interface.</p>
<ul>
  <li>Friendly session labels for teachers</li>
  <li>Public general cover generation</li>
  <li>Automatic merging by paper number</li>
  <li>ZIP export of final merged files</li>
</ul>
</div>
""",
        unsafe_allow_html=True,
    )


def render_request_page():
    st.markdown(
        """
<div class="page-card">
<h3 style="margin-top:0;">Request A Free Custom School Past Paper Merger</h3>
<p>If your school wants a custom branded past paper merger, you can submit a request here for free.</p>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")

    with st.form("school_request_form"):
        school_name = st.text_input("School Name")
        contact_name = st.text_input("Contact Person")
        contact_email = st.text_input("Contact Email")
        country = st.text_input("Country")
        notes = st.text_area("What would you like in your custom school version?")
        submitted = st.form_submit_button("Submit Request")

    if submitted:
        if not school_name or not contact_name or not contact_email:
            st.error("Please fill in the school name, contact person, and contact email.")
            return

        payload = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "school_name": school_name,
            "contact_name": contact_name,
            "contact_email": contact_email,
            "country": country,
            "notes": notes,
        }

        save_school_request(payload)

        try:
            email_sent, email_error = send_school_request_notification(payload)
        except Exception as exc:
            email_sent, email_error = False, str(exc)

        try:
            confirmation_sent, confirmation_error = send_requester_confirmation_email(payload)
        except Exception as exc:
            confirmation_sent, confirmation_error = False, str(exc)

        if email_sent and confirmation_sent:
            st.success("Your request has been saved, emailed to the admin, and confirmed to the requester.")
        elif email_sent:
            st.warning(
                f"Your request was saved and emailed to the admin, but the requester confirmation email was not sent. {confirmation_error}"
            )
        else:
            st.warning(f"Your request was saved, but email notification was not sent. {email_error}")


page = st.radio(
    "Navigation",
    ["Main Page", "About", "Request Custom School Version"],
    horizontal=True,
    label_visibility="collapsed",
)

if not st.session_state["startup_popup_seen"]:
    show_startup_popup()

if page == "Main Page":
    render_home_page()
elif page == "About":
    render_about_page()
else:
    render_request_page()


st.markdown(
    """
<hr style="margin-top: 50px; border: none; height: 1px; background-color: #333;">
<div style='text-align: center; font-size: 0.8rem; color: #888; padding-bottom: 20px;'>
© 2026 PaperPort Public General Version. All rights reserved. <br> Created by Fernando Gabriel Morera.
</div>
""",
    unsafe_allow_html=True,
)
