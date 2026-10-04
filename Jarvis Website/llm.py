import json
import os
import re
from datetime import date

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

from website.models import Meeting, Project

load_dotenv()

MODEL_OPTIONS = {
    'gemini': {
        'label': 'Gemini',
        'model': os.getenv('GEMINI_MODEL', 'gemini-3.6-flash'),
    },
}


class AssistantAnswer(BaseModel):
    summary: str = ''
    points: list[object] = Field(default_factory=list)
    analysis: str = ''


def available_models():
    return [{'id': key, 'label': value['label']} for key, value in MODEL_OPTIONS.items()]


def build_llm(model_id='gemini'):
    selected = MODEL_OPTIONS.get(model_id, MODEL_OPTIONS['gemini'])
    if model_id == 'gemini':
        return ChatGoogleGenerativeAI(model=selected['model'])
    raise ValueError(f'Unsupported model: {model_id}')


def _normalise(value):
    return re.sub(r'[^a-z0-9]+', ' ', (value or '').casefold()).strip()


def _project_tokens(project_name):
    ignored = {'project', 'the', 'and', 'of', 'for'}
    return {token for token in _normalise(project_name).split() if len(token) >= 3 and token not in ignored}


def _find_project(user, question):
    projects = Project.query.filter_by(company_id=user.company_id).order_by(Project.project_name).all()
    question_text = _normalise(question)
    question_tokens = set(question_text.split())
    exact_matches = [project for project in projects if _normalise(project.project_name) in question_text]
    if exact_matches:
        return projects, exact_matches, False
    partial_matches = [project for project in projects if _project_tokens(project.project_name) & question_tokens]
    return projects, partial_matches, bool(partial_matches)


def _meeting_context(meetings):
    context = []
    sources = []
    for meeting in meetings:
        sections = []
        for section in meeting.sections:
            tasks = []
            for task in section.tasks:
                tasks.append({
                    'title': task.task_title,
                    'description': task.task_description or '',
                    'assigned_to': task.task_assigned_to or '',
                    'due_date': task.task_due_date.isoformat() if task.task_due_date else '',
                    'status': task.task_Status or '',
                    'priority': task.task_priority or '',
                })
            sections.append({'title': section.section_title, 'date': section.section_date.isoformat(), 'tasks': tasks})
        context.append({
            'meeting_id': meeting.meeting_id,
            'title': meeting.meeting_title,
            'date': meeting.meeting_date.isoformat() if meeting.meeting_date else '',
            'revision': meeting.revision_No or 0,
            'description': meeting.meeting_description or '',
            'agenda': meeting.agenda or '',
            'participants': meeting.participants or '',
            'sections': sections,
        })
        sources.append({
            'label': f'{meeting.meeting_title} (Rev {meeting.revision_No or 0})',
            'meeting_url': f'/meeting/{meeting.meeting_id}',
            'pdf_url': f'/meeting/{meeting.meeting_id}/export/pdf',
        })
    return context, sources


def _portfolio_context(projects):
    context = []
    sources = []
    for project in projects:
        meetings = Meeting.query.filter_by(project_id=project.project_id).order_by(Meeting.meeting_date.desc(), Meeting.meeting_id.desc()).limit(10).all()
        project_context, project_sources = _meeting_context(meetings)
        for item in project_context:
            item['project'] = project.project_name
        for source in project_sources:
            source['project'] = project.project_name
        context.extend(project_context)
        sources.extend(project_sources)
    return context, sources


def _is_portfolio_question(question):
    text = _normalise(question)
    return (
        ('pending' in text and ('action' in text or 'item' in text or 'status' in text))
        or 'all project' in text
    )


def _has_explicit_portfolio_scope(question):
    text = _normalise(question)
    return 'all project' in text or 'every project' in text or 'portfolio' in text


def _parse_answer(content):
    if isinstance(content, list):
        content = ''.join(item.get('text', '') for item in content if isinstance(item, dict))
    text = str(content or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        return AssistantAnswer.model_validate(json.loads(text)).model_dump()
    except (ValueError, TypeError, json.JSONDecodeError):
        return {'summary': text, 'points': [], 'analysis': ''}


def ask_agent(user, question, model_id='gemini'):
    question = (question or '').strip()
    if not question:
        return {'needs_project': True, 'message': 'What project would you like assistance with?', 'projects': []}

    projects, matches, partial_match = _find_project(user, question)
    if _is_portfolio_question(question) and not matches and _has_explicit_portfolio_scope(question):
        context, sources = _portfolio_context(projects)
        llm = build_llm(model_id)
        prompt = f'''You are a portfolio project assistant. Answer only from the authorised data below for Company "{user.company.company_name}".
User question: {question}

Return valid JSON only with these keys:
summary: one short answer,
points: a list grouped by project where useful, including every pending item, owner, due date, priority, and status,
analysis: a short practical recommendation. Do not invent facts. Say when records do not contain an answer.

Authorised company project and meeting data:
{json.dumps(context, default=str)}'''
        answer = _parse_answer(llm.invoke(prompt).content)
        answer.update({'project': 'All projects', 'sources': sources, 'generated_on': date.today().isoformat(), 'read_only': True})
        return answer
    if _is_portfolio_question(question) and not matches:
        return {
            'needs_scope': True,
            'message': 'Would you like me to search all projects or one specific project?',
            'projects': [project.project_name for project in projects],
        }
    if len(matches) != 1:
        project_names = [project.project_name for project in projects]
        if not matches:
            return {
                'needs_project': True,
                'message': f'Your account belongs to Company "{user.company.company_name}". Please choose one of your projects before I search.',
                'projects': project_names,
            }
        return {
            'needs_project': True,
            'message': 'Which project would you like assistance with?',
            'projects': [project.project_name for project in matches],
        }

    project = matches[0]
    if partial_match:
        return {
            'needs_project': True,
            'confirmation_required': True,
            'message': f'Did you mean the project "{project.project_name}"?',
            'projects': [project.project_name],
        }
    meetings = Meeting.query.filter_by(project_id=project.project_id).order_by(Meeting.meeting_date.desc(), Meeting.meeting_id.desc()).limit(10).all()
    context, sources = _meeting_context(meetings)
    llm = build_llm(model_id)
    prompt = f'''You are a project assistant. Answer only from the authorised project data below.
Project: {project.project_name}
User question: {question}

Return valid JSON only with these keys:
summary: one short answer,
points: a list of important decisions, updates, action items, owners, dates, or priorities,
analysis: a short practical recommendation. Do not invent facts. Say when the records do not contain an answer.

Authorised meeting data:
{json.dumps(context, default=str)}'''
    answer = _parse_answer(llm.invoke(prompt).content)
    answer.update({
        'project': project.project_name,
        'sources': sources,
        'generated_on': date.today().isoformat(),
        'read_only': True,
    })
    return answer