from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from os import path
import os
from dotenv import load_dotenv
import psycopg2
from datetime import datetime

db = SQLAlchemy()
def migrate_legacy_meetings():
    from .models import Meeting, MeetingRevision

    groups = {}
    for meeting in Meeting.query.order_by(Meeting.meeting_id).all():
        key = (meeting.project_id, meeting.meeting_title.strip().casefold())
        groups.setdefault(key, []).append(meeting)

    for meetings in groups.values():
        if len(meetings) < 2:
            continue
        root = meetings[0]
        ordered = sorted(meetings, key=lambda item: ((item.revision_No or 0), item.meeting_id))
        latest = ordered[-1]
        existing_revisions = {revision.revision_No for revision in root.revision_history}
        for item in ordered[:-1]:
            if item.revision_No in existing_revisions:
                continue
            db.session.add(MeetingRevision(
                meeting_id=root.meeting_id,
                revision_No=item.revision_No or 0,
                rev_Date=item.rev_Date or item.date_Issued or datetime.now().astimezone(),
                snapshot={
                    'meeting': [item.meeting_title, item.meeting_date.isoformat() if item.meeting_date else None, item.meeting_start_time.isoformat() if item.meeting_start_time else None, item.meeting_end_time.isoformat() if item.meeting_end_time else None, item.location or '', item.meeting_type or 'Technical', item.meeting_description or '', item.agenda or '', item.chairperson or '', item.participants or '', item.participant_company or ''],
                    'sections': [
                        [section.section_date.isoformat() if section.section_date else '', section.section_title or '', [[task.task_title or '', task.task_description or '', task.task_assigned_to or '', task.task_due_date.isoformat() if task.task_due_date else '', task.task_Status or 'Open', task.task_priority or 'None', task.task_notes or ''] for task in section.tasks]]
                        for section in item.sections
                    ],
                },
            ))

        if latest.meeting_id != root.meeting_id:
            root.meeting_title = latest.meeting_title
            root.meeting_date = latest.meeting_date
            root.meeting_start_time = latest.meeting_start_time
            root.meeting_end_time = latest.meeting_end_time
            root.location = latest.location
            root.meeting_type = latest.meeting_type
            root.meeting_description = latest.meeting_description
            root.agenda = latest.agenda
            root.prepared_by = latest.prepared_by
            root.chairperson = latest.chairperson
            root.participants = latest.participants
            root.participant_company = latest.participant_company
            root.rev_Date = latest.rev_Date
            root.revision_No = latest.revision_No
            root.sections.clear()
            db.session.flush()
            for source_section in latest.sections:
                target_section = source_section.__class__(
                    meeting_id=root.meeting_id,
                    section_date=source_section.section_date,
                    section_title=source_section.section_title,
                )
                db.session.add(target_section)
                db.session.flush()
                for source_task in source_section.tasks:
                    db.session.add(source_task.__class__(
                        section_id=target_section.section_id,
                        task_title=source_task.task_title,
                        task_description=source_task.task_description,
                        task_Status=source_task.task_Status,
                        task_due_date=source_task.task_due_date,
                        task_assigned_to=source_task.task_assigned_to,
                        task_priority=source_task.task_priority,
                        task_notes=source_task.task_notes,
                    ))
        for duplicate in meetings[1:]:
            if duplicate.meeting_id != root.meeting_id:
                db.session.delete(duplicate)
    db.session.commit()


def migrate_user_activation():
    inspector = inspect(db.engine)
    user_columns = {column['name'] for column in inspector.get_columns('user')}
    if 'is_active' not in user_columns:
        db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))
        db.session.commit()


def migrate_company_tax_no():
    inspector = inspect(db.engine)
    company_columns = {column['name'] for column in inspector.get_columns('company')}
    if 'company_tax_no' not in company_columns:
        db.session.execute(text('ALTER TABLE company ADD COLUMN company_tax_no VARCHAR(100)'))
        db.session.commit()


def migrate_project_site():
    inspector = inspect(db.engine)
    project_columns = {column['name'] for column in inspector.get_columns('project')}
    if 'project_site' not in project_columns:
        db.session.execute(text('ALTER TABLE project ADD COLUMN project_site TEXT'))
        db.session.commit()


def migrate_project_archive():
    project_columns = {column['name'] for column in inspect(db.engine).get_columns('project')}
    if 'deleted_at' not in project_columns:
        db.session.execute(text('ALTER TABLE project ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_project_deleted_at ON project (deleted_at)'))
    db.session.commit()


def migrate_meeting_archive():
    meeting_columns = {column['name'] for column in inspect(db.engine).get_columns('meeting')}
    if 'deleted_at' not in meeting_columns:
        db.session.execute(text('ALTER TABLE meeting ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE'))
    if 'deleted_with_project' not in meeting_columns:
        db.session.execute(text('ALTER TABLE meeting ADD COLUMN deleted_with_project BOOLEAN NOT NULL DEFAULT FALSE'))
    if 'revision_order' not in meeting_columns:
        db.session.execute(text('ALTER TABLE meeting ADD COLUMN revision_order INTEGER NOT NULL DEFAULT 0'))
    db.session.execute(text('UPDATE meeting SET revision_order = COALESCE("revision_No", 0) WHERE revision_order = 0'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_meeting_deleted_at ON meeting (deleted_at)'))
    db.session.commit()


def migrate_meeting_revision_archive():
    revision_columns = {column['name'] for column in inspect(db.engine).get_columns('meeting_revision')}
    if 'deleted_at' not in revision_columns:
        db.session.execute(text('ALTER TABLE meeting_revision ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE'))
    if 'deleted_with_project' not in revision_columns:
        db.session.execute(text('ALTER TABLE meeting_revision ADD COLUMN deleted_with_project BOOLEAN NOT NULL DEFAULT FALSE'))
    if 'revision_order' not in revision_columns:
        db.session.execute(text('ALTER TABLE meeting_revision ADD COLUMN revision_order INTEGER NOT NULL DEFAULT 0'))
    db.session.execute(text('UPDATE meeting_revision SET revision_order = "revision_No" WHERE revision_order = 0'))
    db.session.execute(text(
        'UPDATE meeting_revision SET deleted_at = meeting.deleted_at, deleted_with_project = TRUE '
        'FROM meeting WHERE meeting_revision.meeting_id = meeting.meeting_id '
        'AND meeting.deleted_at IS NOT NULL AND meeting.deleted_with_project = TRUE '
        'AND meeting_revision.deleted_at IS NULL'
    ))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_meeting_revision_deleted_at ON meeting_revision (deleted_at)'))
    db.session.commit()


def migrate_calendar_event_description():
    from .models import CalendarEvent

    event_columns = {column['name'] for column in inspect(db.engine).get_columns(CalendarEvent.__tablename__)}
    if 'event_description' not in event_columns:
        db.session.execute(text('ALTER TABLE calendar_event ADD COLUMN event_description TEXT'))
        db.session.commit()


def migrate_meeting_task_priority_none():
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text("ALTER TYPE meetingtask_priority_enum ADD VALUE IF NOT EXISTS 'None'"))
        db.session.commit()


# DB_NAME = "database.db"

load_dotenv()
def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    # app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')

    db.init_app(app)

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    from .models import (Company, User, PasswordResetToken, Client, Contractor, Consultant, Project, Meeting, CalendarEvent, MeetingRevision, MeetingSection, MeetingTask, Task, AuditLog)

    with app.app_context():
        db.create_all()
        migrate_user_activation()
        migrate_company_tax_no()
        migrate_project_site()
        migrate_project_archive()
        migrate_meeting_archive()
        migrate_meeting_revision_archive()
        migrate_calendar_event_description()
        migrate_meeting_task_priority_none()
        migrate_legacy_meetings()

    return app

    
