"""
AI Question Generator - Subjective Questions Only
Uses Groq API for generating descriptive/subjective questions
"""

import os
import requests
import json
import re
from typing import List, Dict
from dotenv import load_dotenv
load_dotenv()


class AIQuestionGenerator:
    """
    AI-powered question generator using Groq API
    Generates ONLY subjective/descriptive questions
    Supports difficulty levels: Easy, Medium, Hard
    """

    def __init__(self, api_key: str = None):
        """Initialize with Groq API key"""
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("Groq API key not set. Set GROQ_API_KEY in .env")

        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def generate_subjective_questions(
        self,
        syllabus_text: str,
        count: int,
        marks: int,
        difficulty: str = 'Medium'
    ) -> List[Dict]:

        difficulty_guidelines = {
            'Easy': "Questions should test basic understanding and recall.",
            'Medium': "Questions should test application and explanation.",
            'Hard': "Questions should test critical thinking and analysis."
        }

        syllabus_text_limited = syllabus_text[:4000]

        prompt = f"""
You are an expert exam question generator.

Difficulty: {difficulty}
Guideline: {difficulty_guidelines.get(difficulty)}

Syllabus:
{syllabus_text_limited}

Generate exactly {count} subjective questions.
Each question worth {marks} marks.

Return ONLY valid JSON:
{{
    "questions": [
        {{
            "question": "...",
            "model_answer": "...",
            "difficulty": "{difficulty}",
            "marks": {marks},
            "key_concepts": ["a","b"]
        }}
    ]
}}
"""

        try:
            response = self._call_groq_api(prompt)
            return self._parse_subjective_response(response, count, marks, difficulty)
        except Exception as e:
            print("Generation error:", e)
            return self._generate_fallback_subjective(count, marks, difficulty)

    def _call_groq_api(self, prompt: str) -> str:

        payload = {
           "model": "llama-3.1-8b-instant",

            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4096
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        response = requests.post(
            self.api_url,
            json=payload,
            headers=headers,
            timeout=60
        )

        if response.status_code != 200:
            raise Exception(f"Groq API error: {response.text}")

        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _parse_subjective_response(
        self,
        response: str,
        count: int,
        marks: int,
        difficulty: str
    ) -> List[Dict]:

        response = re.sub(r'^```json', '', response).strip()
        response = re.sub(r'^```', '', response).strip()
        response = re.sub(r'```$', '', response).strip()

        json_match = re.search(r'\{.*\}', response, re.DOTALL)

        if not json_match:
            raise ValueError("No JSON detected")

        data = json.loads(json_match.group())

        questions = data.get("questions", [])

        cleaned = []
        for i, q in enumerate(questions[:count]):
            cleaned.append({
                "question": q.get("question", f"Question {i+1}"),
                "model_answer": q.get("model_answer", ""),
                "difficulty": q.get("difficulty", difficulty),
                "marks": q.get("marks", marks),
                "key_concepts": q.get("key_concepts", [])
            })

        return cleaned

    def _generate_fallback_subjective(self, count, marks, difficulty):

        fallback = []

        for i in range(count):
            fallback.append({
                "question": f"Sample {difficulty} question {i+1}",
                "model_answer": "Sample model answer.",
                "difficulty": difficulty,
                "marks": marks,
                "key_concepts": []
            })

        return fallback


question_generator = AIQuestionGenerator()


def test_generator():
    syllabus = "Photosynthesis converts sunlight into chemical energy."

    qs = question_generator.generate_subjective_questions(
        syllabus, 2, 5, 'Medium'
    )

    for q in qs:
        print(q["question"])
        print(q["model_answer"][:100])


if __name__ == '__main__':
    test_generator()
