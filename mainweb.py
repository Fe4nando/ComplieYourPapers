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
from dictionary import *
import os


st.set_page_config(page_title="PaperPilot Web", page_icon="📘")
st.title("📘 Past Paper Downloader (BETA)")


level_choice = st.radio("Select Level:", ["IGCSE", "A Level"], horizontal=True)

subjects = IGCSE_SUBJECTS if level_choice == "IGCSE" else ALEVEL_SUBJECTS
subject_name = st.selectbox("Select Subject", sorted(subjects.keys()))
subject_code = subjects[subject_name]

st.info(f"📘 Selected: **{subject_name}**  |  Code: `{subject_code}`")


alias_name = ""
if len(subject_name) > 16:
    alias_name = st.text_input(
        "✏️ Alias for Cover (Short Name)",
        placeholder="Enter a shorter name for the cover page"
    )


col1, col2 = st.columns(2)
with col1:
    year_start = st.number_input("Start Year", min_value=2000, max_value=2030, value=2023)
with col2:
    year_end = st.number_input("End Year", min_value=2000, max_value=2030, value=2025)

sessions = st.multiselect("Select Sessions", ["m", "s", "w"], default=["s", "w"])
paper_type = st.selectbox("Paper Type", ["qp (Question Paper)", "ms (Mark Scheme)"])


paper_input_raw = st.text_input("Enter Paper Numbers (e.g. 1236 or 011213)", "11 12 13")


st.markdown("### 🖼️ Upload a Cover Image (PNG) — or leave empty to use `template_base.png`")
cover_image = st.file_uploader("Upload PNG Cover", type=["png"])


def generate_cover_page(level_code, subject_code, subject_name, alias_name, paper_id, output_folder, uploaded_image_path=None):
    """Generate a front cover page PDF with GEMS layout style"""
    TEMPLATE_PATH = os.path.join(os.getcwd(), "template_base.png")
    image_path_to_use = uploaded_image_path if uploaded_image_path else TEMPLATE_PATH
    if not os.path.exists(image_path_to_use):
        st.warning("⚠️ No cover image found. Skipping cover generation.")
        return None


    image = Image.open(image_path_to_use).convert("RGB")
    draw = ImageDraw.Draw(image)

    try:
        font_large = ImageFont.truetype("Poppins-Bold.ttf", 106)
        font_medium = ImageFont.truetype("Poppins-Bold.ttf", 74)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()


    x_pos = 152
    y_start = 440
    spacing = 172

    if alias_name.strip():
        subject_display = alias_name.strip()
    elif len(subject_name) > 16:
        words = subject_name.split()
        subject_display = ' '.join(words[:2])
    else:
        subject_display = subject_name

    draw.text((x_pos, y_start), f"{level_code} {subject_code}", fill="black", font=font_large)
    draw.text((x_pos, y_start + spacing), subject_display, fill="black", font=font_large)
    draw.text((x_pos, y_start + spacing * 2), f"PAPER {paper_id}", fill="black", font=font_medium)

    os.makedirs(output_folder, exist_ok=True)
    pdf_path = os.path.join(output_folder, f"0000_COVER_{paper_id}.pdf")

    a4_width, a4_height = A4
    pdf_bytes = BytesIO()
    c = canvas.Canvas(pdf_bytes, pagesize=A4)
    img = ImageReader(image)
    c.drawImage(img, 0, 0, width=a4_width, height=a4_height)
    c.showPage()
    c.save()
    pdf_bytes.seek(0)

    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes.getvalue())

    return pdf_path


def format_papers(text):
    cleaned = re.sub(r"\D", "", text)
    groups = [cleaned[i:i+2] for i in range(0, len(cleaned), 2)]
    return " ".join([g for g in groups if g])

paper_input = format_papers(paper_input_raw)
paper_numbers = [p.strip() for p in paper_input.split() if p.strip()]

chip_style = """
<style>
.paper-chip {
    background-color: #0078D7;
    color: white;
    padding: 6px 12px;
    border-radius: 10px;
    display: inline-block;
    margin: 4px;
    font-weight: 600;
    font-size: 14px;
}
.paper-chip-container {
    display: flex;
    flex-wrap: wrap;
    margin-top: 6px;
}
</style>
"""
if paper_numbers:
    st.markdown(chip_style, unsafe_allow_html=True)
    chips_html = "<div class='paper-chip-container'>" + "".join(
        [f"<div class='paper-chip'>{p}</div>" for p in paper_numbers]
    ) + "</div>"
    st.markdown(chips_html, unsafe_allow_html=True)


def download_paper(args):
    subject_code, session, year_suffix, paper_type_short, paper_no = args
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


if st.button("⚡ Download & Merge Papers"):
    if not paper_numbers:
        st.error("Please enter at least one paper number.")
    else:
        paper_type_short = paper_type.split(" ")[0]
        downloaded_by_number = {num: [] for num in paper_numbers}
        downloaded, failed = [], []

        uploaded_cover_path = None
        if cover_image:
            uploaded_cover_path = os.path.join(os.getcwd(), "uploaded_cover.png")
            with open(uploaded_cover_path, "wb") as f:
                f.write(cover_image.read())

        st.write("### 📥 Download Progress:")
        status_placeholder = st.empty()
        progress = st.progress(0)

        tasks = []
        for year in range(year_start, year_end + 1):
            year_suffix = str(year)[2:]
            for session in sessions:
                for paper_no in paper_numbers:
                    tasks.append((subject_code, session, year_suffix, paper_type_short, paper_no))

        total_tasks = len(tasks)
        completed = 0
        status_lines = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(download_paper, t): t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                paper_no, filename, content = future.result()
                if content:
                    content.seek(0)
                    downloaded_by_number[paper_no].append(content)
                    downloaded.append(filename)
                    status_lines.append(f"✅ {filename}")
                else:
                    failed.append(filename)
                    status_lines.append(f"⚠️ Unable to download {filename}")
                completed += 1
                progress.progress(completed / total_tasks)
                status_placeholder.markdown("<br>".join(status_lines[-15:]), unsafe_allow_html=True)

        output_zip = BytesIO()
        with zipfile.ZipFile(output_zip, "w") as zf:
            for num in paper_numbers:
                pdf_list = downloaded_by_number.get(num, [])
                if not pdf_list:
                    continue

                cover_pdf_path = generate_cover_page(level_choice, subject_code, subject_name, alias_name, num, os.getcwd(), uploaded_cover_path)
                cover_pdf = open(cover_pdf_path, "rb") if cover_pdf_path else None

                final_merger = PdfMerger()
                if cover_pdf:
                    final_merger.append(cover_pdf)

                # Append all downloaded papers
                for b in pdf_list:
                    b.seek(0)
                    final_merger.append(b)

                # ✅ Append end.pdf if it exists
                end_pdf_path = os.path.join(os.getcwd(), "end.pdf")
                if os.path.exists(end_pdf_path):
                    with open(end_pdf_path, "rb") as end_pdf:
                        final_merger.append(end_pdf)
                else:
                    st.warning("⚠️ end.pdf not found — skipping end page for this file.")

                # Write merged file
                merged_pdf = BytesIO()
                final_merger.write(merged_pdf)
                final_merger.close()
                merged_pdf.seek(0)

                file_name = f"{level_choice}_{subject_code}_Paper_{num}_merged.pdf"
                zf.writestr(file_name, merged_pdf.getvalue())

        output_zip.seek(0)
        zip_name = f"{level_choice}_{subject_code}_merged_papers.zip"

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
