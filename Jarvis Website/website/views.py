from datetime import datetime, time, timedelta, timezone
from html import escape
from io import BytesIO
from math import ceil
import re
from itertools import zip_longest
from types import SimpleNamespace
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from . import db
from .models import Company, User, Client, Consultant, Contractor, Project, Meeting, CalendarEvent, MeetingRevision, MeetingSection, MeetingTask, Task, AuditLog

views = Blueprint('views', __name__)    


def get_logged_in_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.get(user_id)


def is_admin(user):
    return bool(user and (user.role or '').casefold() == 'admin')


def user_payload(user):
    return {
        'id': user.id,
        'email': user.email,
        'employee_id': user.employee_id or '',
        'company_name': user.company.company_name if user.company else '',
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone_number': user.phone_number or '',
        'role': user.role,
        'is_active': user.is_active,
    }


def project_payload(project):
    current_time = datetime.now().astimezone()
    today = current_time.date()
    due_tasks = []
    latest_meetings = {}
    for meeting in project.meetings:
        meeting_key = meeting.meeting_title.strip().casefold()
        current_latest = latest_meetings.get(meeting_key)
        if current_latest is None or (meeting.revision_No or 0) > (current_latest.revision_No or 0):
            latest_meetings[meeting_key] = meeting
    for meeting in latest_meetings.values():
        for section in meeting.sections:
            for task in section.tasks:
                status = (task.task_Status or '').strip().casefold()
                if status in ('closed', 'fyi'):
                    continue
                due_tasks.append((task.task_due_date, meeting, task))
    meeting_summaries = []
    for meeting in sorted(latest_meetings.values(), key=lambda item: item.meeting_id, reverse=True):
        open_tasks = [
            {
                'id': task.task_id,
                'title': task.task_title,
                'description': task.task_description or '',
                'assigned_to': task.task_assigned_to or '',
                'due_date': task.task_due_date.strftime('%d/%m/%Y') if task.task_due_date else '',
                'status': task.task_Status or '',
            }
            for section in meeting.sections
            for task in section.tasks
            if (task.task_Status or '').casefold() != 'closed'
        ]
        meeting_summaries.append({
            'id': meeting.meeting_id,
            'meeting_id': f'MOM{meeting.meeting_id:04d}',
            'title': meeting.meeting_title,
            'date': meeting.meeting_date.isoformat() if meeting.meeting_date else '',
            'type': meeting.meeting_type or '',
            'location': meeting.location or '',
            'description': meeting.meeting_description or '',
            'agenda': meeting.agenda or '',
            'start_time': meeting.meeting_start_time.strftime('%H:%M') if meeting.meeting_start_time else '',
            'end_time': meeting.meeting_end_time.strftime('%H:%M') if meeting.meeting_end_time else '',
            'chairperson': meeting.chairperson or '',
            'revision': f'Rev_{meeting.revision_No or 0}',
            'tasks': open_tasks,
        })
    due_tasks.sort(key=lambda item: (item[0] is None, item[0] or today))
    project_tasks = []
    for due_date, meeting, task in due_tasks:
        days_until_due = (due_date - today).days if due_date else None
        if days_until_due is not None and days_until_due < 0:
            alert = 'Past due'
            alert_class = 'past-due'
        elif (task.task_priority or '').strip().casefold() == 'high' or (
            days_until_due is not None and days_until_due <= 3
        ):
            alert = 'Urgent'
            alert_class = 'urgent'
        elif days_until_due is not None and days_until_due <= 7:
            alert = 'High'
            alert_class = 'high'
        else:
            continue
        project_tasks.append({
            'title': task.task_title,
            'due_date': due_date.strftime('%d/%m/%Y') if due_date else '',
            'alert': alert,
            'alert_class': alert_class,
            'meeting_id': meeting.meeting_id,
            'task_id': task.task_id,
        })
    calendar_events = []
    for event in sorted(project.calendar_events, key=lambda item: (item.event_date, item.start_time or datetime.min.time())):
        if event.event_date < today:
            continue
        event_time = event.end_time or event.start_time
        if event.event_date == today and event_time and event_time <= current_time.timetz().replace(tzinfo=None):
            continue
        calendar_events.append({
            'id': event.event_id,
            'title': event.event_title,
            'date': event.event_date.isoformat(),
            'start_time': event.start_time.strftime('%H:%M') if event.start_time else '',
            'end_time': event.end_time.strftime('%H:%M') if event.end_time else '',
        })
    return {
        'id': project.project_id,
        'display_id': project_display_id(project),
        'name': project.project_name,
        'company': project.company.company_name if project.company else '',
        'client': project.client.client_name if project.client else '',
        'contractor': ', '.join(
            contractor.contractor_name
            for contractor in (project.contractors or ([project.contractor] if project.contractor else []))
        ),
        'consultant': project.consultant.consultant_name if project.consultant else '',
        'project_site': project.project_site or '',
        'description': project.description or '',
        'purchase_order_date': project.PurchaseOrder_date.isoformat() if project.PurchaseOrder_date else '',
        'issued_date': project.Issued_Date.strftime('%d/%m/%Y') if project.Issued_Date else '',
        'next_task': project_tasks[0] if project_tasks else None,
        'tasks': project_tasks,
        'calendar_events': calendar_events,
        'meetings': meeting_summaries,
        'description': project.description or '',
        'status': (project.Project_Status or 'planning').lower(),
        'purchase_order_date': project.PurchaseOrder_date.isoformat() if project.PurchaseOrder_date else '',
        'updated': project.Issued_Date.strftime('%d %b %Y') if project.Issued_Date else '',
    }


def project_display_id(project):
    issued = project.Issued_Date or datetime.now()
    return f'PRJ{issued.strftime("%m%Y")}-{project.project_id:02d}'


PAST_PROJECT_STATUSES = ('Completed', 'Deferred', 'Cancelled')
PROJECT_DELETE_RETENTION_DAYS = 30


def record_project_audit(user, action, description):
    db.session.add(AuditLog(
        action=action,
        description=description,
        user_id=user.id,
        company_id=user.company_id,
    ))


def permanently_delete_project(project, user, reason):
    project_details = (
        f'Project: {project_display_id(project)}, Name: {project.project_name}, '
        f'Status: {project.Project_Status}. {reason}'
    )
    record_project_audit(user, 'Project permanently deleted', project_details)
    CalendarEvent.query.filter_by(project_id=project.project_id).delete(synchronize_session=False)
    Task.query.filter_by(project_id=project.project_id).delete(synchronize_session=False)
    project.contractors.clear()
    db.session.delete(project)


def purge_expired_projects(company_id, user, now=None):
    now = now or datetime.now().astimezone()
    cutoff = now - timedelta(days=PROJECT_DELETE_RETENTION_DAYS)
    expired_projects = Project.query.filter(
        Project.company_id == company_id,
        Project.deleted_at.isnot(None),
        Project.deleted_at <= cutoff,
    ).all()
    for project in expired_projects:
        permanently_delete_project(
            project,
            user,
            'Removed automatically after the 30-day recovery period.',
        )
    if expired_projects:
        db.session.commit()
    return len(expired_projects)


def purge_expired_meetings(company_id, user, now=None):
    now = now or datetime.now().astimezone()
    cutoff = now - timedelta(days=PROJECT_DELETE_RETENTION_DAYS)
    archived_revisions = MeetingRevision.query.join(Meeting).join(Project).filter(
        Project.company_id == company_id,
        MeetingRevision.deleted_at.isnot(None),
    ).all()
    expired_revisions = [
        revision for revision in archived_revisions
        if revision.deleted_at.astimezone() <= cutoff
    ]
    affected_meetings = {revision.meeting for revision in expired_revisions}
    for revision in expired_revisions:
        meeting_values = (revision.snapshot or {}).get('meeting') or []
        title = meeting_values[0] if meeting_values else revision.meeting.meeting_title
        record_project_audit(
            user,
            'Meeting revision permanently deleted',
            f'Meeting: MOM{revision.meeting_id:04d}, Revision: Rev_{revision.revision_No}, Title: {title}. Removed automatically after the 30-day recovery period.',
        )
        db.session.delete(revision)
    db.session.flush()
    for meeting in affected_meetings:
        if meeting.deleted_at is not None and MeetingRevision.query.filter_by(meeting_id=meeting.meeting_id).count() == 0:
            db.session.delete(meeting)
    if expired_revisions:
        db.session.commit()
    return len(expired_revisions)


def resolve_project_stakeholders(form, company_id, kind, model, id_field, name_field, reg_field, email_field, phone_field, address_field):
    field_names = (id_field, name_field, reg_field, email_field, phone_field, address_field)
    values = [form.getlist(field_name) for field_name in field_names]
    row_count = max((len(items) for items in values), default=1)
    selected = []
    selected_ids = set()
    submitted_registrations = set()
    submitted_names = set()
    for index in range(row_count):
        row = [items[index].strip() if index < len(items) else '' for items in values]
        stakeholder_id, name, registration, email, phone, address = row
        if stakeholder_id:
            if any((name, registration, email, phone, address)) or not stakeholder_id.isdigit():
                raise ValueError(f'Choose either a pre-existing {kind} or register a new one in each section.')
            stakeholder = model.query.filter_by(
                **{model.__mapper__.primary_key[0].name: int(stakeholder_id), 'company_id': company_id}
            ).first()
            if not stakeholder:
                raise ValueError(f'Select a valid pre-existing {kind} from your organisation.')
            stakeholder_pk = getattr(stakeholder, model.__mapper__.primary_key[0].name)
            if stakeholder_pk in selected_ids:
                raise ValueError(f'Select each {kind} only once.')
            selected_ids.add(stakeholder_pk)
            selected.append(stakeholder)
            continue
        if not any((name, registration, email, phone, address)):
            continue
        if not name or not registration:
            raise ValueError(f'Enter both the new {kind} name and registration number.')

        normalized_registration = registration.casefold()
        normalized_name = name.casefold()
        if normalized_registration in submitted_registrations or normalized_name in submitted_names:
            raise ValueError(f'This {kind} is listed more than once. Select it from the pre-existing field.')
        submitted_registrations.add(normalized_registration)
        submitted_names.add(normalized_name)

        duplicate_registration = model.query.filter_by(**{reg_field: registration}).first()
        duplicate_name = model.query.filter(
            model.company_id == company_id,
            db.func.lower(getattr(model, name_field)) == normalized_name,
        ).first()
        if duplicate_registration or duplicate_name:
            if duplicate_name or duplicate_registration.company_id == company_id:
                raise ValueError(f'This {kind} is already registered. Please select it in the pre-existing {kind} field.')
            raise ValueError(f'This registration number is already registered to another organisation.')

        selected.append(model(
            **{
                name_field: name,
                reg_field: registration,
                email_field: email or None,
                phone_field: phone or None,
                address_field: address or None,
                'company_id': company_id,
            }
        ))
    return selected


@views.route('/')
def home():
    user = get_logged_in_user()
    if not user:
        #flash('Please log in to view your dashboard.', category='error')
        return redirect(url_for('auth.login'))

    if not session.get('user_id'):
        session.pop('user_id', None)
        #flash('Please log in to view your dashboard.', category='error')
        return redirect(url_for('auth.login'))

    purge_expired_projects(user.company_id, user)
    current_time = datetime.now().astimezone()
    hour = current_time.hour
    greeting = 'Good morning' if hour < 12 else 'Good afternoon' if hour < 18 else 'Good evening'
    offset_minutes = int((current_time.utcoffset() or timezone.utc.utcoffset(current_time)).total_seconds() // 60)
    offset_sign = '+' if offset_minutes >= 0 else '-'
    offset_minutes = abs(offset_minutes)
    timezone_label = f'UTC{offset_sign}{offset_minutes // 60:02d}:{offset_minutes % 60:02d}'
    return render_template(
        'home.html',
        current_date=current_time.strftime('%A, %d %B %Y, %H:%M:%S'),
        timezone=timezone_label,
        greeting=greeting,
        first_name=user.first_name,
        user_role=user.role,
        company_email=user.company.company_email if user.company else '',
    )


@views.route('/api/organisation', methods=['GET', 'PUT'])
def organisation_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    company = user.company
    if request.method == 'PUT':
        if not is_admin(user):
            return jsonify({'error': 'admin_required'}), 403
        data = request.get_json(silent=True) or request.form
        changed_fields = []
        company_values = {
            'company_name': (data.get('company_name') or company.company_name).strip(),
            'company_reg_no': (data.get('company_reg_no') or company.company_reg_no).strip(),
            'company_tax_no': (data.get('company_tax_no', company.company_tax_no) or '').strip() or None,
            'company_email': (data.get('company_email', company.company_email) or '').strip() or None,
            'company_phone_number': (data.get('company_phone_number', company.company_phone_number) or '').strip() or None,
            'address': (data.get('address', company.address) or '').strip() or None,
            'website': (data.get('website', company.website) or '').strip() or None,
            'description': (data.get('description', company.description) or '').strip() or None,
        }
        for field, value in company_values.items():
            if getattr(company, field) != value:
                changed_fields.append(field)
        for field, value in company_values.items():
            setattr(company, field, value)
        company.date_Issued = datetime.now().astimezone()
        db.session.add(AuditLog(
            action='Company details updated',
            description=(
                f'Company {company.company_name} updated by {user.first_name} {user.last_name} '
                f'({user.email}). Fields: {", ".join(changed_fields) if changed_fields else "saved without field changes"}.'
            ),
            user_id=user.id,
            company_id=user.company_id,
        ))
        db.session.commit()
    members = sorted(company.users, key=lambda item: (not item.is_active, item.first_name.casefold(), item.last_name.casefold()))
    if not is_admin(user):
        members = [member for member in members if member.is_active]
    return jsonify({
        'company': {
            'company_name': company.company_name,
            'company_reg_no': company.company_reg_no,
            'company_tax_no': company.company_tax_no or '',
            'company_email': company.company_email or '',
            'company_phone_number': company.company_phone_number or '',
            'address': company.address or '',
            'website': company.website or '',
            'description': company.description or '',
            'date_issued': company.date_Issued.strftime('%d %b %Y, %H:%M') if company.date_Issued else '',
        },
        'members': [user_payload(member) for member in members],
        'current_user': user_payload(user),
        'is_admin': is_admin(user),
    })


@views.route('/api/organisation/company-password', methods=['PUT'])
def update_company_password():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    if not is_admin(user):
        return jsonify({'error': 'admin_required'}), 403
    data = request.get_json(silent=True) or {}
    company_password = data.get('company_password') or ''
    if len(company_password) < 7:
        return jsonify({'error': 'Company password must be at least 7 characters.'}), 400

    company = user.company
    company.company_password_hash = generate_password_hash(company_password)
    company.date_Issued = datetime.now().astimezone()
    db.session.add(AuditLog(
        action='Company Password Changed',
        description=f'Company password changed by {user.first_name} {user.last_name} ({user.email}).',
        user_id=user.id,
        company_id=user.company_id,
    ))
    db.session.commit()
    return jsonify({'success': True})


@views.route('/api/organisation/members', methods=['POST'])
def add_organisation_member():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    if not is_admin(user):
        return jsonify({'error': 'admin_required'}), 403
    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()
    temporary_password = data.get('temporary_password') or ''
    role = str(data.get('role') or 'Member').strip().casefold()
    if not email or len(temporary_password) < 7:
        return jsonify({'error': 'Email and a temporary password of at least 7 characters are required.'}), 400
    if role not in {'admin', 'member'}:
        return jsonify({'error': 'Role must be Admin or Member.'}), 400
    existing_member = User.query.filter_by(email=email).first()
    if existing_member:
        if existing_member.company_id != user.company_id:
            return jsonify({'error': 'That email address is already registered to another company.'}), 400
        if existing_member.is_active:
            return jsonify({'error': 'That email address is already added as an active member on your team.'}), 400
        existing_member.first_name = (data.get('first_name') or '').strip() or existing_member.first_name or 'New'
        existing_member.last_name = (data.get('last_name') or '').strip()
        existing_member.role = 'Admin' if role == 'admin' else 'Member'
        existing_member.password_hash = generate_password_hash(temporary_password)
        existing_member.is_active = True
        db.session.add(AuditLog(
            action='Team Member Reactivated',
            description=f'User: {existing_member.first_name} {existing_member.last_name} ({existing_member.email}) reactivated by {user.first_name} {user.last_name} ({user.email}).',
            user_id=user.id,
            company_id=user.company_id,
        ))
        db.session.commit()
        payload = user_payload(existing_member)
        payload['reactivated'] = True
        return jsonify(payload), 200
    member = User(
        email=email,
        first_name=(data.get('first_name') or '').strip() or 'New',
        last_name=(data.get('last_name') or '').strip() or 'Member',
        role='Admin' if role == 'admin' else 'Member',
        password_hash=generate_password_hash(temporary_password),
        company_id=user.company_id,
        is_active=True,
    )
    db.session.add(member)
    db.session.commit()
    return jsonify(user_payload(member)), 201


@views.route('/api/organisation/members/<int:member_id>', methods=['PUT'])
def update_organisation_member(member_id):
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    if not is_admin(user):
        return jsonify({'error': 'admin_required'}), 403
    member = User.query.filter_by(id=member_id, company_id=user.company_id).first()
    if not member:
        return jsonify({'error': 'Member not found.'}), 404
    data = request.get_json(silent=True) or request.form
    requested_role = data.get('role')
    if requested_role is not None:
        normalized_role = str(requested_role).strip().casefold()
        if normalized_role not in {'admin', 'member'}:
            return jsonify({'error': 'Role must be Admin or Member.'}), 400
        role = 'Admin' if normalized_role == 'admin' else 'Member'
        if member.id == user.id and role != member.role:
            return jsonify({'error': 'You cannot change your own role.'}), 400
        if role != member.role:
            old_role = member.role
            member.role = role
            db.session.add(AuditLog(
                action='Team Member Role Changed',
                description=(
                    f'User: {member.first_name} {member.last_name} ({member.email}) role changed '
                    f'from {old_role} to {role} by {user.first_name} {user.last_name} ({user.email}).'
                ),
                user_id=user.id,
                company_id=user.company_id,
            ))
    if 'is_active' in data:
        requested_active = data.get('is_active') in (True, 'true', '1', 1, 'on')
        if member.id == user.id and not requested_active:
            return jsonify({'error': 'You cannot deactivate your own account.'}), 400
        member.is_active = requested_active
    new_password = data.get('password') or ''
    if new_password:
        if len(new_password) < 7:
            return jsonify({'error': 'Password must be at least 7 characters.'}), 400
        member.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify(user_payload(member))


@views.route('/api/account', methods=['GET', 'PUT'])
def account_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    if request.method == 'PUT':
        data = request.get_json(silent=True) or request.form
        user.first_name = (data.get('first_name') or user.first_name).strip()
        user.last_name = (data.get('last_name') or user.last_name).strip()
        user.employee_id = (data.get('employee_id') or '').strip() or None
        user.phone_number = (data.get('phone_number') or '').strip() or None
        new_password = data.get('password') or ''
        if new_password:
            if len(new_password) < 7:
                return jsonify({'error': 'Password must be at least 7 characters.'}), 400
            user.password_hash = generate_password_hash(new_password)
        db.session.commit()
    return jsonify(user_payload(user))


STAKEHOLDER_MODELS = {
    'clients': (Client, 'client_id', 'client_name', 'client_reg_no', 'client_address', 'client_email', 'client_phone_number'),
    'contractors': (Contractor, 'contractor_id', 'contractor_name', 'contractor_reg_no', 'contractor_address', 'contractor_email', 'contractor_phone_number'),
    'consultants': (Consultant, 'consultant_id', 'consultant_name', 'consultant_reg_no', 'consultant_address', 'consultant_email', 'consultant_phone_number'),
}


def stakeholder_payload(stakeholder, kind):
    model, id_field, name_field, reg_field, address_field, email_field, phone_field = STAKEHOLDER_MODELS[kind]
    return {
        'id': getattr(stakeholder, id_field),
        'name': getattr(stakeholder, name_field) or '',
        'reg_no': getattr(stakeholder, reg_field) or '',
        'address': getattr(stakeholder, address_field) or '',
        'email': getattr(stakeholder, email_field) or '',
        'phone': getattr(stakeholder, phone_field) or '',
    }


@views.route('/api/stakeholders')
def stakeholders_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    if not is_admin(user):
        return jsonify({'error': 'admin_required'}), 403
    return jsonify({
        kind: [
            stakeholder_payload(item, kind)
            for item in model.query.filter_by(company_id=user.company_id).order_by(getattr(model, name_field)).all()
        ]
        for kind, (model, id_field, name_field, reg_field, address_field, email_field, phone_field) in STAKEHOLDER_MODELS.items()
    })


@views.route('/api/stakeholders/<kind>', methods=['POST'])
def add_stakeholder(kind):
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    if not is_admin(user):
        return jsonify({'error': 'admin_required'}), 403
    config = STAKEHOLDER_MODELS.get(kind)
    if not config:
        return jsonify({'error': 'Stakeholder type not found.'}), 404
    model, id_field, name_field, reg_field, address_field, email_field, phone_field = config
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    reg_no = (data.get('reg_no') or '').strip()
    if not name or not reg_no:
        return jsonify({'error': 'Name and registration number are required.'}), 400
    if model.query.filter_by(**{reg_field: reg_no}).first():
        return jsonify({'error': 'That registration number already exists.'}), 400
    stakeholder = model(
        **{name_field: name, reg_field: reg_no, address_field: (data.get('address') or '').strip() or None,
           email_field: (data.get('email') or '').strip() or None, phone_field: (data.get('phone') or '').strip() or None,
           'company_id': user.company_id},
    )
    db.session.add(stakeholder)
    db.session.add(AuditLog(
        action=f'{kind[:-1].title()} created',
        description=f'{kind[:-1].title()} {name} ({reg_no}) created by {user.first_name} {user.last_name} ({user.email}).',
        user_id=user.id,
        company_id=user.company_id,
    ))
    db.session.commit()
    return jsonify(stakeholder_payload(stakeholder, kind)), 201


@views.route('/api/stakeholders/<kind>/<int:stakeholder_id>', methods=['PUT'])
def update_stakeholder(kind, stakeholder_id):
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    if not is_admin(user):
        return jsonify({'error': 'admin_required'}), 403
    config = STAKEHOLDER_MODELS.get(kind)
    if not config:
        return jsonify({'error': 'Stakeholder type not found.'}), 404
    model, id_field, name_field, reg_field, address_field, email_field, phone_field = config
    stakeholder = model.query.filter_by(**{id_field: stakeholder_id, 'company_id': user.company_id}).first()
    if not stakeholder:
        return jsonify({'error': 'Stakeholder not found.'}), 404
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    reg_no = (data.get('reg_no') or '').strip()
    if not name or not reg_no:
        return jsonify({'error': 'Name and registration number are required.'}), 400
    setattr(stakeholder, name_field, name)
    setattr(stakeholder, reg_field, reg_no)
    setattr(stakeholder, address_field, (data.get('address') or '').strip() or None)
    setattr(stakeholder, email_field, (data.get('email') or '').strip() or None)
    setattr(stakeholder, phone_field, (data.get('phone') or '').strip() or None)
    db.session.add(AuditLog(
        action=f'{kind[:-1].title()} details updated',
        description=f'{kind[:-1].title()} {name} ({reg_no}) updated by {user.first_name} {user.last_name} ({user.email}).',
        user_id=user.id,
        company_id=user.company_id,
    ))
    db.session.commit()
    return jsonify(stakeholder_payload(stakeholder, kind))


@views.route('/api/projects', methods=['GET', 'POST'])
def projects_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401

    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        project_name = (data.get('name') or data.get('project_name') or '').strip()
        if not project_name:
            return jsonify({'error': 'Project name is required.'}), 400

        project = Project(
            project_name=project_name,
            project_site=(data.get('project_site') or '').strip() or None,
            description=(data.get('description') or '').strip(),
            Project_Status=(data.get('status') or 'planning').strip(),
            company_id=user.company_id,
        )
        db.session.add(project)
        db.session.commit()
        return jsonify(project_payload(project)), 201

    purge_expired_projects(user.company_id, user)
    active_projects = Project.query.filter(
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Project.Project_Status.notin_(PAST_PROJECT_STATUSES),
    ).order_by(Project.project_id.desc()).all()
    return jsonify([project_payload(project) for project in active_projects])


@views.route('/api/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401

    project = Project.query.filter_by(project_id=project_id, company_id=user.company_id).first()
    if not project or project.deleted_at is not None:
        return jsonify({'error': 'Project not found.'}), 404

    data = request.get_json(silent=True) or request.form
    old_status = project.Project_Status
    project.project_name = (data.get('name') or project.project_name).strip()
    project.project_site = (data.get('project_site') or '').strip() or None
    project.description = (data.get('description') or '').strip()
    project.Project_Status = (data.get('status') or project.Project_Status or 'planning').strip()
    if project.Project_Status in PAST_PROJECT_STATUSES and old_status not in PAST_PROJECT_STATUSES:
        record_project_audit(
            user,
            'Project moved to Past projects archive',
            f'Project: {project_display_id(project)}, Name: {project.project_name}, Status: {project.Project_Status}.',
        )
    db.session.commit()
    return jsonify(project_payload(project))


@views.route('/project/new', methods=['GET', 'POST'])
def new_project():
    if not get_logged_in_user():
        flash('Please log in to create a project.', category='error')
        return redirect(url_for('auth.login'))

    current_user = get_logged_in_user()
    company = current_user.company

    def get_contractor_form_rows(form_data=None):
        field_names = (
            'existing_contractor_id',
            'contractor_name',
            'contractor_reg_no',
            'contractor_email',
            'contractor_phone_number',
            'contractor_address',
        )
        if not form_data:
            rows = [{}]
        else:
            values = [form_data.getlist(name) for name in field_names]
            row_count = max((len(items) for items in values), default=1)
            rows = [
                {name: items[index] if index < len(items) else '' for name, items in zip(field_names, values)}
                for index in range(row_count)
            ]

        for row in rows:
            selected_contractor = None
            selected_id = row.get('existing_contractor_id', '')
            if selected_id.isdigit():
                selected_contractor = Contractor.query.filter_by(
                    contractor_id=int(selected_id),
                    company_id=company.company_id,
                ).first()
            row.update({
                'existing_contractor_id': str(selected_contractor.contractor_id) if selected_contractor else '',
                'existing_contractor_name': selected_contractor.contractor_name if selected_contractor else '',
                'existing_contractor_reg_no': selected_contractor.contractor_reg_no if selected_contractor else '',
                'existing_contractor_email': selected_contractor.contractor_email or '' if selected_contractor else '',
                'existing_contractor_phone': selected_contractor.contractor_phone_number or '' if selected_contractor else '',
                'existing_contractor_address': selected_contractor.contractor_address or '' if selected_contractor else '',
                'name': row.get('contractor_name', ''),
                'reg_no': row.get('contractor_reg_no', ''),
                'email': row.get('contractor_email', ''),
                'phone': row.get('contractor_phone_number', ''),
                'address': row.get('contractor_address', ''),
            })
        return rows

    def render_project_form(form_data=None):
        selected_consultant = None
        selected_consultant_id = form_data.get('existing_consultant_id', '').strip() if form_data else ''
        if selected_consultant_id.isdigit():
            selected_consultant = Consultant.query.filter_by(
                consultant_id=int(selected_consultant_id),
                company_id=company.company_id,
            ).first()
        return render_template(
            'project.html',
            project=None,
            company=company,
            current_user=current_user,
            clients=Client.query.filter_by(company_id=company.company_id).order_by(Client.client_name).all(),
            contractors=Contractor.query.filter_by(company_id=company.company_id).order_by(Contractor.contractor_name).all(),
            consultants=Consultant.query.filter_by(company_id=company.company_id).order_by(Consultant.consultant_name).all(),
            selected_consultant=selected_consultant,
            form_data=form_data,
            contractor_rows=get_contractor_form_rows(form_data),
        )

    if request.method == 'POST':
        form = request.form
        if not form.get('project_name', '').strip():
            flash('Project name is required.', category='error')
            return render_project_form(form)

        existing_client_id = form.get('existing_client_id', '').strip()
        client_name = form.get('client_name', '').strip()
        client_reg_no = form.get('client_reg_no', '').strip()
        client_email = form.get('client_email', '').strip()
        client_phone_number = form.get('client_phone_number', '').strip()
        client_address = form.get('client_address', '').strip()
        new_client_details = (client_name, client_reg_no, client_email, client_phone_number, client_address)

        if existing_client_id:
            if any(new_client_details):
                flash('Choose either a pre-existing client or register a new client, not both.', category='error')
                return render_project_form(form)
            if not existing_client_id.isdigit():
                flash('Select a valid pre-existing client from your organisation.', category='error')
                return render_project_form(form)
            client = Client.query.filter_by(
                client_id=int(existing_client_id),
                company_id=company.company_id,
            ).first()
            if client is None:
                flash('Select a valid pre-existing client from your organisation.', category='error')
                return render_project_form(form)
        elif any(new_client_details):
            if not client_name or not client_reg_no:
                flash('Enter both the new client name and registration number.', category='error')
                return render_project_form(form)
            duplicate_client = Client.query.filter_by(client_reg_no=client_reg_no).first()
            duplicate_name = Client.query.filter(
                Client.company_id == company.company_id,
                db.func.lower(Client.client_name) == client_name.lower(),
            ).first()
            if duplicate_client or duplicate_name:
                if duplicate_name or duplicate_client.company_id == company.company_id:
                    flash(
                        'A client with this name or registration number is already registered. Please select it in the pre-existing client field.',
                        category='error',
                    )
                else:
                    flash(
                        'This registration number is already registered to another organisation.',
                        category='error',
                    )
                return render_project_form(form)
            client = Client(
                client_name=client_name,
                client_reg_no=client_reg_no,
                client_email=client_email or None,
                client_phone_number=client_phone_number or None,
                client_address=client_address or None,
                company_id=company.company_id,
            )
            db.session.add(client)
        else:
            client = None

        contractor_ids = form.getlist('existing_contractor_id')
        contractor_names = form.getlist('contractor_name')
        contractor_regs = form.getlist('contractor_reg_no')
        contractor_emails = form.getlist('contractor_email')
        contractor_phones = form.getlist('contractor_phone_number')
        contractor_addresses = form.getlist('contractor_address')
        contractor_rows = []
        row_count = max(map(len, (
            contractor_ids,
            contractor_names,
            contractor_regs,
            contractor_emails,
            contractor_phones,
            contractor_addresses,
        )), default=0)
        selected_contractor_ids = set()
        for index in range(row_count):
            contractor_id = contractor_ids[index].strip() if index < len(contractor_ids) else ''
            name = contractor_names[index].strip() if index < len(contractor_names) else ''
            registration = contractor_regs[index].strip() if index < len(contractor_regs) else ''
            email = contractor_emails[index].strip() if index < len(contractor_emails) else ''
            phone = contractor_phones[index].strip() if index < len(contractor_phones) else ''
            address = contractor_addresses[index].strip() if index < len(contractor_addresses) else ''
            new_details = (name, registration, email, phone, address)

            if contractor_id:
                if any(new_details) or not contractor_id.isdigit():
                    flash('Choose either a pre-existing contractor/vendor or register a new one in each section.', category='error')
                    return render_project_form(form)
                selected = Contractor.query.filter_by(
                    contractor_id=int(contractor_id),
                    company_id=company.company_id,
                ).first()
                if selected is None:
                    flash('Select a valid pre-existing contractor/vendor from your organisation.', category='error')
                    return render_project_form(form)
                if selected.contractor_id in selected_contractor_ids:
                    flash('Select each contractor/vendor only once.', category='error')
                    return render_project_form(form)
                selected_contractor_ids.add(selected.contractor_id)
                contractor_rows.append(selected)
            elif any(new_details):
                if not name or not registration:
                    flash('Enter both the new contractor/vendor name and registration number.', category='error')
                    return render_project_form(form)
                duplicate_registration = Contractor.query.filter_by(contractor_reg_no=registration).first()
                duplicate_name = Contractor.query.filter(
                    Contractor.company_id == company.company_id,
                    db.func.lower(Contractor.contractor_name) == name.lower(),
                ).first()
                if duplicate_registration or duplicate_name:
                    if duplicate_name or duplicate_registration.company_id == company.company_id:
                        flash(
                            'This contractor/vendor is already registered. Please select it in the pre-existing contractor/vendor field.',
                            category='error',
                        )
                    else:
                        flash('This registration number is already registered to another organisation.', category='error')
                    return render_project_form(form)
                contractor = Contractor(
                    contractor_name=name,
                    contractor_reg_no=registration,
                    contractor_email=email or None,
                    contractor_phone_number=phone or None,
                    contractor_address=address or None,
                    company_id=company.company_id,
                )
                db.session.add(contractor)
                contractor_rows.append(contractor)

        if not contractor_rows:
            flash('Add at least one sub contractor/vendor using either the pre-existing or new section.', category='error')
            return render_project_form(form)

        existing_consultant_id = form.get('existing_consultant_id', '').strip()
        consultant_reg_no = form.get('consultant_reg_no', '').strip()
        if existing_consultant_id:
            consultant = None
            if existing_consultant_id.isdigit():
                consultant = Consultant.query.filter_by(
                    consultant_id=int(existing_consultant_id),
                    company_id=company.company_id,
                ).first()
            if consultant is None:
                flash('Select a valid pre-existing consultant from your organisation.', category='error')
                return render_project_form(form)
        elif consultant_reg_no:
            duplicate_consultant = Consultant.query.filter_by(consultant_reg_no=consultant_reg_no).first()
            if duplicate_consultant:
                if duplicate_consultant.company_id == company.company_id:
                    flash(
                        'This consultant is already registered. Please select it in the pre-existing consultant field.',
                        category='error',
                    )
                else:
                    flash('This registration number is already registered to another organisation.', category='error')
                return render_project_form(form)
            consultant = Consultant(
                consultant_reg_no=consultant_reg_no,
                consultant_name=form.get('consultant_name', '').strip(),
                consultant_email=form.get('consultant_email', '').strip() or None,
                consultant_phone_number=form.get('consultant_phone_number', '').strip() or None,
                consultant_address=form.get('consultant_address', '').strip() or None,
                company_id=company.company_id,
            )
            db.session.add(consultant)
        else:
            consultant = None

        consultant_regs = form.getlist('consultant_reg_no')
        consultant_names = form.getlist('consultant_name')
        consultant_emails = form.getlist('consultant_email')
        consultant_phones = form.getlist('consultant_phone_number')
        consultant_addresses = form.getlist('consultant_address')
        for index, registration in enumerate(consultant_regs[1:], start=1):
            registration = registration.strip()
            if not registration or Consultant.query.filter_by(consultant_reg_no=registration, company_id=company.company_id).first():
                continue
            db.session.add(Consultant(
                consultant_reg_no=registration,
                consultant_name=consultant_names[index].strip() if index < len(consultant_names) else '',
                consultant_email=consultant_emails[index].strip() if index < len(consultant_emails) else None,
                consultant_phone_number=consultant_phones[index].strip() if index < len(consultant_phones) else None,
                consultant_address=consultant_addresses[index].strip() if index < len(consultant_addresses) else None,
                company_id=company.company_id,
            ))

        project = Project(
            project_name=form.get('project_name', '').strip(),
            project_site=form.get('project_site', '').strip() or None,
            description=form.get('project_description', '').strip() or None,
            PurchaseOrder_date=datetime.strptime(form.get('purchase_order_date'), '%Y-%m-%d').date() if form.get('purchase_order_date') else None,
            Project_Status=form.get('project_status', 'Active'),
            company_id=company.company_id,
            client=client,
            contractor=contractor_rows[0],
            contractors=contractor_rows,
            consultant=consultant,
        )
        db.session.add(project)
        db.session.flush()
        db.session.add(AuditLog(
            action=f'Project {project.project_name}-{project_display_id(project)} Created',
            description=(
                f'Project: {project.project_name}, ID: {project_display_id(project)}, '
                f'Created by: {current_user.first_name} {current_user.last_name}'.strip() +
                f', User ID: {current_user.id}, Email: {current_user.email}, Role: {current_user.role}, '
                f'Company: {company.company_name}, Company Reg No: {company.company_reg_no}, '
                f'Status: {project.Project_Status}, Purchase Order Date: {project.PurchaseOrder_date}, '
                f'Project Site: {project.project_site or ""}, Description: {project.description or ""}, '
                f'Client: {client.client_name if client else ""}, Contractors: {", ".join(item.contractor_name for item in contractor_rows)}, '
                f'Consultant: {consultant.consultant_name if consultant else ""}'
            ),
            user_id=current_user.id,
            company_id=company.company_id,
        ))
        db.session.commit()
        flash('Project created successfully.', category='success')
        return redirect(url_for('views.home', view='projects', project_id=project.project_id))

    return render_project_form()


@views.route('/project/archive')
def project_archive():
    user = get_logged_in_user()
    if not user:
        flash('Please log in to view the project archive.', category='error')
        return redirect(url_for('auth.login'))

    purge_expired_projects(user.company_id, user)
    archived_projects = Project.query.filter(
        Project.company_id == user.company_id,
        Project.deleted_at.isnot(None),
    ).order_by(Project.deleted_at.desc()).all()
    now = datetime.now().astimezone()
    recently_deleted = [
        (
            project,
            max(0, ceil(
                (project.deleted_at + timedelta(days=PROJECT_DELETE_RETENTION_DAYS) - now).total_seconds()
                / 86400
            )),
        )
        for project in archived_projects
    ]
    past_projects = Project.query.filter(
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Project.Project_Status.in_(PAST_PROJECT_STATUSES),
    ).order_by(Project.project_name).all()
    return render_template(
        'project_archive.html',
        recently_deleted=recently_deleted,
        past_projects=past_projects,
        project_display_id=project_display_id,
    )


@views.route('/meeting/archive')
def meeting_archive():
    user = get_logged_in_user()
    if not user:
        flash('Please log in to view the meeting archive.', category='error')
        return redirect(url_for('auth.login'))

    purge_expired_meetings(user.company_id, user)
    legacy_archived_meetings = Meeting.query.join(Project).filter(
        Project.company_id == user.company_id,
        Meeting.deleted_at.isnot(None),
    ).all()
    for meeting in legacy_archived_meetings:
        for revision in meeting.revision_history:
            if revision.deleted_at is None:
                revision.deleted_at = meeting.deleted_at
                revision.deleted_with_project = meeting.deleted_with_project
        current_order = meeting.revision_order if meeting.revision_order is not None else (meeting.revision_No or 0)
        if not any(meeting_revision_order(revision) == current_order for revision in meeting.revision_history):
            store_current_meeting_revision(
                meeting,
                deleted_at=meeting.deleted_at,
                deleted_with_project=meeting.deleted_with_project,
            )
    if legacy_archived_meetings:
        db.session.commit()

    archived_revisions = MeetingRevision.query.join(Meeting).join(Project).filter(
        Project.company_id == user.company_id,
        MeetingRevision.deleted_at.isnot(None),
    ).order_by(MeetingRevision.deleted_at.desc(), MeetingRevision.revision_id.desc()).all()
    now = datetime.now().astimezone()
    recently_deleted = [
        (
            revision_archive_entry(revision.meeting, revision),
            max(0, ceil(
                (revision.deleted_at.astimezone() + timedelta(days=PROJECT_DELETE_RETENTION_DAYS) - now).total_seconds()
                / 86400
            )),
        )
        for revision in archived_revisions
    ]
    past_meetings = Meeting.query.join(Project).filter(
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Project.Project_Status.in_(PAST_PROJECT_STATUSES),
        Meeting.deleted_at.is_(None),
    ).order_by(Project.project_name, Meeting.meeting_date.desc(), Meeting.meeting_id.desc()).all()
    return render_template(
        'meeting_archive.html',
        recently_deleted=recently_deleted,
        past_meetings=past_meetings,
        project_display_id=project_display_id,
    )


@views.route('/meeting/<int:meeting_id>/archive', methods=['POST'])
def archive_meeting(meeting_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to archive a meeting.', category='error')
        return redirect(url_for('auth.login'))
    meeting = Meeting.query.join(Project).filter(
        Meeting.meeting_id == meeting_id,
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Meeting.deleted_at.is_(None),
    ).first_or_404()
    archived_revision_no = archive_active_meeting_revision(
        meeting,
        meeting.revision_order if meeting.revision_order is not None else (meeting.revision_No or 0),
        user,
    )
    if archived_revision_no is None:
        return redirect(url_for('views.home', view='meetings'))
    db.session.commit()
    flash(f'Rev_{archived_revision_no} was moved to Recently deleted.', category='success')
    return redirect(url_for('views.home', view='meetings'))


@views.route('/meeting/<int:meeting_id>/revision/<int:revision_order>/archive', methods=['POST'])
def archive_meeting_revision(meeting_id, revision_order):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to archive a meeting revision.', category='error')
        return redirect(url_for('auth.login'))
    meeting = Meeting.query.join(Project).filter(
        Meeting.meeting_id == meeting_id,
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Meeting.deleted_at.is_(None),
    ).first_or_404()
    archived_revision_no = archive_active_meeting_revision(meeting, revision_order, user)
    if archived_revision_no is None:
        return redirect(url_for('views.home', view='meetings'))
    db.session.commit()
    flash(f'Rev_{archived_revision_no} was moved to Recently deleted.', category='success')
    return redirect(url_for('views.home', view='meetings'))


@views.route('/meeting/<int:meeting_id>/revision/<int:revision_id>/restore', methods=['POST'])
def restore_meeting_revision(meeting_id, revision_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to restore a meeting revision.', category='error')
        return redirect(url_for('auth.login'))
    purge_expired_meetings(user.company_id, user)
    revision = MeetingRevision.query.join(Meeting).join(Project).filter(
        Meeting.meeting_id == meeting_id,
        MeetingRevision.revision_id == revision_id,
        MeetingRevision.deleted_at.isnot(None),
        Project.company_id == user.company_id,
    ).first_or_404()
    meeting = revision.meeting
    if meeting.project.deleted_at is not None:
        flash('Restore the project first to recover revisions archived with it.', category='error')
        return redirect(url_for('views.meeting_archive'))
    archived_number = revision.revision_No
    revision.deleted_at = None
    revision.deleted_with_project = False
    if meeting.deleted_at is not None:
        meeting.deleted_at = None
        meeting.deleted_with_project = False
        if not promote_latest_active_revision(meeting):
            apply_meeting_revision_snapshot(meeting, revision.snapshot, 0, meeting_revision_order(revision))
            db.session.delete(revision)
    elif meeting_revision_order(revision) > (meeting.revision_order or meeting.revision_No or 0):
        store_current_meeting_revision(meeting)
        apply_meeting_revision_snapshot(meeting, revision.snapshot, meeting.revision_No or 0, meeting_revision_order(revision))
        db.session.delete(revision)
    normalize_meeting_revision_numbers(meeting)
    record_project_audit(
        user,
        'Meeting revision restored from recently deleted archive',
        f'Meeting: MOM{meeting.meeting_id:04d}, Revision: Rev_{archived_number}, Title: {meeting.meeting_title}.',
    )
    db.session.commit()
    flash(f'Rev_{archived_number} was restored and the active revisions were renumbered.', category='success')
    return redirect(url_for('views.meeting_archive'))


@views.route('/meeting/<int:meeting_id>/revision/<int:revision_id>/delete-permanently', methods=['POST'])
def delete_meeting_revision_permanently(meeting_id, revision_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to permanently delete a meeting revision.', category='error')
        return redirect(url_for('auth.login'))
    purge_expired_meetings(user.company_id, user)
    revision = MeetingRevision.query.join(Meeting).join(Project).filter(
        Meeting.meeting_id == meeting_id,
        MeetingRevision.revision_id == revision_id,
        MeetingRevision.deleted_at.isnot(None),
        Project.company_id == user.company_id,
    ).first_or_404()
    meeting = revision.meeting
    values = (revision.snapshot or {}).get('meeting') or []
    title = values[0] if values else meeting.meeting_title
    revision_number = revision.revision_No
    record_project_audit(
        user,
        'Meeting revision permanently deleted',
        f'Meeting: MOM{meeting.meeting_id:04d}, Revision: Rev_{revision_number}, Title: {title}. Permanently deleted by user from the meeting archive.',
    )
    db.session.delete(revision)
    db.session.flush()
    if meeting.deleted_at is not None and MeetingRevision.query.filter_by(meeting_id=meeting.meeting_id).count() == 0:
        db.session.delete(meeting)
    db.session.commit()
    flash(f'Rev_{revision_number} was permanently deleted.', category='success')
    return redirect(url_for('views.meeting_archive'))


@views.route('/meeting/<int:meeting_id>/restore', methods=['POST'])
def restore_meeting(meeting_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to restore a meeting.', category='error')
        return redirect(url_for('auth.login'))
    purge_expired_meetings(user.company_id, user)
    meeting = Meeting.query.join(Project).filter(
        Meeting.meeting_id == meeting_id,
        Project.company_id == user.company_id,
        Meeting.deleted_at.isnot(None),
    ).first_or_404()
    if meeting.project.deleted_at is not None:
        flash('Restore the project first to recover meetings archived with it.', category='error')
        return redirect(url_for('views.meeting_archive'))
    if not any(revision.deleted_at is None for revision in meeting.revision_history):
        flash('No revisions are available to restore.', category='error')
        return redirect(url_for('views.meeting_archive'))
    meeting.deleted_at = None
    meeting.deleted_with_project = False
    promote_latest_active_revision(meeting)
    record_project_audit(
        user,
        'Meeting restored from recently deleted archive',
        f'Meeting: MOM{meeting.meeting_id:04d}, Title: {meeting.meeting_title}.',
    )
    db.session.commit()
    flash(f'"{meeting.meeting_title}" was restored.', category='success')
    return redirect(url_for('views.meeting_archive'))


@views.route('/meeting/<int:meeting_id>/delete-permanently', methods=['POST'])
def delete_meeting_permanently(meeting_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to permanently delete a meeting.', category='error')
        return redirect(url_for('auth.login'))
    purge_expired_meetings(user.company_id, user)
    meeting = Meeting.query.join(Project).filter(
        Meeting.meeting_id == meeting_id,
        Project.company_id == user.company_id,
        Meeting.deleted_at.isnot(None),
    ).first_or_404()
    for revision in meeting.revision_history:
        db.session.delete(revision)
    title = meeting.meeting_title
    db.session.delete(meeting)
    db.session.commit()
    flash(f'"{title}" and all archived revisions were permanently deleted.', category='success')
    return redirect(url_for('views.meeting_archive'))


@views.route('/project/<int:project_id>/archive', methods=['POST'])
def archive_project(project_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to archive a project.', category='error')
        return redirect(url_for('auth.login'))
    project = Project.query.filter_by(
        project_id=project_id,
        company_id=user.company_id,
        deleted_at=None,
    ).first_or_404()
    now = datetime.now().astimezone()
    project.deleted_at = now
    for meeting in Meeting.query.filter_by(project_id=project.project_id, deleted_at=None).all():
        for revision in meeting.revision_history:
            if revision.deleted_at is None:
                revision.deleted_at = now
                revision.deleted_with_project = True
        store_current_meeting_revision(
            meeting,
            deleted_at=now,
            deleted_with_project=True,
        )
        meeting.deleted_at = now
        meeting.deleted_with_project = True
    record_project_audit(
        user,
        'Project moved to Recently deleted archive',
        (
            f'Project: {project_display_id(project)}, Name: {project.project_name}, '
            f'Status: {project.Project_Status}. Recoverable within 30 days.'
        ),
    )
    db.session.commit()
    flash(f'"{project.project_name}" was moved to Recently deleted. It can be restored within 30 days.', category='success')
    return redirect(url_for('views.home', view='projects'))


@views.route('/project/<int:project_id>/restore', methods=['POST'])
def restore_project(project_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to restore a project.', category='error')
        return redirect(url_for('auth.login'))
    project = Project.query.filter(
        Project.project_id == project_id,
        Project.company_id == user.company_id,
        Project.deleted_at.isnot(None),
        Project.deleted_at > datetime.now().astimezone() - timedelta(days=PROJECT_DELETE_RETENTION_DAYS),
    ).first_or_404()
    project.deleted_at = None
    for meeting in Meeting.query.filter_by(project_id=project.project_id, deleted_with_project=True).all():
        archived_current_exists = any(
            revision.deleted_with_project
            and meeting_revision_order(revision) == (meeting.revision_order if meeting.revision_order is not None else (meeting.revision_No or 0))
            for revision in meeting.revision_history
        )
        for revision in meeting.revision_history:
            if revision.deleted_with_project:
                revision.deleted_at = None
                revision.deleted_with_project = False
        meeting.deleted_at = None
        meeting.deleted_with_project = False
        if archived_current_exists:
            promote_latest_active_revision(meeting)
        else:
            normalize_meeting_revision_numbers(meeting)
    record_project_audit(
        user,
        'Project restored from recently deleted archive',
        f'Project: {project_display_id(project)}, Name: {project.project_name}, Status: {project.Project_Status}.',
    )
    db.session.commit()
    flash(f'"{project.project_name}" was restored.', category='success')
    return redirect(url_for('views.project_archive'))


@views.route('/project/<int:project_id>/delete-permanently', methods=['POST'])
def delete_project_permanently(project_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to permanently delete a project.', category='error')
        return redirect(url_for('auth.login'))
    project = Project.query.filter(
        Project.project_id == project_id,
        Project.company_id == user.company_id,
        Project.deleted_at.isnot(None),
    ).first_or_404()
    project_name = project.project_name
    permanently_delete_project(project, user, 'Permanently deleted by user from the project archive.')
    db.session.commit()
    flash(f'"{project_name}" was permanently deleted.', category='success')
    return redirect(url_for('views.project_archive'))


@views.route('/project/<path:project_name>')
def project_details(project_name):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to view project details.', category='error')
        return redirect(url_for('auth.login'))

    project = Project.query.filter_by(
        project_name=project_name,
        company_id=user.company_id,
        deleted_at=None,
    ).first_or_404()
    project_id_label = project_display_id(project)
    last_project_edit = AuditLog.query.filter_by(
        company_id=user.company_id,
        action='Project details edited',
    ).filter(
        AuditLog.description.contains(f'Project ID: {project_id_label};'),
    ).order_by(AuditLog.timestamp.desc()).first()
    edit_client_rows = [project.client] if project.client else [None]
    edit_contractor_rows = list(project.contractors)
    if project.contractor and project.contractor not in edit_contractor_rows:
        edit_contractor_rows.insert(0, project.contractor)
    edit_consultant_rows = [project.consultant] if project.consultant else [None]
    return render_template(
        'project.html',
        project=project,
        last_saved_date=last_project_edit.timestamp if last_project_edit else project.Issued_Date,
        edit_client_rows=edit_client_rows or [None],
        edit_contractor_rows=edit_contractor_rows or [None],
        edit_consultant_rows=edit_consultant_rows or [None],
        edit_clients=Client.query.filter_by(company_id=user.company_id).order_by(Client.client_name).all(),
        edit_contractors=Contractor.query.filter_by(company_id=user.company_id).order_by(Contractor.contractor_name).all(),
        edit_consultants=Consultant.query.filter_by(company_id=user.company_id).order_by(Consultant.consultant_name).all(),
    )

def meeting_revision_number(project_id, title):
    revisions = Meeting.query.filter_by(project_id=project_id, meeting_title=title).all()
    numbers = []
    for item in revisions:
        try:
            numbers.append(int(item.revision_No or 0))
        except ValueError:
            pass
    return max(numbers, default=-1) + 1

def meeting_form_context(meeting=None):
    user = get_logged_in_user()
    company = user.company if user else None
    names = set()
    companies = set()
    if company:
        names.update(client.client_name for client in company.clients)
        names.update(contractor.contractor_name for contractor in company.contractors)
        names.update(consultant.consultant_name for consultant in company.consultants)
        companies.add(company.company_name)
        companies.update(client.client_name for client in company.clients)
        companies.update(contractor.contractor_name for contractor in company.contractors)
        companies.update(consultant.consultant_name for consultant in company.consultants)
    return {
        'meeting': meeting,
        'projects': Project.query.filter(
            Project.company_id == user.company_id,
            Project.deleted_at.is_(None),
            Project.Project_Status.notin_(PAST_PROJECT_STATUSES),
        ).order_by(Project.project_name).all() if user else [],
        'meeting_types': Meeting.__table__.columns.meeting_type.type.enums,
        'task_statuses': ('Open', 'Closed', 'Pending', 'FYI'),
        'task_priorities': ('High', 'Medium', 'Low', 'None'),
        'party_names': sorted(name for name in names if name),
        'party_companies': sorted(name for name in companies if name),
        'prepared_by': f'{user.first_name} {user.last_name}' if user else '',
    }


def get_company_meeting(meeting_id, user=None):
    user = user or get_logged_in_user()
    if not user:
        return None
    return Meeting.query.join(Project).filter(
        Meeting.meeting_id == meeting_id,
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Meeting.deleted_at.is_(None),
    ).first()

def save_sections(meeting):
    dates = request.form.getlist('section_date')
    titles = request.form.getlist('section_title')
    section_indexes = request.form.getlist('section_index')
    for index, title in enumerate(titles):
        if not title.strip():
            continue
        source_index = int(section_indexes[index]) if index < len(section_indexes) and section_indexes[index].isdigit() else index
        section = MeetingSection(
            meeting_id=meeting.meeting_id,
            section_date=datetime.strptime(dates[index], '%Y-%m-%d').date() if index < len(dates) and dates[index] else datetime.now().date(),
            section_title=title.strip(),
        )
        db.session.add(section)
        db.session.flush()
        task_titles = request.form.getlist(f'task_title_{source_index}')
        descriptions = request.form.getlist(f'task_description_{source_index}')
        assigned_to = request.form.getlist(f'task_assigned_to_{source_index}')
        due_dates = request.form.getlist(f'task_due_date_{source_index}')
        statuses = request.form.getlist(f'task_status_{source_index}')
        priorities = request.form.getlist(f'task_priority_{source_index}')
        notes = request.form.getlist(f'task_notes_{source_index}')
        for task_index, task_title in enumerate(task_titles):
            if task_title.strip():
                db.session.add(MeetingTask(
                    section_id=section.section_id,
                    task_title=task_title.strip(),
                    task_description=descriptions[task_index].strip() if task_index < len(descriptions) else '',
                    task_assigned_to=assigned_to[task_index].strip() if task_index < len(assigned_to) else '',
                    task_due_date=datetime.strptime(due_dates[task_index], '%Y-%m-%d').date() if task_index < len(due_dates) and due_dates[task_index] else None,
                    task_Status=statuses[task_index] if task_index < len(statuses) and statuses[task_index] in ('Open', 'Closed', 'Pending', 'FYI') else 'Open',
                    task_priority=priorities[task_index] if task_index < len(priorities) and priorities[task_index] in ('High', 'Medium', 'Low', 'None') else 'None',
                    task_notes=notes[task_index].strip() if task_index < len(notes) else '',
                ))

@views.route('/meeting/new', methods=['GET', 'POST'])
def new_meeting():
    if not get_logged_in_user():
        flash('Please log in to create a meeting.', category='error')
        return redirect(url_for('auth.login'))
    if request.method == 'GET':
        return render_template('meeting.html', **meeting_form_context())
    project = Project.query.filter(
        Project.project_id == request.form.get('project_id', type=int),
        Project.company_id == get_logged_in_user().company_id,
        Project.deleted_at.is_(None),
        Project.Project_Status.notin_(PAST_PROJECT_STATUSES),
    ).first()
    title = request.form.get('meeting_title', '').strip()
    if not project or not title:
        flash('Select a project and enter a meeting title.', category='error')
        return render_template('meeting.html', **meeting_form_context())
    user = get_logged_in_user()
    now = datetime.now().astimezone()
    meeting = Meeting(
        meeting_title=title,
        meeting_date=datetime.strptime(request.form['meeting_date'], '%Y-%m-%d').date() if request.form.get('meeting_date') else None,
        meeting_start_time=datetime.strptime(request.form['meeting_start_time'], '%H:%M').time() if request.form.get('meeting_start_time') else None,
        meeting_end_time=datetime.strptime(request.form['meeting_end_time'], '%H:%M').time() if request.form.get('meeting_end_time') else None,
        location=request.form.get('location', '').strip(),
        meeting_type=request.form.get('meeting_type', 'Technical').strip(),
        meeting_description=request.form.get('meeting_description', '').strip(),
        agenda=request.form.get('agenda', '').strip(),
        prepared_by=f'{user.first_name} {user.last_name}',
        chairperson=request.form.get('chairperson', '').strip(),
        participants='\n'.join(value.strip() for value in request.form.getlist('participants') if value.strip()),
        participant_company='\n'.join(value.strip() for value in request.form.getlist('participant_company') if value.strip()),
        project_id=project.project_id, date_Issued=now, revision_No=0,
    )
    db.session.add(meeting)
    db.session.flush()
    save_sections(meeting)
    db.session.commit()
    flash('Meeting created successfully.', category='success')
    return redirect(url_for('views.meeting_details', meeting_id=meeting.meeting_id))

@views.route('/meeting/<int:meeting_id>')
def meeting_details(meeting_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to view meeting details.', category='error')
        return redirect(url_for('auth.login'))
    meeting = get_company_meeting(meeting_id, user)
    if not meeting:
        return redirect(url_for('views.home'))
    return render_template('meeting_preview.html', meeting=meeting)


@views.route('/meeting/<int:meeting_id>/edit')
def edit_meeting(meeting_id):
    user = get_logged_in_user()
    if not user:
        flash('Please log in to edit meeting details.', category='error')
        return redirect(url_for('auth.login'))
    meeting = get_company_meeting(meeting_id, user)
    if not meeting:
        return redirect(url_for('views.home'))
    return render_template('meeting.html', **meeting_form_context(meeting), focus_task_id=request.args.get('task_id', type=int))

def export_filename(meeting, extension):
    project_id = project_display_id(meeting.project) if meeting.project else f'PRJ{meeting.project_id:02d}'
    downloaded_utc = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'MOM{meeting.meeting_id:04d}_{project_id}_Rev_{meeting.revision_No or 0}_{downloaded_utc}.{extension}'

def meeting_export_sections(meeting):
    sections = []
    task_number = 1
    for section in meeting.sections:
        tasks = []
        for task in sorted(section.tasks, key=lambda item: item.task_id):
            tasks.append([
                task_number,
                task.task_title or '',
                task.task_description or '',
                task.task_assigned_to or '',
                task.task_due_date.strftime('%d/%m/%Y') if task.task_due_date else '',
                task.task_Status or '',
                task.task_priority or 'None',
                task.task_notes or '',
            ])
            task_number += 1
        sections.append({
            'date': section.section_date.strftime('%d/%m/%Y') if section.section_date else '',
            'title': section.section_title or '',
            'tasks': tasks,
        })
    return sections

def meeting_export_context(meeting):
    project = meeting.project
    participant_names = (meeting.participants or '').splitlines()
    participant_companies = (meeting.participant_company or '').splitlines()
    participants = list(zip_longest(participant_names, participant_companies, fillvalue=''))
    return project, participants, meeting_export_sections(meeting)

def export_status_class(status):
    return re.sub(r'[^a-z]+', '-', (status or '').lower()).strip('-') or 'open'

@views.route('/meeting/<int:meeting_id>/export/excel')
def export_meeting_excel(meeting_id):
    user = get_logged_in_user()
    if not user:
        return redirect(url_for('auth.login'))
    meeting = get_company_meeting(meeting_id, user)
    if not meeting:
        return redirect(url_for('views.home'))
    project, participants, sections = meeting_export_context(meeting)
    participant_rows = ''.join(f'<tr><td>{escape(name)}</td><td>{escape(company)}</td></tr>' for name, company in participants)
    action_rows = []
    for section in sections:
        action_rows.append(f'<tr class="section"><th colspan="8">{escape(section["date"])} - {escape(section["title"])}</th></tr>')
        action_rows.append('<tr><th>No.</th><th>Action / Key Item</th><th>Description</th><th>Assigned_To</th><th>Due Date</th><th>Progress</th><th>Priority</th><th>Remarks</th></tr>')
        for task_id, title, description, assigned, due_date, status, priority, notes in section['tasks']:
            status_label = 'For Info' if status == 'FYI' else status
            action_rows.append(
                '<tr>'
                f'<td>{task_id}</td><td><strong>{escape(title)}</strong></td><td>{escape(description).replace(chr(10), "<br>")}</td>'
                f'<td>{escape(assigned).replace(chr(10), "<br>")}</td><td>{escape(due_date)}</td>'
                f'<td class="status {export_status_class(status)}">{escape(status_label)}</td><td class="priority priority-{export_status_class(priority)}">{escape("" if priority == "None" else priority)}</td>'
                f'<td>{escape(notes).replace(chr(10), "<br>")}</td></tr>'
            )
    project_name = project.project_name if project else ''
    project_parties = f'<h2>Project Information</h2><table><tr><th>Company</th><td>{escape(project.company.company_name if project and project.company else "")}</td><th>Client</th><td>{escape(project.client.client_name if project and project.client else "")}</td></tr><tr><th>Contractor</th><td>{escape(", ".join(c.contractor_name for c in project.company.contractors) if project and project.company else "")}</td><th>Consultant</th><td>{escape(", ".join(c.consultant_name for c in project.company.consultants) if project and project.company else "")}</td></tr></table>'
    document = f'''<html><head><meta charset="utf-8"><style>
body{{font-family:Arial,sans-serif;font-size:11pt;color:#111}}h1{{text-align:center;font-size:18pt}}h2{{background:#d9e1f2;padding:6px;margin:14px 0 0}}table{{border-collapse:collapse;width:100%;margin-bottom:10px}}th,td{{border:1px solid #777;padding:6px;vertical-align:top}}th{{background:#d9e1f2;text-align:left}}.label{{font-weight:bold;width:18%}}.section th{{background:#eee;font-size:12pt}}.status,.priority{{font-weight:bold;text-align:center}}.open,.pending,.priority-high{{background:#ffc7ce;color:#9c0006}}.fyi,.priority-medium{{background:#ffeb9c;color:#9c6500}}.closed,.priority-low,.priority-none{{background:#c6efce;color:#006100}}.in-progress{{background:#c6d9f1;color:#1f4e79}}.incomplete{{background:#ffeb9c;color:#9c6500}}.cancelled{{background:#d9d9d9;color:#555}}
</style></head><body><h1>MINUTES OF MEETING</h1><table><tr><th class="label">Meeting ID</th><td>MOM{meeting.meeting_id:04d}</td><th class="label">Revision</th><td>Rev_{meeting.revision_No or 0}</td></tr><tr><th class="label">Project ID</th><td>{escape(project_display_id(project) if project else '')}</td><th class="label">Project name</th><td>{escape(project_name)}</td></tr><tr><th class="label">Meeting title</th><td>{escape(meeting.meeting_title)}</td><th class="label">Meeting type</th><td>{escape(meeting.meeting_type or '')}</td></tr><tr><th class="label">Date</th><td>{escape(meeting.meeting_date.strftime('%d/%m/%Y') if meeting.meeting_date else '')}</td><th class="label">Location</th><td>{escape(meeting.location or '')}</td></tr><tr><th class="label">Start / End</th><td>{escape(str(meeting.meeting_start_time or ''))} / {escape(str(meeting.meeting_end_time or ''))}</td><th class="label">Chairperson</th><td>{escape(meeting.chairperson or '')}</td></tr><tr><th class="label">Prepared by</th><td>{escape(meeting.prepared_by or '')}</td><th class="label">Issued</th><td>{escape(meeting.date_Issued.strftime('%d/%m/%Y %H:%M') if meeting.date_Issued else '')}</td></tr></table><h2>Participants</h2><table><tr><th>Name</th><th>Company</th></tr>{participant_rows}</table><h2>Agenda</h2><p>{escape(meeting.agenda or '').replace(chr(10), '<br>')}</p><h2>Meeting description</h2><p>{escape(meeting.meeting_description or '').replace(chr(10), '<br>')}</p><h2>Action Items</h2><table>{''.join(action_rows)}</table></body></html>'''
    project_site_row = f'<tr><th class="label">Project site / location</th><td colspan="3">{escape(project.project_site if project else "")}</td></tr>'
    document = document.replace('</table><h2>Participants</h2>', project_site_row + '</table><h2>Participants</h2>')
    document = document.replace('<th class="label">Location</th>', '<th class="label">Meeting location</th>')
    document = document.replace('<th class="label">Chairperson</th>', '<th class="label">Host</th>')
    document = document.replace('<h2>Participants</h2>', project_parties + '<h2>Participants</h2>')
    return Response(document, mimetype='application/vnd.ms-excel', headers={'Content-Disposition': f'attachment; filename="{export_filename(meeting, "xls")}"'})

def pdf_escape(value):
    return str(value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

def make_simple_pdf(lines):
    expanded = []
    for item in lines:
        text, color = item if isinstance(item, tuple) else (item, (0, 0, 0))
        text = str(text)
        while text:
            expanded.append((text[:105], color))
            text = text[105:]
        if not expanded or expanded[-1][0] != '':
            expanded.append(('', (0, 0, 0)))
    pages = [expanded[index:index + 52] for index in range(0, len(expanded), 52)] or [[]]
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', None]
    page_numbers = []
    content_numbers = []
    next_number = 3
    for _ in pages:
        page_numbers.append(next_number)
        content_numbers.append(next_number + 1)
        next_number += 2
    font_number = next_number
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(f"{number} 0 R" for number in page_numbers)}] /Count {len(pages)} >>'.encode()
    for page_index, page in enumerate(pages):
        stream_lines = ['BT', '/F1 9 Tf', '36 756 Td']
        for text, color in page:
            red, green, blue = color
            stream_lines.append(f'{red} {green} {blue} rg')
            stream_lines.append(f'({pdf_escape(text)}) Tj')
            stream_lines.append('0 -14 Td')
        stream_lines.append('ET')
        stream = '\n'.join(stream_lines).encode('latin-1', 'replace')
        page_object = f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_number} 0 R >> >> /Contents {content_numbers[page_index]} 0 R >>'.encode()
        content_object = b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream'
        objects.extend([page_object, content_object])
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(pdf)
    pdf.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
    pdf.extend(''.join(f'{offset:010d} 00000 n \n' for offset in offsets).encode())
    pdf.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    return bytes(pdf)

@views.route('/meeting/<int:meeting_id>/export/pdf')
def export_meeting_pdf(meeting_id):
    user = get_logged_in_user()
    if not user:
        return redirect(url_for('auth.login'))
    meeting = get_company_meeting(meeting_id, user)
    if not meeting:
        return redirect(url_for('views.home'))
    revision_order_value = request.args.get('revision_order')
    revision_value = request.args.get('revision')
    revision_lookup_value = revision_order_value if revision_order_value is not None else revision_value
    if revision_lookup_value is not None:
        try:
            revision_number = int(revision_lookup_value)
        except ValueError:
            return jsonify({'error': 'invalid_revision'}), 400
        current_revision = meeting.revision_No or 0
        current_order = meeting.revision_order if meeting.revision_order is not None else current_revision
        requested_current = revision_number == current_order if revision_order_value is not None else revision_number == current_revision
        if not requested_current:
            revision = next(
                (
                    item for item in meeting.revision_history
                    if item.deleted_at is None
                    and (
                        meeting_revision_order(item) == revision_number
                        if revision_order_value is not None
                        else item.revision_No == revision_number
                    )
                ),
                None,
            )
            if not revision:
                return jsonify({'error': 'revision_not_found'}), 404
            meeting = meeting_pdf_revision(meeting, revision)
    project, participants, sections = meeting_export_context(meeting)
    buffer = BytesIO()
    page_width, page_height = A4
    content_width = page_width - (20 * mm)
    styles = getSampleStyleSheet()
    body = ParagraphStyle('body', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, spaceAfter=0)
    small = ParagraphStyle('small', parent=body, fontSize=8, leading=10)
    title = ParagraphStyle('title', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=18, alignment=TA_CENTER, spaceAfter=4)
    section_style = ParagraphStyle('section', parent=body, fontName='Helvetica-Bold', fontSize=8, leading=10)

    def p(value, style=body):
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)

    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#173d3c'))
        canvas.setLineWidth(1.5)
        canvas.line(12 * mm, page_height - 25 * mm, page_width - 12 * mm, page_height - 25 * mm)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawString(14 * mm, page_height - 18 * mm, 'MINUTES OF MEETING')
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawRightString(page_width - 14 * mm, page_height - 18 * mm, f'MOM{meeting.meeting_id:04d}  |  Rev_{meeting.revision_No or 0}')
        canvas.setFont('Helvetica', 8)
        canvas.drawCentredString(page_width / 2, 9 * mm, f'Page {doc.page}')
        canvas.restoreState()

    doc = BaseDocTemplate(buffer, pagesize=A4, leftMargin=10 * mm, rightMargin=10 * mm, topMargin=28 * mm, bottomMargin=14 * mm)
    doc.addPageTemplates([PageTemplate(id='mom', frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')], onPage=header_footer)])
    story = [Paragraph('MINUTES OF MEETING', title)]
    project_id = project_display_id(project) if project else ''
    metadata = [
        [p('Meeting ID', section_style), p(f'MOM{meeting.meeting_id:04d}'), p('Project ID', section_style), p(project_id), p('Revision', section_style), p(f'Rev_{meeting.revision_No or 0}')],
        [p('Project name', section_style), p(project.project_name if project else ''), p('Meeting title', section_style), p(meeting.meeting_title), p('Meeting type', section_style), p(meeting.meeting_type)],
        [p('Company', section_style), p(project.company.company_name if project and project.company else ''), p('Client', section_style), p(project.client.client_name if project and project.client else ''), p('Meeting location', section_style), p(meeting.location)],
        [p('Contractor', section_style), p(', '.join(c.contractor_name for c in project.company.contractors) if project and project.company else ''), p('Consultant', section_style), p(', '.join(c.consultant_name for c in project.company.consultants) if project and project.company else ''), p('Date', section_style), p(meeting.meeting_date.strftime('%d/%m/%Y') if meeting.meeting_date else '')],
        [p('Start / End', section_style), p(f'{meeting.meeting_start_time or ""} - {meeting.meeting_end_time or ""}'), p('Host', section_style), p(meeting.chairperson), p('Prepared by', section_style), p(meeting.prepared_by)],
        [p('Project site / location', section_style), p(project.project_site if project else ''), '', '', '', ''],
    ]
    meta_table = Table(metadata, colWidths=[22*mm, 38*mm, 22*mm, 43*mm, 22*mm, 43*mm], repeatRows=0)
    meta_table.setStyle(TableStyle([('SPAN', (1, 5), (5, 5)), ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#888888')), ('BACKGROUND', (0, 0), (-1, -1), colors.white), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    story.extend([meta_table, Spacer(1, 5)])
    story.append(Table([[p('Participants', section_style)]], colWidths=[content_width], style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eaf2fb')), ('BOX', (0, 0), (-1, -1), .5, colors.HexColor('#777777')), ('LEFTPADDING', (0, 0), (-1, -1), 5)])))
    participant_pairs = list(participants)
    participant_rows = []
    for index in range(0, len(participant_pairs), 2):
        left = participant_pairs[index]
        right = participant_pairs[index + 1] if index + 1 < len(participant_pairs) else ('', '')
        participant_rows.append([p(left[0]), p(left[1]), p(right[0]), p(right[1])])
    participant_table = Table([[p('Name', section_style), p('Company', section_style), p('Name', section_style), p('Company', section_style)]] + participant_rows, colWidths=[30*mm, 65*mm, 30*mm, 65*mm], repeatRows=1)
    participant_table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#999999')), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeee')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    story.extend([participant_table, Spacer(1, 5), Table([[p('Agenda', section_style), p('Meeting description', section_style)], [p(meeting.agenda), p(meeting.meeting_description)]], colWidths=[95*mm, 95*mm], style=TableStyle([('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#999999')), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf2fb')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5), ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)])), Spacer(1, 6)])
    story.append(Table([[p('Action Items', section_style)]], colWidths=[content_width], style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eaf2fb')), ('BOX', (0, 0), (-1, -1), .5, colors.HexColor('#777777')), ('LEFTPADDING', (0, 0), (-1, -1), 5)])))
    status_backgrounds = {'open': colors.HexColor('#ffc7ce'), 'pending': colors.HexColor('#ffc7ce'), 'fyi': colors.HexColor('#ffeb9c'), 'closed': colors.HexColor('#c6efce')}
    priority_backgrounds = {'high': colors.HexColor('#ffc7ce'), 'medium': colors.HexColor('#ffeb9c'), 'low': colors.HexColor('#c6efce')}
    for section in sections:
        rows = [[p('No.', section_style), p('Action / Key Item', section_style), p('Description', section_style), p('Assigned_To', section_style), p('Due Date', section_style), p('Progress', section_style), p('Priority', section_style), p('Remarks', section_style)]]
        for task_id, task_title, description, assigned, due_date, status, priority, notes in section['tasks']:
            status_label = 'For Info' if status == 'FYI' else status
            rows.append([p(task_id), p(task_title, section_style), p(description, small), p(assigned, small), p(due_date), p(status_label, section_style), p('' if priority == 'None' else priority, section_style), p(notes, small)])
        table_rows = [[p(f'{section["date"]} - {section["title"]}', section_style)] + [''] * 7] + rows
        table = Table(table_rows, colWidths=[9*mm, 31*mm, 38*mm, 28*mm, 20*mm, 17*mm, 16*mm, 31*mm], repeatRows=2)
        table.setStyle(TableStyle([('SPAN', (0, 0), (7, 0)), ('BACKGROUND', (0, 0), (7, 0), colors.HexColor('#eeeeee')), ('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#777777')), ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#eaf2fb')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        for row_index, task in enumerate(section['tasks'], start=2):
            status = export_status_class(task[5])
            priority = export_status_class(task[6])
            table.setStyle(TableStyle([
                ('BACKGROUND', (5, row_index), (5, row_index), status_backgrounds.get(status, colors.white)),
                *([('BACKGROUND', (6, row_index), (6, row_index), priority_backgrounds[priority])] if priority in priority_backgrounds else []),
            ]))
        story.append(KeepTogether(table))
    doc.build(story)
    disposition = 'inline' if request.args.get('inline') == '1' else 'attachment'
    return Response(buffer.getvalue(), mimetype='application/pdf', headers={'Content-Disposition': f'{disposition}; filename="{export_filename(meeting, "pdf")}"'})

def meeting_pdf_revision(current_meeting, revision):
    snapshot = revision.snapshot or {}
    values = snapshot.get('meeting') or []

    def snapshot_date(value):
        return datetime.fromisoformat(value).date() if value else None

    def snapshot_time(value):
        return time.fromisoformat(value) if value else None

    meeting_fields = {
        'meeting_id': current_meeting.meeting_id,
        'meeting_title': values[0] if len(values) > 0 else current_meeting.meeting_title,
        'meeting_date': snapshot_date(values[1]) if len(values) > 1 else None,
        'meeting_start_time': snapshot_time(values[2]) if len(values) > 2 else None,
        'meeting_end_time': snapshot_time(values[3]) if len(values) > 3 else None,
        'location': values[4] if len(values) > 4 else '',
        'meeting_type': values[5] if len(values) > 5 else 'Technical',
        'meeting_description': values[6] if len(values) > 6 else '',
        'agenda': values[7] if len(values) > 7 else '',
        'chairperson': values[8] if len(values) > 8 else '',
        'participants': values[9] if len(values) > 9 else '',
        'participant_company': values[10] if len(values) > 10 else '',
        'prepared_by': current_meeting.prepared_by,
        'project_id': current_meeting.project_id,
        'project': current_meeting.project,
        'revision_No': revision.revision_No,
        'date_Issued': current_meeting.date_Issued,
        'rev_Date': revision.rev_Date,
    }
    sections = []
    task_id = 0
    for section_values in snapshot.get('sections') or []:
        section_date = section_values[0] if len(section_values) > 0 else ''
        section_title = section_values[1] if len(section_values) > 1 else ''
        tasks = []
        for task_values in (section_values[2] if len(section_values) > 2 else []):
            task_id += 1
            priority = 'None'
            notes = ''
            if len(task_values) > 6:
                priority, notes = task_values[5], task_values[6]
            elif len(task_values) > 5:
                if task_values[5] in ('High', 'Medium', 'Low', 'None'):
                    priority = task_values[5]
                else:
                    notes = task_values[5]
            tasks.append(SimpleNamespace(
                task_id=task_id,
                task_title=task_values[0] if len(task_values) > 0 else '',
                task_description=task_values[1] if len(task_values) > 1 else '',
                task_assigned_to=task_values[2] if len(task_values) > 2 else '',
                task_due_date=snapshot_date(task_values[3]) if len(task_values) > 3 and task_values[3] else None,
                task_Status=task_values[4] if len(task_values) > 4 else 'Open',
                task_priority=priority or 'None',
                task_notes=notes,
            ))
        sections.append(SimpleNamespace(
            section_date=snapshot_date(section_date) if section_date else None,
            section_title=section_title,
            tasks=tasks,
        ))
    meeting_fields['sections'] = sections
    return SimpleNamespace(**meeting_fields)

def meeting_submission_snapshot(meeting):
    def value(name, default=''):
        return request.form.get(name, default).strip()

    def date_value(name):
        raw = value(name)
        return datetime.strptime(raw, '%Y-%m-%d').date() if raw else None

    def time_value(name):
        raw = value(name)
        return datetime.strptime(raw, '%H:%M').time() if raw else None

    sections = []
    dates = request.form.getlist('section_date')
    titles = request.form.getlist('section_title')
    indexes = request.form.getlist('section_index')
    for index, title in enumerate(titles):
        source_index = int(indexes[index]) if index < len(indexes) and indexes[index].isdigit() else index
        task_titles = request.form.getlist(f'task_title_{source_index}')
        descriptions = request.form.getlist(f'task_description_{source_index}')
        assigned = request.form.getlist(f'task_assigned_to_{source_index}')
        due_dates = request.form.getlist(f'task_due_date_{source_index}')
        statuses = request.form.getlist(f'task_status_{source_index}')
        priorities = request.form.getlist(f'task_priority_{source_index}')
        notes = request.form.getlist(f'task_notes_{source_index}')
        tasks = []
        for task_index, task_title in enumerate(task_titles):
            if task_title.strip():
                due_date = due_dates[task_index].strip() if task_index < len(due_dates) else ''
                tasks.append((
                    task_title.strip(),
                    descriptions[task_index].strip() if task_index < len(descriptions) else '',
                    assigned[task_index].strip() if task_index < len(assigned) else '',
                    due_date,
                    statuses[task_index].strip() if task_index < len(statuses) else 'Open',
                    priorities[task_index].strip() if task_index < len(priorities) else 'None',
                    notes[task_index].strip() if task_index < len(notes) else '',
                ))
        sections.append((dates[index].strip() if index < len(dates) else '', title.strip(), tasks))

    return {
        'meeting': (
            value('meeting_title', meeting.meeting_title),
            date_value('meeting_date'),
            time_value('meeting_start_time'),
            time_value('meeting_end_time'),
            value('location'),
            value('meeting_type', meeting.meeting_type or 'Technical'),
            value('meeting_description'),
            value('agenda'),
            value('chairperson'),
            '\n'.join(item.strip() for item in request.form.getlist('participants') if item.strip()),
            '\n'.join(item.strip() for item in request.form.getlist('participant_company') if item.strip()),
        ),
        'sections': sections,
    }

def meeting_database_snapshot(meeting):
    sections = []
    for section in meeting.sections:
        sections.append((
            section.section_date.isoformat() if section.section_date else '',
            section.section_title or '',
            [(task.task_title or '', task.task_description or '', task.task_assigned_to or '', task.task_due_date.isoformat() if task.task_due_date else '', task.task_Status or 'Open', task.task_priority or 'None', task.task_notes or '') for task in section.tasks],
        ))
    return {
        'meeting': (
            meeting.meeting_title or '', meeting.meeting_date, meeting.meeting_start_time, meeting.meeting_end_time,
            meeting.location or '', meeting.meeting_type or 'Technical', meeting.meeting_description or '', meeting.agenda or '',
            meeting.chairperson or '', meeting.participants or '', meeting.participant_company or '',
        ),
        'sections': sections,
    }

def meeting_revision_snapshot(meeting):
    snapshot = meeting_database_snapshot(meeting)
    meeting_values = list(snapshot['meeting'])
    meeting_values[1] = meeting_values[1].isoformat() if meeting_values[1] else None
    meeting_values[2] = meeting_values[2].isoformat() if meeting_values[2] else None
    meeting_values[3] = meeting_values[3].isoformat() if meeting_values[3] else None
    return {
        'meeting': meeting_values,
        'sections': snapshot['sections'],
    }

def meeting_revision_order(revision):
    return revision.revision_order if revision.revision_order is not None else revision.revision_No

def normalize_meeting_revision_numbers(meeting):
    active_history = sorted(
        (
            revision for revision in meeting.revision_history
            if revision.deleted_at is None and revision not in db.session.deleted
        ),
        key=lambda revision: (meeting_revision_order(revision), revision.revision_id),
    )
    for revision_number, revision in enumerate(active_history):
        revision.revision_No = revision_number
    if meeting.deleted_at is None:
        meeting.revision_No = len(active_history)

def apply_meeting_revision_snapshot(meeting, snapshot, revision_number, revision_order):
    values = (snapshot or {}).get('meeting') or []

    def snapshot_value(index, default=''):
        return values[index] if len(values) > index and values[index] is not None else default

    meeting.meeting_title = snapshot_value(0, meeting.meeting_title)
    meeting.meeting_date = datetime.fromisoformat(values[1]).date() if len(values) > 1 and values[1] else None
    meeting.meeting_start_time = time.fromisoformat(values[2]) if len(values) > 2 and values[2] else None
    meeting.meeting_end_time = time.fromisoformat(values[3]) if len(values) > 3 and values[3] else None
    meeting.location = snapshot_value(4)
    meeting.meeting_type = snapshot_value(5, 'Technical')
    meeting.meeting_description = snapshot_value(6)
    meeting.agenda = snapshot_value(7)
    meeting.chairperson = snapshot_value(8)
    meeting.participants = snapshot_value(9)
    meeting.participant_company = snapshot_value(10)
    meeting.revision_No = revision_number
    meeting.revision_order = revision_order
    meeting.deleted_at = None
    meeting.deleted_with_project = False
    meeting.sections.clear()
    db.session.flush()
    for section_values in (snapshot or {}).get('sections') or []:
        section_date = section_values[0] if len(section_values) > 0 else ''
        section = MeetingSection(
            meeting_id=meeting.meeting_id,
            section_date=datetime.fromisoformat(section_date).date() if section_date else datetime.now().date(),
            section_title=section_values[1] if len(section_values) > 1 else '',
        )
        db.session.add(section)
        db.session.flush()
        for task_values in section_values[2] if len(section_values) > 2 else []:
            priority = 'None'
            notes = ''
            if len(task_values) > 6:
                priority, notes = task_values[5], task_values[6]
            elif len(task_values) > 5:
                if task_values[5] in ('High', 'Medium', 'Low', 'None'):
                    priority = task_values[5]
                else:
                    notes = task_values[5]
            db.session.add(MeetingTask(
                section_id=section.section_id,
                task_title=task_values[0] if len(task_values) > 0 else '',
                task_description=task_values[1] if len(task_values) > 1 else '',
                task_assigned_to=task_values[2] if len(task_values) > 2 else '',
                task_due_date=datetime.fromisoformat(task_values[3]).date() if len(task_values) > 3 and task_values[3] else None,
                task_Status=task_values[4] if len(task_values) > 4 else 'Open',
                task_priority=priority or 'None',
                task_notes=notes,
            ))

def store_current_meeting_revision(meeting, deleted_at=None, deleted_with_project=False):
    revision = MeetingRevision(
        meeting_id=meeting.meeting_id,
        revision_No=meeting.revision_No or 0,
        revision_order=meeting.revision_order if meeting.revision_order is not None else (meeting.revision_No or 0),
        rev_Date=meeting.rev_Date or meeting.date_Issued or datetime.now().astimezone(),
        snapshot=meeting_revision_snapshot(meeting),
        deleted_at=deleted_at,
        deleted_with_project=deleted_with_project,
    )
    db.session.add(revision)
    db.session.flush()
    return revision

def promote_latest_active_revision(meeting):
    latest = max(
        (revision for revision in meeting.revision_history if revision.deleted_at is None),
        key=lambda revision: (meeting_revision_order(revision), revision.revision_id),
        default=None,
    )
    if not latest:
        return False
    apply_meeting_revision_snapshot(
        meeting,
        latest.snapshot,
        latest.revision_No,
        meeting_revision_order(latest),
    )
    db.session.delete(latest)
    normalize_meeting_revision_numbers(meeting)
    return True

def archive_active_meeting_revision(meeting, revision_order, user, deleted_with_project=False, deleted_at=None):
    now = deleted_at or datetime.now().astimezone()
    current_order = meeting.revision_order if meeting.revision_order is not None else (meeting.revision_No or 0)
    if meeting.deleted_at is not None:
        flash('This meeting has no active revisions to archive.', category='error')
        return None
    if revision_order == current_order:
        archived_revision = store_current_meeting_revision(
            meeting,
            deleted_at=now,
            deleted_with_project=deleted_with_project,
        )
        archived_number = archived_revision.revision_No
        if not promote_latest_active_revision(meeting):
            meeting.deleted_at = now
            meeting.deleted_with_project = deleted_with_project
    else:
        archived_revision = next(
            (
                revision for revision in meeting.revision_history
                if meeting_revision_order(revision) == revision_order and revision.deleted_at is None
            ),
            None,
        )
        if not archived_revision:
            flash('That meeting revision is no longer active.', category='error')
            return None
        archived_number = archived_revision.revision_No
        archived_revision.deleted_at = now
        archived_revision.deleted_with_project = deleted_with_project
        normalize_meeting_revision_numbers(meeting)
    record_project_audit(
        user,
        'Meeting revision moved to Recently deleted archive',
        f'Meeting: MOM{meeting.meeting_id:04d}, Revision: Rev_{archived_number}, Title: {meeting.meeting_title}. Recoverable within 30 days.',
    )
    return archived_number

def revision_archive_entry(meeting, revision):
    archived_meeting = meeting_pdf_revision(meeting, revision)
    return SimpleNamespace(
        meeting_id=meeting.meeting_id,
        revision_id=revision.revision_id,
        revision_No=revision.revision_No,
        revision_order=meeting_revision_order(revision),
        rev_Date=revision.rev_Date,
        deleted_at=revision.deleted_at,
        deleted_with_project=revision.deleted_with_project,
        project=meeting.project,
        meeting=archived_meeting,
    )

@views.route('/meeting/<int:meeting_id>/save', methods=['POST'])
def save_meeting_revision(meeting_id):
    user = get_logged_in_user()
    if not user:
        return redirect(url_for('auth.login'))
    original = get_company_meeting(meeting_id, user)
    if not original:
        return redirect(url_for('views.home'))
    if meeting_submission_snapshot(original) == meeting_database_snapshot(original):
        flash('Nothing was changed.', category='success')
        return redirect(url_for('views.meeting_details', meeting_id=original.meeting_id))
    now = datetime.now().astimezone()
    previous_revision = original.revision_No or 0
    db.session.add(MeetingRevision(
        meeting_id=original.meeting_id,
        revision_No=previous_revision,
        revision_order=original.revision_order if original.revision_order is not None else previous_revision,
        rev_Date=original.rev_Date or original.date_Issued or now,
        snapshot=meeting_revision_snapshot(original),
    ))
    original.meeting_title = request.form.get('meeting_title', original.meeting_title).strip()
    original.meeting_date = datetime.strptime(request.form['meeting_date'], '%Y-%m-%d').date() if request.form.get('meeting_date') else None
    original.meeting_start_time = datetime.strptime(request.form['meeting_start_time'], '%H:%M').time() if request.form.get('meeting_start_time') else None
    original.meeting_end_time = datetime.strptime(request.form['meeting_end_time'], '%H:%M').time() if request.form.get('meeting_end_time') else None
    original.location = request.form.get('location', '').strip()
    original.meeting_type = request.form.get('meeting_type', 'Technical').strip()
    original.meeting_description = request.form.get('meeting_description', '').strip()
    original.agenda = request.form.get('agenda', '').strip()
    original.prepared_by = original.prepared_by or f'{user.first_name} {user.last_name}'
    original.chairperson = request.form.get('chairperson', '').strip()
    original.participants = '\n'.join(value.strip() for value in request.form.getlist('participants') if value.strip())
    original.participant_company = '\n'.join(value.strip() for value in request.form.getlist('participant_company') if value.strip())
    original.rev_Date = now
    original.revision_No = previous_revision + 1
    original.revision_order = max(
        [original.revision_order or previous_revision]
        + [meeting_revision_order(revision) for revision in original.revision_history]
    ) + 1
    original.sections.clear()
    db.session.flush()
    save_sections(original)
    db.session.commit()
    flash(f'Meeting MOM{original.meeting_id:04d} saved as Rev_{original.revision_No}.', category='success')
    return redirect(url_for('views.meeting_details', meeting_id=original.meeting_id))


@views.route('/api/meetings')
def meetings_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    meeting_records = Meeting.query.join(Project).filter(
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Project.Project_Status.notin_(PAST_PROJECT_STATUSES),
        Meeting.deleted_at.is_(None),
    ).all()
    meeting_entries = []
    for meeting in meeting_records:
        project = meeting.project
        common_fields = {
            'id': meeting.meeting_id,
            'project': project.project_name if project else '',
            'project_id': project_display_id(project) if project else '',
            'company': project.company.company_name if project and project.company else '',
            'client': project.client.client_name if project and project.client else '',
        }
        for revision in meeting.revision_history:
            if revision.deleted_at is not None:
                continue
            snapshot_meeting = (revision.snapshot or {}).get('meeting') or []
            modified_at = revision.rev_Date
            meeting_entries.append({
                **common_fields,
                'title': snapshot_meeting[0] if snapshot_meeting else meeting.meeting_title,
                'date': snapshot_meeting[1] if len(snapshot_meeting) > 1 and snapshot_meeting[1] else '',
                'revision_number': revision.revision_No,
                'revision_order': meeting_revision_order(revision),
                'revision': f'Rev_{revision.revision_No}',
                'modified': modified_at.isoformat(),
                'is_current': False,
                '_sort_modified': modified_at.replace(tzinfo=timezone.utc) if modified_at.tzinfo is None else modified_at.astimezone(timezone.utc),
            })

        modified_at = meeting.rev_Date or meeting.date_Issued
        sort_modified = (
            modified_at.replace(tzinfo=timezone.utc)
            if modified_at and modified_at.tzinfo is None
            else modified_at.astimezone(timezone.utc)
            if modified_at
            else datetime.min.replace(tzinfo=timezone.utc)
        )
        meeting_entries.append({
            **common_fields,
            'title': meeting.meeting_title,
            'date': meeting.meeting_date.isoformat() if meeting.meeting_date else '',
            'revision_number': meeting.revision_No or 0,
            'revision_order': meeting.revision_order if meeting.revision_order is not None else (meeting.revision_No or 0),
            'revision': f'Rev_{meeting.revision_No or 0}',
            'modified': modified_at.isoformat() if modified_at else '',
            'is_current': True,
            '_sort_modified': sort_modified,
        })

    meeting_entries.sort(
        key=lambda entry: (entry['_sort_modified'], entry['revision_number']),
        reverse=True,
    )
    for entry in meeting_entries:
        del entry['_sort_modified']
    return jsonify(meeting_entries)


@views.route('/api/assistant/models')
def assistant_models_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    from llm import available_models
    return jsonify({'models': available_models()})


@views.route('/api/assistant/chat', methods=['POST'])
def assistant_chat_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    model_id = (data.get('model') or 'gemini').strip().casefold()
    if not question:
        return jsonify({'error': 'question_required'}), 400
    try:
        from llm import ask_agent
        return jsonify(ask_agent(user, question, model_id))
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception:
        return jsonify({'error': 'The assistant could not read the authorised project records.'}), 500


def calendar_event_payload(event, source='event'):
    return {
        'id': f'{source}-{event.event_id if source == "event" else event.meeting_id}',
        'title': event.event_title if source == 'event' else event.meeting_title,
        'date': event.event_date.isoformat() if source == 'event' else (event.meeting_date.isoformat() if event.meeting_date else ''),
        'start_time': event.start_time.strftime('%H:%M') if source == 'event' and event.start_time else (event.meeting_start_time.strftime('%H:%M') if source == 'meeting' and event.meeting_start_time else ''),
        'end_time': event.end_time.strftime('%H:%M') if source == 'event' and event.end_time else (event.meeting_end_time.strftime('%H:%M') if source == 'meeting' and event.meeting_end_time else ''),
        'project': event.project.project_name if event.project else '',
        'project_id': event.project_id,
        'event_description': event.event_description or '' if source == 'event' else '',
        'notes': event.notes or '' if source == 'event' else '',
        'source': source,
    }


@views.route('/api/calendar-events', methods=['GET', 'POST'])
def calendar_events_api():
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401

    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        title = (data.get('title') or '').strip()
        date_value = (data.get('date') or '').strip()
        try:
            project_id = int(data.get('project_id'))
        except (TypeError, ValueError):
            project_id = None
        project = Project.query.filter(
            Project.project_id == project_id,
            Project.company_id == user.company_id,
            Project.deleted_at.is_(None),
            Project.Project_Status.notin_(PAST_PROJECT_STATUSES),
        ).first()
        if not title or not date_value or not project:
            return jsonify({'error': 'Title, date, and a company project are required.'}), 400
        try:
            event_date = datetime.strptime(date_value, '%Y-%m-%d').date()
            start_time = datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None
            end_time = datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None
        except ValueError:
            return jsonify({'error': 'Use valid date and time values.'}), 400
        event = CalendarEvent(
            event_title=title,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            event_description=(data.get('event_description') or '').strip(),
            notes=(data.get('notes') or '').strip(),
            company_id=user.company_id,
            project_id=project.project_id,
            created_by=user.id,
        )
        db.session.add(event)
        db.session.commit()
        return jsonify(calendar_event_payload(event)), 201

    project_id_value = request.args.get('project_id')
    try:
        project_id = int(project_id_value) if project_id_value is not None else None
    except ValueError:
        return jsonify({'error': 'A valid project ID is required.'}), 400
    if project_id is not None:
        project = Project.query.filter_by(
            project_id=project_id,
            company_id=user.company_id,
        ).first()
        if not project:
            return jsonify({'error': 'Project not found.'}), 404

    event_query = CalendarEvent.query.filter_by(company_id=user.company_id)
    if project_id is not None:
        event_query = event_query.filter(CalendarEvent.project_id == project_id)
    events = [
        calendar_event_payload(event)
        for event in event_query.order_by(CalendarEvent.event_date, CalendarEvent.start_time).all()
    ]
    meeting_query = Meeting.query.join(Project).filter(
        Project.company_id == user.company_id,
        Meeting.meeting_date.isnot(None),
    )
    if project_id is not None:
        meeting_query = meeting_query.filter(Meeting.project_id == project_id)
    meetings = [
        calendar_event_payload(meeting, source='meeting')
        for meeting in meeting_query.order_by(Meeting.meeting_date, Meeting.meeting_start_time).all()
    ]
    project_query = Project.query.filter(
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Project.Project_Status.notin_(PAST_PROJECT_STATUSES),
    )
    if project_id is not None:
        project_query = project_query.filter(Project.project_id == project_id)
    projects = [
        {'id': project.project_id, 'name': project.project_name}
        for project in project_query.order_by(Project.project_name).all()
    ]
    return jsonify({'events': events + meetings, 'projects': projects})


@views.route('/api/calendar-events/<int:event_id>', methods=['PUT'])
def update_calendar_event(event_id):
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    event = CalendarEvent.query.filter_by(event_id=event_id, company_id=user.company_id).first()
    if not event:
        return jsonify({'error': 'Calendar event not found.'}), 404
    data = request.get_json(silent=True) or request.form
    title = (data.get('title') or '').strip()
    date_value = (data.get('date') or '').strip()
    try:
        project_id = int(data.get('project_id'))
        event_date = datetime.strptime(date_value, '%Y-%m-%d').date()
        start_time = datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None
        end_time = datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Use valid title, project, date, and time values.'}), 400
    project = Project.query.filter(
        Project.project_id == project_id,
        Project.company_id == user.company_id,
        Project.deleted_at.is_(None),
        Project.Project_Status.notin_(PAST_PROJECT_STATUSES),
    ).first()
    if not title or not project:
        return jsonify({'error': 'Title and a company project are required.'}), 400
    event.event_title = title
    event.event_date = event_date
    event.start_time = start_time
    event.end_time = end_time
    event.event_description = (data.get('event_description') or '').strip()
    event.notes = (data.get('notes') or '').strip()
    event.project_id = project.project_id
    db.session.commit()
    return jsonify(calendar_event_payload(event))


@views.route('/api/calendar-events/<int:event_id>', methods=['DELETE'])
def delete_calendar_event(event_id):
    user = get_logged_in_user()
    if not user:
        return jsonify({'error': 'login_required'}), 401
    event = CalendarEvent.query.filter_by(event_id=event_id, company_id=user.company_id).first()
    if not event:
        return jsonify({'error': 'Calendar event not found.'}), 404
    db.session.delete(event)
    db.session.commit()
    return jsonify({'deleted': event_id})


@views.route('/project/<int:project_id>/update', methods=['POST'])
def update_project_page(project_id):
    user = get_logged_in_user()
    if not user:
        return redirect(url_for('auth.login'))
    project = Project.query.filter_by(
        project_id=project_id,
        company_id=user.company_id,
        deleted_at=None,
    ).first()
    if not project:
        return redirect(url_for('views.home'))
    try:
        clients = resolve_project_stakeholders(
            request.form, user.company_id, 'client', Client, 'existing_client_id',
            'client_name', 'client_reg_no', 'client_email', 'client_phone_number', 'client_address',
        )
        if len(clients) > 1:
            raise ValueError('A project can have only one client.')
        contractors = resolve_project_stakeholders(
            request.form, user.company_id, 'sub contractor/vendor', Contractor, 'existing_contractor_id',
            'contractor_name', 'contractor_reg_no', 'contractor_email', 'contractor_phone_number', 'contractor_address',
        )
        if not contractors:
            raise ValueError('A project must have at least one sub contractor/vendor.')
        consultants = resolve_project_stakeholders(
            request.form, user.company_id, 'consultant', Consultant, 'existing_consultant_id',
            'consultant_name', 'consultant_reg_no', 'consultant_email', 'consultant_phone_number', 'consultant_address',
        )
        if len(consultants) > 1:
            raise ValueError('A project can have only one consultant.')
    except ValueError as error:
        flash(str(error), category='error')
        return redirect(url_for('views.project_details', project_name=project.project_name))

    previous_values = {
        'project name': project.project_name,
        'project site / location': project.project_site or '',
        'description': project.description or '',
        'purchase order / contract date': project.PurchaseOrder_date.isoformat() if project.PurchaseOrder_date else '',
        'status': project.Project_Status or '',
        'client': project.client.client_name if project.client else '',
        'sub contractor / vendor': ', '.join(
            contractor.contractor_name
            for contractor in (project.contractors or ([project.contractor] if project.contractor else []))
        ),
        'consultant': project.consultant.consultant_name if project.consultant else '',
    }
    old_status = project.Project_Status
    project.project_name = request.form.get('name', project.project_name).strip()
    project.project_site = request.form.get('project_site', '').strip() or None
    project.description = request.form.get('description', '').strip()
    project.PurchaseOrder_date = datetime.strptime(request.form['purchase_order_date'], '%Y-%m-%d').date() if request.form.get('purchase_order_date') else None
    project.Project_Status = request.form.get('status', project.Project_Status or 'planning').strip()
    project.client = clients[0] if clients else None
    project.contractors = contractors
    project.contractor = contractors[0]
    project.consultant = consultants[0] if consultants else None
    for stakeholder in [*clients, *contractors, *consultants]:
        if stakeholder not in db.session:
            db.session.add(stakeholder)
    updated_values = {
        'project name': project.project_name,
        'project site / location': project.project_site or '',
        'description': project.description or '',
        'purchase order / contract date': project.PurchaseOrder_date.isoformat() if project.PurchaseOrder_date else '',
        'status': project.Project_Status or '',
        'client': project.client.client_name if project.client else '',
        'sub contractor / vendor': ', '.join(
            contractor.contractor_name
            for contractor in (project.contractors or ([project.contractor] if project.contractor else []))
        ),
        'consultant': project.consultant.consultant_name if project.consultant else '',
    }
    changed_fields = [
        field for field, old_value in previous_values.items()
        if old_value != updated_values[field]
    ]
    edited_at = datetime.now().astimezone()
    record_project_audit(
        user,
        'Project details edited',
        (
            f'User: {user.first_name} {user.last_name}; Company: {user.company.company_name}; '
            f'Project ID: {project_display_id(project)}; Project name: {project.project_name}; '
            f'Edited: {edited_at.strftime("%Y-%m-%d %H:%M:%S %Z")}; '
            f'Updated fields: {", ".join(changed_fields) if changed_fields else "No values changed"}.'
        ),
    )
    if project.Project_Status in PAST_PROJECT_STATUSES and old_status not in PAST_PROJECT_STATUSES:
        record_project_audit(
            user,
            'Project moved to Past projects archive',
            f'Project: {project_display_id(project)}, Name: {project.project_name}, Status: {project.Project_Status}.',
        )
    db.session.commit()
    flash('Project details saved.', category='success')
    return redirect(url_for('views.home', view='projects', project_id=project.project_id))


@views.route('/project/<int:project_id>/meetings', methods=['POST'])
def create_meeting_page(project_id):
    if not get_logged_in_user():
        return redirect(url_for('auth.login'))
    project = db.session.get(Project, project_id)
    if not project:
        return redirect(url_for('views.home'))
    meeting = Meeting(
        meeting_title=request.form.get('title', '').strip(),
        meeting_description=request.form.get('description', '').strip(),
        project_id=project.project_id,
    )
    if not meeting.meeting_title:
        flash('Meeting title is required.', category='error')
    else:
        db.session.add(meeting)
        db.session.commit()
        flash('Meeting saved.', category='success')
    return redirect(url_for('views.project_details', project_name=project.project_name))


@views.route('/api/projects/<int:project_id>/meetings', methods=['POST'])
def create_meeting(project_id):
    if not get_logged_in_user():
        return jsonify({'error': 'login_required'}), 401

    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found.'}), 404

    data = request.get_json(silent=True) or request.form
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Meeting title is required.'}), 400

    meeting = Meeting(
        meeting_title=title,
        meeting_description=(data.get('description') or '').strip(),
        project_id=project.project_id,
    )
    db.session.add(meeting)
    db.session.commit()
    return jsonify({'id': meeting.meeting_id, 'title': meeting.meeting_title}), 201