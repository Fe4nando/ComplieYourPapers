import streamlit as st
import requests
from PyPDF2 import PdfMerger
from io import BytesIO
import zipfile
import re
import concurrent.futures
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont
import os
import json
from datetime import datetime

LEVELS = st.secrets["LEVELS"]
DOWNLOAD_DIR = st.secrets["DOWNLOAD_DIR"]
HEADERS = json.loads(st.secrets["HEADERS"])
SESSIONS_ALL = st.secrets["SESSIONS_ALL"]

IGCSE_SUBJECTS = json.loads(st.secrets["IGCSE_SUBJECTS"])
ALEVEL_SUBJECTS = json.loads(st.secrets["ALEVEL_SUBJECTS"])

ALL_SUBJECTS = {
    "IGCSE": sorted(IGCSE_SUBJECTS.keys()),
    "A-Level": sorted(ALEVEL_SUBJECTS.keys())
}

st.set_page_config(page_title="PaperPort Web", page_icon="🎓",  layout="wide" )

st.markdown("""
    <style>
    .logo-container {
        display: flex;
        flex-direction: column;
        align-items: flex-start; /* left align; use center for centered version */
        margin-bottom: -10px;
    }
    .logo-container img {
        height: 80px;
        margin-bottom: 10px;
    }
    .logo-title {
        font-size: 2rem;
        font-weight: 700;
        color: #0A1D4E;
        font-family: 'Poppins', sans-serif;
    }
    </style>
    <div class="logo-container">
        <img src="https://raw.githubusercontent.com/Fe4nando/ComplieYourPapers/main/logo.png" alt="Logo">
        <div class="logo-title">Past Paper Downloader and Merger (Early Access)</div>
    </div>
""", unsafe_allow_html=True)

st.write("")

DATA_FILE = "data.json"

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"total_downloads": 0, "logs": []}, f, indent=4)

def update_data_log(level, subject_name, subject_code, num_papers, success_count, fail_count):
    """Update data.json with download event"""
    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    data["total_downloads"] = data.get("total_downloads", 0) + 1
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "subject_name": subject_name,
        "subject_code": subject_code,
        "papers_selected": num_papers,
        "success": success_count,
        "failed": fail_count
    }
    data["logs"].append(log_entry)

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

level_choice = st.radio("Select Level:", ["IGCSE", "A Level"], horizontal=True)

subjects = IGCSE_SUBJECTS if level_choice == "IGCSE" else ALEVEL_SUBJECTS
subject_name = st.selectbox("Select Subject", sorted(subjects.keys()))
subject_code = subjects[subject_name]

st.info(f"Selected: **{subject_name}**  |  Code: `{subject_code}`")

alias_name = ""
if len(subject_name) > 16:
    alias_name = st.text_input(
        "✏️ Alias for Cover (Short Name)",
        placeholder="Enter a shorter name for the cover page"
    )
current_year = int(datetime.now().year)
col1, col2 = st.columns(2)
with col1:
    year_start = st.number_input("Start Year", min_value=2002, max_value=current_year, value=current_year-5)
with col2:
    year_end = st.number_input("End Year", min_value=2002, max_value=current_year, value=current_year)

sessions = st.multiselect("Select Sessions", ["m", "s", "w"], default=["m", "s","w"])

# =========================
# PAPER TYPE + INPUT LOGIC
# =========================

paper_type = st.selectbox(
    "Paper Type",
    ["qp (Question Paper)", "ms (Mark Scheme)", "in (Insert)", "gt (Grade Thresholds)"]
)

paper_type_short = paper_type.split(" ")[0]

if paper_type_short != "gt":
    paper_input_raw = st.text_input("Enter Paper Numbers (e.g. 12 22 32)", "12 22 32 42")
else:
    paper_input_raw = ""

def format_papers(text):
    cleaned = re.sub(r"\D", "", text)
    groups = [cleaned[i:i+2] for i in range(0, len(cleaned), 2)]
    return " ".join([g for g in groups if g])

paper_input = format_papers(paper_input_raw)
paper_numbers = [p.strip() for p in paper_input.split() if p.strip()]


# =========================
# DOWNLOAD FUNCTION
# =========================

def download_paper(args):
    subject_code, session, year_suffix, paper_type_short, paper_no = args

    if paper_type_short == "gt":
        filename = f"{subject_code}_{session}{year_suffix}_gt.pdf"
    else:
        filename = f"{subject_code}_{session}{year_suffix}_{paper_type_short}_{paper_no}.pdf"

    url = f"https://pastpapers.papacambridge.com/directories/CAIE/CAIE-pastpapers/upload/{filename}"

    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200 and r.content.startswith(b"%PDF"):
            return paper_no, filename, BytesIO(r.content)
        else:
            return paper_no, filename, None
    except Exception:
        return paper_no, filename, None


# =========================
# DOWNLOAD BUTTON LOGIC
# =========================

if st.button("⚡ Download & Merge Papers"):

    if paper_type_short != "gt" and not paper_numbers:
        st.error("Please enter at least one paper number.")
    else:

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

        uploaded_cover_path = None
        if cover_image:
            uploaded_cover_path = os.path.join(os.getcwd(), "uploaded_cover.png")
            with open(uploaded_cover_path, "wb") as f:
                f.write(cover_image.read())

        st.write("### 📥 Download Progress:")
        status_placeholder = st.empty()
        progress = st.progress(0)

        total_tasks = len(tasks)
        completed = 0
        status_lines = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(download_paper, t): t for t in tasks}

            for future in concurrent.futures.as_completed(futures):
                paper_no, filename, content = future.result()

                if content:
                    content.seek(0)

                    if paper_type_short == "gt":
                        gt_downloads.append(content)
                    else:
                        downloaded_by_number[paper_no].append(content)

                    downloaded.append(filename)
                    status_lines.append(f"✅ {filename}")
                else:
                    failed.append(filename)
                    status_lines.append(f"⚠️ Not available: {filename}")

                completed += 1
                progress.progress(completed / total_tasks)
                status_placeholder.markdown("<br>".join(status_lines[-15:]), unsafe_allow_html=True)

        output_zip = BytesIO()

        with zipfile.ZipFile(output_zip, "w") as zf:

            # ===== GRADE THRESHOLDS =====
            if paper_type_short == "gt":

                if gt_downloads:
                    final_merger = PdfMerger()

                    for pdf in gt_downloads:
                        pdf.seek(0)
                        final_merger.append(pdf)

                    merged_pdf = BytesIO()
                    final_merger.write(merged_pdf)
                    final_merger.close()
                    merged_pdf.seek(0)

                    file_name = f"{level_choice}_{subject_code}_Grade_Thresholds_merged.pdf"
                    zf.writestr(file_name, merged_pdf.getvalue())

            # ===== NORMAL PAPERS =====
            else:

                for num in paper_numbers:
                    pdf_list = downloaded_by_number.get(num, [])
                    if not pdf_list:
                        continue

                    cover_pdf_path = generate_cover_page(
                        level_choice,
                        subject_code,
                        subject_name,
                        alias_name,
                        num,
                        os.getcwd(),
                        uploaded_cover_path
                    )

                    cover_pdf = open(cover_pdf_path, "rb") if cover_pdf_path else None
                    final_merger = PdfMerger()

                    if cover_pdf:
                        final_merger.append(cover_pdf)

                    for b in pdf_list:
                        b.seek(0)
                        final_merger.append(b)

                    merged_pdf = BytesIO()
                    final_merger.write(merged_pdf)
                    final_merger.close()
                    merged_pdf.seek(0)

                    file_name = f"{level_choice}_{subject_code}_Paper_{num}_merged.pdf"
                    zf.writestr(file_name, merged_pdf.getvalue())

        output_zip.seek(0)
        zip_name = f"{level_choice}_{subject_code}_merged_papers.zip"

        update_data_log(
            level_choice,
            subject_name,
            subject_code,
            len(paper_numbers) if paper_type_short != "gt" else 1,
            len(downloaded),
            len(failed)
        )

        st.success(f"✅ Downloaded {len(downloaded)} papers. {len(failed)} failed.")

        st.download_button(
            label="⬇️ Download All Merged Files (ZIP)",
            data=output_zip.getvalue(),
            file_name=zip_name,
            mime="application/zip"
        )

        if failed:
            with st.expander("⚠️ Show Failed Downloads"):
                st.write("\n".join(failed))

st.markdown("""
    <hr style="margin-top: 50px; border: none; height: 1px; background-color: #333;">
    <div style='text-align: center; font-size: 0.8rem; color: #888; padding-bottom: 20px;'>
        © 2025 Paperport. All rights reserved. <br> Created by Fernando Gabriel Morera.
    </div>
""", unsafe_allow_html=True)










