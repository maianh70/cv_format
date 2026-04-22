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

def main():
    
    # ===== CONFIG =====
    st.set_page_config(page_title="CV Automated ForMAtter", layout="centered")
    st.title("📄 Mekong CV ForMAtter 2026")

    # === Single-input fields ===
    name = st.text_input("Enter expert's name:")
    title = st.text_input("Enter expert title:")
    nationality = st.text_input("Enter expert's nationality:")
    dob = st.date_input("Enter expert's day of birth", value=date.today())


    # === Multiple-input fields ===
    languages_count = st.number_input("Enter the number of languages (e.g: 1, 4,..):", min_value=0, step=1)
    education_count = st.number_input("Enter the number of education entries (e.g: 1, 4,..):", min_value=0, step=1)
    employment_count = st.number_input("Enter the number of employment entries (e.g: 1, 4,..):", min_value=0, step=1)
    experience_count = st.number_input("Enter the number of experience entries (e.g: 1, 4,..):", min_value=0, step=1)

    # ==== Template Input ====
    template = st.file_uploader("Upload your Template (DOCX)", type=["docx"])
    if template is not None:
        docs = DocxTemplate(template)
    else:
        st.warning("Please upload a DOCX template to proceed.")
        return

    # ===== JSON for automation formatting =====
    cv_data_p1 = {
    "name": name,
    "title": title,
    "nationality": nationality,
    "dob": dob,
    "languages": ["" for _ in range(languages_count)],
    "education": ["" for _ in range(education_count)],
    "employment": ["" for _ in range(employment_count)],
    "experiences": ["" for _ in range(experience_count)]
    }

    expert_name = cv_data_p1["name"].replace(" ", "_").replace("/", "")

    # === Generate Word Document ===

    if st.button("🚀  Fill personal information"):
        if template is None or not name or not title or not nationality:
            st.error("Please fill in all required fields.")
        else:
        # === Generate Word Document ===

            file_path_p1 = fill_data(cv_data_p1, docs)

            st.session_state.generate_file = file_path_p1
            st.session_state.stage = "generated"

    if st.session_state.get("stage") == "generated":

        st.success("name, title, nationality have added. All rows are needed for professional information is added as well")

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
        context = st.text_area("Additional Information (e.g: specific formatting requirements, key achievements to highlight, etc.):",)
        if input_cv and context:
            if st.button("🚀  Fill professional information"):
                try:
                    cv_text = extract_text_from_cv(input_cv) #EXTRACT DETAILED INFOR
                    cv_data_p2 = detail_infor_extraction(name, title, nationality, cv_text, context, languages_count, education_count, employment_count, experience_count)
                    file_path_p2 =  fill_data(cv_data_p2, docs)
                    expert_name_auto = f"{expert_name}_auto_fill.docx"
                    download_button(file_path_p2, expert_name_auto)
                except Exception as e:
                    st.error(f"Error processing CV: {e}")

            


def detail_infor_extraction(cv_text, context, name, title, nationality, dob, languages_count=0, education_count=0, employment_count=0, experience_count=0):
    prompt = f"""
        Extract structured information from the CV text below and the additional context.

        Return ONLY valid JSON that matches these keys below. 
        The JSON structure MUST match the provided schema EXACTLY
        NO EXPLANATION.
        Make sure to fetch:
        {languages_count} iteams for the key "languages", 
        {education_count} iteams for the key "education", 
        {employment_count} iteams for the key "employment", 
        {experience_count} iteams for the key "experiences".


        SPECIAL EXTRACTION RULES

        1. LANGUAGES
        - If languages are explicitly listed → extract them
        - Infer mother tongue based on their nationalities: {nationality}
        - Categorize proficiency levels into "Basic", "Intermediate", "Advanced", "Native" based on descriptions in the CV for each skills (speaking, reading, writing).
        
        2. EDUCATION
        - Extract ONLY formal degrees
        - Copy EXACT from original text, do NOT infer or rewrite for school_name, degree, date

        3. EMPLOYMENT
        - Copy EXACT from original text, do NOT infer or rewrite
    


        JSON FORMAT:
        {{
            "name": "{name}",
            "title": "{title}",
            "nationality": "{nationality}",
            "dob": "{dob}"
            "languages": [
                {{
                    "name_l": "",
                    "speaking": "",
                    "reading": "",
                    "writing": ""
                }}
            ],
            "education": [
                {{
                    "school_name": "",
                    "degree": "",
                    "date": ""
                }}
            ],
            "employment": [
            {{
                "from_date": "",
                "to_date": "",
                "employer": "",
                "position": ""
            }}
            ],
            "experiences": ["" for _ in range(experience_count)]
            ]
        }}

        CV TEXT:
        {cv_text}
        CONTEXT:
        {context}
        """

    load_dotenv()
    # ===== API SETUP =====
    client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=st.secrets["GROQ_API_KEY"]
    )
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )
    result = response.choices[0].message.content
    
    try:
        data = json.loads(result.strip())
        return data
    except json.JSONDecodeError:
        # Fallback: extract JSON using regex
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            #st.write("Extracted JSON:", json_str[:1000] + "..." if len(json_str) > 1000 else json_str)
            data = json.loads(json_str)
            return data
        else:
            raise ValueError("Could not extract valid JSON from the response") 


def extract_text_from_cv(input_cv):
     with pdfplumber.open(input_cv) as pdf:
        extracted_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return extracted_text
    
def fill_data(data, docs=None):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        docs.render(data)
        docs.save(tmp.name)
        return tmp.name

def download_button(file_path, name):
    with open(file_path, "rb") as f:
        st.download_button(
            "📥 Download CV",
            f,
            file_name=f"{name}_formatted_cv.docx"
        )
def generate_word(data, docs, file_name, name):
    fill_data(data, docs=None)
    download_button(file_path, name)

if __name__ == "__main__":
    main()
