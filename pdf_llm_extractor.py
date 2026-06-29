"""
LLM-Based PDF Answer Extractor & Evaluator
Uses OCR (PyMuPDF/Tesseract) for text extraction + Groq API for evaluation.
Falls back to Gemini Vision if GEMINI_API_KEY is available and Groq fails.

Install: pip install pymupdf pytesseract requests python-dotenv
"""

import os
import json
import re
import requests
from io import BytesIO
from dotenv import load_dotenv
load_dotenv()

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
    if os.name == 'nt':
        default_win = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        env_cmd = os.environ.get('TESSERACT_CMD')
        if env_cmd and os.path.exists(env_cmd):
            pytesseract.pytesseract.tesseract_cmd = env_cmd
        elif os.path.exists(default_win):
            pytesseract.pytesseract.tesseract_cmd = default_win
except ImportError:
    TESSERACT_AVAILABLE = False

from PIL import Image, ImageFilter, ImageEnhance

# Optional: Gemini as fallback
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ── Groq API setup ───────────────────────────────────────────────────────────

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── OpenRouter API setup (Vision-capable, reads images directly) ──────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "google/gemma-4-31b-it:free"


def _get_openrouter_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    return key  # Returns None if not set


def _call_openrouter_vision(images: list, prompt: str, max_tokens: int = 4096) -> str:
    """Call OpenRouter with images (base64) for vision-based evaluation."""
    import base64
    
    api_key = _get_openrouter_key()
    if not api_key:
        raise EnvironmentError("OPENROUTER_API_KEY not set in .env")
    
    # Build content with images
    content = []
    for img in images:
        # Convert PIL image to base64
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}
        })
    
    # Add the text prompt
    content.append({"type": "text", "text": prompt})
    
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": content}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Smart Exam Evaluation System"
    }
    
    response = requests.post(OPENROUTER_API_URL, json=payload, headers=headers, timeout=120)
    
    if response.status_code != 200:
        raise Exception(f"OpenRouter API error ({response.status_code}): {response.text[:500]}")
    
    result = response.json()
    return result["choices"][0]["message"]["content"]


def _get_groq_key():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise EnvironmentError("GROQ_API_KEY not set in .env")
    return key


def _call_groq(prompt: str, max_tokens: int = 4096) -> str:
    """Call Groq API and return the response text."""
    api_key = _get_groq_key()
    
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert academic examiner. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    response = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"Groq API error ({response.status_code}): {response.text[:500]}")
    
    result = response.json()
    return result["choices"][0]["message"]["content"]


# ── PDF Text Extraction ───────────────────────────────────────────────────────

def _pdf_to_images(pdf_path: str, dpi: int = 300) -> list:
    """Convert every page of a PDF to a PIL Image."""
    if FITZ_AVAILABLE:
        doc = fitz.open(pdf_path)
        scale = dpi / 72
        mat = fitz.Matrix(scale, scale)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            mode = "RGBA" if pix.alpha else "RGB"
            try:
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            except Exception:
                img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
            images.append(img.convert("RGB"))
        doc.close()
        return images

    if PDF2IMAGE_AVAILABLE:
        try:
            return convert_from_path(pdf_path, dpi=dpi)
        except Exception as e:
            raise RuntimeError(f"pdf2image failed: {e}")

    raise RuntimeError("Cannot render PDF. Install PyMuPDF: pip install pymupdf")


def _extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from PDF using multiple methods:
    1. PyMuPDF direct text extraction (for digital PDFs)
    2. EasyOCR (for scanned/handwritten PDFs - no system install needed)
    3. Tesseract OCR as fallback
    """
    text = ""
    
    # Method 1: Try PyMuPDF direct text extraction
    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(pdf_path)
            for page_num, page in enumerate(doc):
                page_text = page.get_text()
                if page_text.strip():
                    text += f"\n--- Page {page_num + 1} ---\n{page_text}"
            doc.close()
            
            # If we got substantial text, it's a digital PDF
            if len(text.strip()) > 100:
                print(f"✓ Extracted text using PyMuPDF ({len(text)} chars)")
                return text.strip()
        except Exception as e:
            print(f"PyMuPDF text extraction failed: {e}")
    
    # Method 2: EasyOCR (handles handwriting well, no system install needed)
    if EASYOCR_AVAILABLE:
        try:
            print("Converting PDF to images for EasyOCR...")
            images = _pdf_to_images(pdf_path, dpi=300)
            print(f"Running EasyOCR on {len(images)} page(s)... (first run downloads model ~100MB)")
            
            reader = easyocr.Reader(['en'], gpu=False)
            
            for i, image in enumerate(images):
                # Convert PIL image to numpy array
                import numpy as np
                img_array = np.array(image)
                
                results = reader.readtext(img_array, detail=0, paragraph=True)
                page_text = "\n".join(results)
                
                if page_text.strip():
                    text += f"\n--- Page {i + 1} ---\n{page_text}"
            
            if text.strip():
                print(f"✓ Extracted text using EasyOCR ({len(text)} chars)")
                return text.strip()
        except Exception as e:
            print(f"EasyOCR extraction failed: {e}")
    
    # Method 3: Tesseract OCR as fallback
    if TESSERACT_AVAILABLE:
        try:
            print("Converting PDF to images for Tesseract OCR...")
            images = _pdf_to_images(pdf_path, dpi=300)
            print(f"Running Tesseract OCR on {len(images)} page(s)...")
            
            for i, image in enumerate(images):
                gray = image.convert("L")
                enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
                sharpened = enhanced.filter(ImageFilter.SHARPEN)
                
                page_text = pytesseract.image_to_string(
                    sharpened, config='--psm 6 --oem 3'
                )
                if page_text.strip():
                    text += f"\n--- Page {i + 1} ---\n{page_text}"
            
            if text.strip():
                print(f"✓ Extracted text using Tesseract ({len(text)} chars)")
                return text.strip()
        except Exception as e:
            print(f"Tesseract extraction failed: {e}")
    
    if not text.strip():
        return "Failed to extract text from PDF."
    
    return text.strip()


def _clean_json(raw: str) -> str:
    """Strip markdown fences from LLM output."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


# ── Main evaluation pipeline ─────────────────────────────────────────────────

def process_answer_sheet(pdf_path: str, questions: list) -> list:
    """
    Full pipeline: Extract and evaluate student answers from PDF.
    
    Strategy:
    1. Try OpenRouter Vision (sends images directly - best for handwriting)
    2. Fall back to OCR + Groq text evaluation

    Args:
        pdf_path:  Path to the student's answer sheet PDF.
        questions: List of dicts, each with keys:
                   'id' (model_answer_id), 'question_id', 'question_text', 'model_answer_text', 'marks'

    Returns:
        List of result dicts, one per question.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Build question guidelines for the prompt
    q_guidelines = []
    for idx, q in enumerate(questions):
        q_num = idx + 1
        q_guidelines.append(
            f"QUESTION {q_num} (ID={q['question_id']}): {q['question_text']}\n"
            f"Maximum Marks: {q['marks']}\n"
            f"Model Answer: {q['model_answer_text']}\n"
            f"----------------------------------------"
        )
    q_guidelines_text = "\n".join(q_guidelines)

    raw = None

    # ── Method 1: OpenRouter Vision (best for handwriting) ──────────────────
    if _get_openrouter_key():
        try:
            print("Converting PDF pages to images...")
            images = _pdf_to_images(pdf_path, dpi=200)
            print(f"Sending {len(images)} page(s) to OpenRouter Vision...")

            vision_prompt = f"""You are an expert academic examiner. Below are scanned pages of a student's exam answer sheet.

EXAM QUESTIONS, MARKS, AND MODEL ANSWERS:
{q_guidelines_text}

INSTRUCTIONS:
1. Carefully read the student's handwritten answers from the images.
2. For each question, transcribe the answer, evaluate against the model answer, and award marks.
3. Be strict but fair. If a question was not attempted, award 0 marks.
4. Write 2-3 sentences of constructive feedback per question.
5. Return ONLY valid JSON (no markdown, no explanation):
{{
  "results": [
    {{
      "question_number": 1,
      "question_id": "Q1",
      "student_answer": "Transcribed answer...",
      "awarded_marks": 4.5,
      "score_percentage": 90.0,
      "feedback": "Feedback here...",
      "missing_concepts": ["concept1"]
    }}
  ]
}}"""

            raw_response = _call_openrouter_vision(images, vision_prompt)
            raw = _clean_json(raw_response)
            print("✓ OpenRouter Vision evaluation complete")
        except Exception as e:
            print(f"OpenRouter Vision failed: {e}")
            raw = None

    # ── Method 2: OCR + Groq text evaluation (fallback) ─────────────────────
    if raw is None:
        print("Falling back to OCR + Groq evaluation...")
        extracted_text = _extract_text_from_pdf(pdf_path)
        
        if not extracted_text or extracted_text == "Failed to extract text from PDF.":
            raise ValueError("Could not extract any text from the PDF. Please ensure the PDF is readable.")
        
        print(f"Extracted {len(extracted_text)} characters, sending to Groq...")

    # Limit extracted text to avoid token limits
        max_text_len = 3000
        if len(extracted_text) > max_text_len:
            extracted_text = extracted_text[:max_text_len]

        groq_prompt = f"""You are an expert academic examiner evaluating a student's exam answers.

EXAM QUESTIONS, MARKS, AND MODEL ANSWERS:
{q_guidelines_text}

STUDENT'S EXTRACTED ANSWER SHEET TEXT:
{extracted_text}

INSTRUCTIONS:
1. For each question, find the student's answer from the extracted text.
2. If not attempted, set student_answer to "" and award 0 marks.
3. Evaluate based on conceptual correctness, key terms, and clarity.
4. Award marks up to Maximum Marks. Be strict but fair.
5. Return ONLY valid JSON (no markdown, no explanation):
{{
  "results": [
    {{
      "question_number": 1,
      "question_id": "Q1",
      "student_answer": "The student's answer...",
      "awarded_marks": 4.5,
      "score_percentage": 90.0,
      "feedback": "Feedback here...",
      "missing_concepts": ["concept1"]
    }}
  ]
}}"""

        raw_response = _call_groq(groq_prompt, max_tokens=4096)
        raw = _clean_json(raw_response)

    # ── Parse results ───────────────────────────────────────────────────────
    try:
        parsed = json.loads(raw)
        raw_results = parsed.get("results", [])
    except json.JSONDecodeError as e:
        print(f"LLM did not return valid JSON. Raw output:\n{raw[:500]}")
        raise ValueError(f"Evaluation failed to return valid JSON format: {e}")

    # Map results to questions
    results_map = {res.get("question_number"): res for res in raw_results}

    final_results = []
    for idx, q in enumerate(questions):
        q_num = idx + 1
        
        res = results_map.get(q_num)
        if not res:
            res = next((r for r in raw_results if str(r.get("question_id")) == str(q["question_id"])), None)

        if res:
            student_answer = str(res.get("student_answer", "")).strip()
            awarded_marks = float(res.get("awarded_marks", 0.0))
            score_percentage = float(res.get("score_percentage", 0.0))
            feedback = str(res.get("feedback", "")).strip()
            missing_concepts = res.get("missing_concepts", [])
        else:
            student_answer = ""
            awarded_marks = 0.0
            score_percentage = 0.0
            feedback = "No answer detected / evaluation skipped."
            missing_concepts = []

        max_marks = float(q["marks"])
        awarded_marks = max(0.0, min(max_marks, awarded_marks))
        score_percentage = max(0.0, min(100.0, score_percentage))

        final_results.append({
            "question_id":      q["question_id"],
            "question_number":  q_num,
            "model_answer_id":  q["id"],
            "student_answer":   student_answer,
            "score_percentage": score_percentage,
            "awarded_marks":    awarded_marks,
            "max_marks":        max_marks,
            "feedback":         feedback if student_answer else "Not attempted.",
            "missing_concepts": missing_concepts,
            "status":           "Attempted" if student_answer else "Not Attempted",
        })

    print(f"✓ Evaluation complete: {len(final_results)} questions processed")
    return final_results
