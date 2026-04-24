import streamlit as st
import pdfplumber
import re
import json
import tempfile
from docxtpl import DocxTemplate
from openai import OpenAI
import os
from dotenv import load_dotenv
from datetime import date
import io

def main():
    
    # ===== CONFIG =====
    st.set_page_config(page_title="CV Automated ForMAtter", layout="centered")
    st.title("📄 Mekong CV ForMAtter 2026")
    min_date = date(1928, 1, 1)
    max_date = date(2028, 1, 1)
    # === Single-input fields ===
    name = st.text_input("Enter expert's name:")
    title = st.text_input("Enter expert title:")
    nationality = st.text_input("Enter expert's nationality:")
    dob = st.date_input(
        "Enter expert's day of birth", 
        value=date.today(), 
        min_value=min_date, 
        max_value=max_date
    )


    # === Multiple-input fields ===
    languages_count = st.number_input("Enter the number of languages (e.g: 1, 4,..):", min_value=0, step=1)
    education_count = st.number_input("Enter the number of education entries (e.g: 1, 4,..):", min_value=0, step=1)
    employment_count = st.number_input("Enter the number of employment entries (e.g: 1, 4,..):", min_value=0, step=1)

   # ==== Template Input ====
    # FIX: store template bytes so DocxTemplate can be re-created fresh for each render
    template_file = st.file_uploader("Upload your Template (DOCX)", type=["docx"])
    if template_file is None:
        st.warning("Please upload a DOCX template to proceed.")
        return
 
    # Read bytes once; validate the template is readable before going further
    template_bytes = template_file.read()
    try:
        DocxTemplate(io.BytesIO(template_bytes))  # dry-run: catches corrupt files & bad Jinja2 tags
    except Exception as e:
        st.error(
            "⚠️ Could not read the template. "
            "Make sure all `{{ }}` and `{% %}` tags are typed directly in Word "
            "(not copy-pasted) and are not split across formatting runs. "
            f"Detail: {e}"
        )
        return
    # ===== JSON for automation formatting =====
    cv_data_p1 = {
        "name": name,
        "title": title,
        "nationality": nationality,
        "dob": str(dob),
        "languages": ["" for _ in range(languages_count)],
        "education": ["" for _ in range(education_count)],
        "employment": ["" for _ in range(employment_count)]
    }

    expert_name = cv_data_p1["name"].replace(" ", "_").replace("/", "")

    # === Generate Word Document ===

    if st.button("🚀  Fill personal information"):
        if not name or not title or not nationality:
            st.error("Please fill in all required fields.")
        else:
        # === Generate Word Document ===
            docs = DocxTemplate(io.BytesIO(template_bytes))
            file_path_p1 = fill_data(cv_data_p1, docs)
            if file_path_p1:
                st.session_state.generate_file = file_path_p1
                st.session_state.stage = "generated"

    if st.session_state.get("stage") == "generated":
        st.success("Name, Title, Nationality have added. All rows are needed for professional information is added as well")
        col1, col2 = st.columns(2)
        # 5. Download button
        with col1:
            expert_name_manual = f"{expert_name}_personal_info_cv.docx"
            download_button(st.session_state.generate_file, expert_name_manual)
        with col2:
            if st.button("✏️ Fill Detailed Information"):
                st.session_state.stage = "detail_input"

    if st.session_state.get("stage") == "detail_input":
        input_cv = st.file_uploader("Upload your CV (PDF)", type=["pdf"])
        context = st.text_area("Additional Information (e.g: specific formatting requirements, key achievements to highlight, etc.):",
                              placeholder="It's optional"
                              )
        if input_cv:
            if st.button("🚀  Fill professional information"):
                with st.spinner("Extracting information from CV..."):
                    cv_text = extract_text_from_cv(input_cv) #EXTRACT DETAILED INFOR
                with st.spinner("Asking AI to structure the data..."):
                    cv_data_p2 = detail_infor_extraction(
                        name, title, nationality, str(dob), 
                        cv_text, context, 
                        int(languages_count), int(education_count), 
                        int(employment_count)
                    )
                if cv_data_p2 is not None:
                    with st.spinner("Filling template..."):
                        docs2 = DocxTemplate(io.BytesIO(template_bytes))
                        file_path_p2 =  fill_data(cv_data_p2, docs2)
                    if file_path_p2:
                        expert_name_auto = f"{expert_name}_auto_fill.docx"
                        download_button(file_path_p2, expert_name_auto)
                

            

def detail_infor_extraction(name, title, nationality, dob,
                             cv_text, context,
                             languages_count=0, education_count=0,
                             employment_count=0):

 
    prompt = f"""
        Extract structured information from the CV text below and the additional context.
 
        Return ONLY valid JSON. NO explanation, NO markdown, NO code fences.
        The JSON structure MUST match the schema below EXACTLY.
 
        =====================
        EXTRACTION RULES
        =====================
 
        1. LANGUAGES
        - Extract explicitly listed languages only.
        - Infer mother tongue from nationality: {nationality}
        - Map proficiency descriptions to exactly one of: "Basic", "Intermediate", "Advanced", "Native"
          for each of speaking, reading, writing.
        - Produce exactly {languages_count} entries.
 
        2. EDUCATION
        - Extract ONLY formal university degrees (Bachelor, Master, PhD/Doctorate).
        - Copy school_name, degree, and date EXACTLY from the CV text — do not paraphrase.
        - Produce exactly {education_count} entries.
 
        3. EMPLOYMENT RECORD
        - Include ONLY positions whose total duration is MORE THAN 12 months (1 year).
        - Produce exactly {employment_count} entries, picking the longest/most relevant ones.
        - from_date and to_date: write the exact start and end of the engagement (e.g. "June 2015", "December 2017").
          If the position is ongoing, write "Present" for to_date.
        - employer: organisation name only, copied exactly from the CV.
        - position: job title only, copied exactly from the CV.
 
        4. PROFESSIONAL CERTIFICATES & ASSOCIATIONS
        - List ALL certifications and professional memberships found in the CV.
        - Return certification/membership names ONLY — no year, no issuing body.
        - Format as a bullet list using "• " prefix, one per line, e.g.:
            "• Google Data Analytics Professional Certificate\n• PRINCE2 Practitioner"
        - If the CV states "None" for memberships, skip that; still list all certifications.
 
        5. COUNTRIES OF WORK EXPERIENCE
        - List every unique country where the expert has worked, studied, or been based.
        - Return as country names separated by commas ONLY, e.g. "Country_1, Country_2"
        - No extra words, no labels, just the country names.
 
        6. WORK UNDERTAKEN (EXPERIENCE)
        - Copy the assignment descriptions AS-IS from the CV text — exact wording, exact details.
        - ONLY apply adjustments explicitly requested in the context below. If the context says
          to highlight something, add or reorder content for that point only. Do not rephrase
          anything that is not mentioned in the context. 
        - The user's context is: {context}
 
        =====================
        JSON SCHEMA
        =====================
        {{
            "name": "{name}",
            "title": "{title}",
            "nationality": "{nationality}",
            "dob": "{dob}",
            "languages": [
                {{
                    "name_l": "<language name>",
                    "speaking": "<Basic|Intermediate|Advanced|Native>",
                    "reading": "<Basic|Intermediate|Advanced|Native>",
                    "writing": "<Basic|Intermediate|Advanced|Native>"
                }}
            ],
            "education": [
                {{
                    "school_name": "<exact institution name and location>",
                    "degree": "<exact degree name>",
                    "date": "<exact date range from CV>"
                }}
            ],
            "employment": [
                {{
                    "from_date": "<start month and year>",
                    "to_date": "<end month and year or Present>",
                    "employer": "<exact organisation name>",
                    "position": "<exact job title>"
                }}
            ],
            "cert_asso": "<all certifications and memberships, one per line>",
            "country_work": "<comma-separated list of countries>",
            "experiences": "",
        }}
 
        =====================
        CV TEXT:
        {cv_text}
 
        CONTEXT (use this to tailor the experience descriptions):
        {context}
        """
 
    load_dotenv()
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=st.secrets["GROQ_API_KEY"]
    )
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    result = response.choices[0].message.content
 
    try:
        data = json.loads(result.strip())
        return data
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data
            except json.JSONDecodeError:
                pass
        st.warning(
            "The AI returned a response that could not be parsed. "
            "Try again — if it keeps failing, simplify the context text or reduce the number of entries."
        )
        return None

def extract_text_from_cv(input_cv):
     with pdfplumber.open(input_cv) as pdf:
        extracted_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return extracted_text
    
def fill_data(data, docs=None):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            docs.render(data)
            docs.save(tmp.name)
            return tmp.name
    except Exception as e:
        msg = str(e)
        if "TemplateSyntaxError" in msg or "jinja2" in msg.lower():
            st.error(
                "The template has a Jinja2 tag error. "
                "Open the .docx in Word, delete and retype any {{ }} or {% %} tags directly "
                "(do not copy-paste them), then re-upload."
            )
        else:
            st.error(f"Failed to fill the template: {msg}")
        return None
    

def download_button(file_path, name):
    with open(file_path, "rb") as f:
        st.download_button(
            "📥 Download CV",
            f,
            file_name=f"{name}_formatted_cv.docx"
        )


if __name__ == "__main__":
    main()
