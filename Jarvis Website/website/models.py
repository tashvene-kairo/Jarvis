from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from sqlalchemy import Enum 



class Company(db.Model):
    company_id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), unique=True, nullable=False)
    company_reg_no = db.Column(db.String(100), unique=True, nullable=False)
    company_tax_no = db.Column(db.String(100))
    company_email = db.Column(db.String(150), unique=True)
    company_password_hash = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(150))
    company_phone_number = db.Column(db.String(20))
    website = db.Column(db.String(150))
    description = db.Column(db.Text)
    date_Issued = db.Column(db.DateTime(timezone=True), default=func.now()) 


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
     # Optional company-specific employee ID
    employee_id = db.Column(db.String(50), nullable=True)   
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)    
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='Employee') 
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default='true')
    phone_number = db.Column(db.String(20)) 

    company_id = db.Column(db.Integer, db.ForeignKey('company.company_id'), nullable=False) 
    company = db.relationship('Company', backref=db.backref('users', lazy=True))


class PasswordResetToken(db.Model):
    token_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    user = db.relationship('User', backref=db.backref('password_reset_tokens', lazy=True, cascade='all, delete-orphan'))


class Client(db.Model):
    client_id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(150), nullable=False)
    client_reg_no = db.Column(db.String(100), unique=True, nullable=False)
    client_address = db.Column(db.String(150))
    client_email = db.Column(db.String(150))    
    client_phone_number = db.Column(db.String(20))

    company_id = db.Column(db.Integer, db.ForeignKey('company.company_id'), nullable=False) 
    company = db.relationship('Company', backref=db.backref('clients', lazy=True))

class Contractor(db.Model):
    contractor_id = db.Column(db.Integer, primary_key=True)
    contractor_name = db.Column(db.String(150), nullable=False) 
    contractor_reg_no = db.Column(db.String(100), unique=True, nullable=False)
    contractor_address = db.Column(db.String(150))
    contractor_email = db.Column(db.String(150))    
    contractor_phone_number = db.Column(db.String(20))

    company_id = db.Column(db.Integer, db.ForeignKey('company.company_id'), nullable=False)
    company = db.relationship('Company', backref=db.backref('contractors', lazy=True))


class Consultant(db.Model):
    consultant_id = db.Column(db.Integer, primary_key=True)
    consultant_name = db.Column(db.String(150), nullable=False) 
    consultant_reg_no = db.Column(db.String(100), unique=True, nullable=False)
    consultant_address = db.Column(db.String(150))
    consultant_email = db.Column(db.String(150))    
    consultant_phone_number = db.Column(db.String(20))

    company_id = db.Column(db.Integer, db.ForeignKey('company.company_id'), nullable=False)
    company = db.relationship('Company', backref=db.backref('consultants', lazy=True))


project_contractor = db.Table(
    'project_contractor',
    db.Column('project_id', db.Integer, db.ForeignKey('project.project_id'), primary_key=True),
    db.Column('contractor_id', db.Integer, db.ForeignKey('contractor.contractor_id'), primary_key=True),
)

class Project(db.Model):
    project_id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(150), nullable=False)    
    project_site = db.Column(db.Text)
    description = db.Column(db.Text)
    PurchaseOrder_date = db.Column(db.Date)
    Issued_Date = db.Column(db.DateTime(timezone=True), default=func.now())
    Project_Status = db.Column(db.Enum('Active', 'Planning', 'Completed', 'Design','Cancelled', 'Deferred', name='project_status_enum'), default='Active', nullable=False)
    deleted_at = db.Column(db.DateTime(timezone=True), index=True)
   
    company_id = db.Column(db.Integer, db.ForeignKey('company.company_id'), nullable=False) 
    company = db.relationship('Company',backref=db.backref('projects', lazy=True))

    client_id = db.Column(db.Integer, db.ForeignKey('client.client_id'))
    client = db.relationship('Client', backref=db.backref('projects', lazy=True))

    contractor_id = db.Column(db.Integer, db.ForeignKey('contractor.contractor_id'))
    contractor = db.relationship('Contractor', backref=db.backref('projects', lazy=True))
    contractors = db.relationship('Contractor', secondary=project_contractor, backref=db.backref('linked_projects', lazy=True))

    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.consultant_id'))
    consultant = db.relationship('Consultant', backref=db.backref('projects', lazy=True))


class Meeting(db.Model):
    meeting_id = db.Column(db.Integer, primary_key=True)
    meeting_title = db.Column(db.String(150), nullable=False)
    meeting_date = db.Column(db.Date)
    meeting_start_time = db.Column(db.Time)
    meeting_end_time = db.Column(db.Time)
    location = db.Column(db.Text)
    meeting_type = db.Column(db.Enum('Weekly', 'Monthly', 'Quarterly', 'Annual', 'Technical', 'Site', 'Commercial', name='meeting_type_enum'), default='Technical', nullable=False)
    meeting_description = db.Column(db.Text)
    agenda = db.Column(db.Text)
    prepared_by = db.Column(db.String(150))
    chairperson = db.Column(db.String(150))
    participants = db.Column(db.Text)
    participant_company = db.Column(db.Text)
    date_Issued = db.Column(db.DateTime(timezone=True), default=func.now())
    rev_Date = db.Column(db.DateTime(timezone=True))    
    revision_No = db.Column(db.Integer, default=0)    
    deleted_at = db.Column(db.DateTime(timezone=True), index=True)
    deleted_with_project = db.Column(db.Boolean, nullable=False, default=False)
    revision_order = db.Column(db.Integer, nullable=False, default=0)

    project_id = db.Column(db.Integer, db.ForeignKey('project.project_id'), nullable=False) 
    project = db.relationship('Project', backref=db.backref('meetings', lazy=True, cascade='all, delete-orphan'))   


class CalendarEvent(db.Model):
    event_id = db.Column(db.Integer, primary_key=True)
    event_title = db.Column(db.String(150), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    event_description = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)

    company_id = db.Column(db.Integer, db.ForeignKey('company.company_id'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.project_id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company = db.relationship('Company', backref=db.backref('calendar_events', lazy=True, cascade='all, delete-orphan'))
    project = db.relationship('Project', backref=db.backref('calendar_events', lazy=True))
    creator = db.relationship('User', backref=db.backref('calendar_events', lazy=True))


class MeetingRevision(db.Model):
    revision_id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey('meeting.meeting_id'), nullable=False, index=True)
    revision_No = db.Column(db.Integer, nullable=False)
    rev_Date = db.Column(db.DateTime(timezone=True), nullable=False, default=func.now())
    snapshot = db.Column(db.JSON, nullable=False)
    deleted_at = db.Column(db.DateTime(timezone=True), index=True)
    deleted_with_project = db.Column(db.Boolean, nullable=False, default=False)
    revision_order = db.Column(db.Integer, nullable=False, default=0)

    meeting = db.relationship('Meeting', backref=db.backref('revision_history', lazy=True, cascade='all, delete-orphan'))
    
    
    
class MeetingSection(db.Model):
    section_id = db.Column(db.Integer, primary_key=True)
    section_date = db.Column(db.Date, nullable=False)
    section_title = db.Column(db.String(150), nullable=False)

    meeting_id = db.Column(db.Integer, db.ForeignKey('meeting.meeting_id'), nullable=False)
    meeting = db.relationship('Meeting', backref=db.backref('sections', lazy=True, cascade='all, delete-orphan'))

class MeetingTask(db.Model):
    task_id = db.Column(db.Integer, primary_key=True)
    task_title = db.Column(db.String(150), nullable=False)
    task_description = db.Column(db.Text)
    task_Status = db.Column(db.Enum('Open', 'FYI', 'Closed', 'Pending', 'Incomplete', 'In Progress', 'Cancelled', name='meetingtask_status_enum'),default='Open', nullable=False)   
    task_due_date = db.Column(db.Date)
    task_assigned_to = db.Column(db.String(150))
    task_priority = db.Column(db.Enum('High', 'Medium', 'Low', 'None', name='meetingtask_priority_enum'), default='None', nullable=False)
    task_notes = db.Column(db.Text)
    

    section_id = db.Column(db.Integer, db.ForeignKey('meeting_section.section_id'), nullable=False)
    section = db.relationship('MeetingSection', backref=db.backref('tasks', lazy=True, cascade='all, delete-orphan'))



class Task(db.Model):
    task_id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(150), nullable=False)   
    description = db.Column(db.Text)
    due_date = db.Column(db.Date)
    task_status = db.Column(db.Enum('Active', 'Delayed', 'Completed', 'In Progress', 'Cancelled', 'In Planning', name='task_status_enum'), default='Active', nullable=False)

    project_id = db.Column(db.Integer, db.ForeignKey('project.project_id'))
    project = db.relationship('Project', backref=db.backref('tasks', lazy=True))  
   
class AuditLog(db.Model):
    log_id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('audit_logs', lazy=True))
    company_id = db.Column(db.Integer, db.ForeignKey('company.company_id'), nullable=False)
    company = db.relationship('Company', backref=db.backref('audit_logs', lazy=True))

    class Followup(db.Model):
        followup_id = db.Column(db.Integer, primary_key=True)
        followup_title = db.Column(db.String(150), nullable=False)
        followup_description = db.Column(db.Text)
        followup_due_date = db.Column(db.Date)
        followup_status = db.Column(db.Enum('Open', 'Closed', 'In Progress', 'Pending', 'Cancelled', name='followup_status_enum'), default='Open', nullable=False)

        task_id = db.Column(db.Integer, db.ForeignKey('task.task_id'), nullable=False)
        task = db.relationship('Task', backref=db.backref('followups', lazy=True, cascade='all, delete-orphan'))