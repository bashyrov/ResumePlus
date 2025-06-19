import os

import tempfile
import zipfile
from django.shortcuts import render
from django.core.files.storage import FileSystemStorage
import pdfplumber
import json
import requests
import logging
from .models import Vacancy
from .services.openai_api import API_KEY, API_URL


logger = logging.getLogger(__name__)


def home(request):
    vacancy_ids = request.session.get('vacancy_ids', [])
    vacancies = Vacancy.objects.filter(id__in=vacancy_ids) if vacancy_ids else []
    return render(request, 'index.html', {'vacancies': vacancies})


def test(request):
    candidate = {
        "first_name": "John",
        "last_name": "Doe",
        "filename": "john_doe_resume.pdf",
        "match_percentage": 85,
        "matching_skills": ["Python", "Django", "SQL", "REST API"],
        "missing_skills": ["AWS", "Docker"],
        "rating": 8,
        "summary": "John is a strong candidate with extensive experience in Python and Django development. He has successfully delivered multiple web applications and demonstrates proficiency in SQL. However, he lacks experience with AWS and Docker, which are critical for the role."
    }
    return render(request, 'result.html', {
                'candidates': candidate,
                'vacancy_title': 'py-dev'}
                  )


def upload_resume(request):
    """Process a ZIP archive of resumes and rank candidates."""
    if request.method == 'POST' and request.FILES.get('file'):
        logger.info("Received file upload")
        file = request.FILES['file']

        if not file.name.endswith('.zip'):
            logger.error("Uploaded file is not a ZIP archive")
            vacancy_ids = request.session.get('vacancy_ids', [])
            vacancies = Vacancy.objects.filter(id__in=vacancy_ids) if vacancy_ids else []
            return render(request, 'analyze.html', {'error': 'Please upload a ZIP archive.', 'vacancies': vacancies})

        fs = FileSystemStorage()
        filename = fs.save(file.name, file)
        file_path = fs.path(filename)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                vacancy_id = request.POST.get('vacancy_id', '')
                if vacancy_id:
                    try:
                        vacancy = Vacancy.objects.get(id=vacancy_id)
                        job_title = vacancy.job_title
                        skills = vacancy.skills
                        experience = vacancy.experience
                        responsibilities = vacancy.responsibilities
                        level = vacancy.level
                        additional = vacancy.additional
                        skills_priority = vacancy.skills_priority
                        experience_priority = vacancy.experience_priority
                        education_priority = vacancy.education_priority
                    except Vacancy.DoesNotExist:
                        logger.error("Selected vacancy not found")
                        vacancy_ids = request.session.get('vacancy_ids', [])
                        vacancies = Vacancy.objects.filter(id__in=vacancy_ids) if vacancy_ids else []
                        return render(request, 'index.html', {'error': 'Selected vacancy not found.', 'vacancies': vacancies})
                else:
                    job_title = request.POST.get('job_title', '')
                    skills = request.POST.get('skills', '')
                    experience = request.POST.get('experience', '')
                    responsibilities = request.POST.get('responsibilities', '')
                    level = request.POST.get('level', '')
                    additional = request.POST.get('additional', '')
                    skills_priority = request.POST.get('skills_priority', '0')
                    experience_priority = request.POST.get('experience_priority', '0')
                    education_priority = request.POST.get('education_priority', '0')

                    try:
                        total_priority = int(skills_priority) + int(experience_priority) + int(education_priority)
                        if total_priority != 100:
                            logger.error("Criteria priorities do not sum to 100%")
                            vacancy_ids = request.session.get('vacancy_ids', [])
                            vacancies = Vacancy.objects.filter(id__in=vacancy_ids) if vacancy_ids else []
                            return render(request, 'index.html', {'error': 'Criteria priorities must sum to 100%.', 'vacancies': vacancies})
                    except ValueError:
                        logger.error("Invalid priority values")
                        vacancy_ids = request.session.get('vacancy_ids', [])
                        vacancies = Vacancy.objects.filter(id__in=vacancy_ids) if vacancy_ids else []
                        return render(request, 'analyze.html', {'error': 'Invalid priority values.', 'vacancies': vacancies})

                    vacancy = Vacancy.objects.create(
                        job_title=job_title,
                        skills=skills,
                        experience=experience,
                        responsibilities=responsibilities,
                        level=level,
                        additional=additional,
                        skills_priority=int(skills_priority),
                        experience_priority=int(experience_priority),
                        education_priority=int(education_priority)
                    )
                    vacancy_ids = request.session.get('vacancy_ids', [])
                    vacancy_ids.append(vacancy.id)
                    request.session['vacancy_ids'] = vacancy_ids
                    request.session.modified = True

                candidates = []
                for root, _, files in os.walk(temp_dir):
                    for pdf_file in files:
                        if not pdf_file.endswith('.pdf'):
                            continue

                        pdf_path = os.path.join(root, pdf_file)
                        try:
                            with pdfplumber.open(pdf_path) as pdf:
                                text = ""
                                for page in pdf.pages:
                                    text += page.extract_text() or ""
                                logger.info(f"Extracted text from {pdf_file}: {text[:100]}...")

                            if not text:
                                logger.warning(f"No text found in {pdf_file}")
                                continue

                            prompt = (
                                f"You are an expert HR analyst with deep knowledge of the current job market. Conduct an extremely strict evaluation of the following resume for the specified job vacancy, considering only the most relevant and in-demand skills, experience, and qualifications based on 2025 market standards. Extract the candidate's first name and last name from the resume text. Provide a detailed analysis, including: "
                                f"1. Percentage match between the candidate's skills/experience and the job requirements, weighted by the provided criteria priority. "
                                f"2. A list of matching skills and experiences that meet or exceed market standards. "
                                f"3. A list of missing skills or gaps critical for the role in the current market. "
                                f"4. A strict rating from 1 to 10 (1 = completely unsuitable, 10 = exceptional fit) based on market competitiveness, penalizing heavily for any gaps in critical skills or experience. "
                                f"5. A brief summary of the candidate's suitability, highlighting strengths and weaknesses relative to market demands (max 50 words on polish language). "
                                f"**Job Vacancy**: "
                                f"- Position: {job_title} "
                                f"- Requirements: "
                                f"  - Skills: {skills} "
                                f"  - Experience: {experience} "
                                f"  - Responsibilities: {responsibilities} "
                                f"  - Level: {level} "
                                f"  - Additional: {additional} "
                                f"- Criteria Priority: "
                                f"  - Skills: {skills_priority}% "
                                f"  - Experience: {experience_priority}% "
                                f"  - Education: {education_priority}% "
                                f"**Resume Text**: {text} "
                                f"**Output Format**: ```json {{ \"first_name\": \"<string>\", \"last_name\": \"<string>\", \"match_percentage\": <number>, \"matching_skills\": [<list of skills>], \"missing_skills\": [<list of skills>], \"rating\": <number>, \"summary\": \"<text>\" }} ```"
                            )

                            headers = {
                                "Authorization": f"Bearer {API_KEY}",
                                "Content-Type": "application/json"
                            }
                            data = {
                                "model": "gpt-4o",
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": 1000,
                                "temperature": 0.7
                            }
                            response = requests.post(API_URL, headers=headers, json=data)
                            response.raise_for_status()

                            try:
                                result = response.json()
                                content = result['choices'][0]['message']['content']
                                json_start = content.find('{')
                                json_end = content.rfind('}') + 1
                                if json_start == -1 or json_end == 0:
                                    logger.error(f"No valid JSON found in OpenAI response for {pdf_file}")
                                    continue
                                analysis = json.loads(content[json_start:json_end])
                                analysis['filename'] = pdf_file  # Store filename for reference
                                candidates.append(analysis)
                            except (json.JSONDecodeError, KeyError) as e:
                                logger.error(f"Failed to parse OpenAI response for {pdf_file}: {str(e)}")
                                continue

                        except Exception as e:
                            logger.error(f"Error processing {pdf_file}: {str(e)}")
                            continue

                candidates.sort(key=lambda x: x.get('match_percentage', 0), reverse=True)
                top_candidates = candidates[:10]

            fs.delete(filename)

            return render(request, 'result.html', {
                'candidates': top_candidates,
                'vacancy_title': job_title
            })

        except Exception as e:
            logger.error(f"Error processing ZIP or API request: {str(e)}")
            fs.delete(filename)
            vacancy_ids = request.session.get('vacancy_ids', [])
            vacancies = Vacancy.objects.filter(id__in=vacancy_ids) if vacancy_ids else []
            return render(request, 'analyze.html', {'error': str(e), 'vacancies': vacancies})

    logger.info("Rendering index.html without file")
    vacancy_ids = request.session.get('vacancy_ids', [])
    vacancies = Vacancy.objects.filter(id__in=vacancy_ids) if vacancy_ids else []
    return render(request, 'analyze.html', {'vacancies': vacancies})