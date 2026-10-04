from datetime import datetime
from datetime import timedelta, timezone
from email.message import EmailMessage
import hashlib
import os
import secrets
import smtplib
import ssl

from dotenv import load_dotenv
from flask import Blueprint, current_app, jsonify, render_template, request, flash, redirect, url_for, session
from . import db
from .models import AuditLog, Company, PasswordResetToken, User
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

auth = Blueprint('auth', __name__)    


def send_password_reset_email(user, token):
    smtp_host = os.getenv('SMTP_HOST')
    smtp_from = os.getenv('SMTP_FROM')
    if not smtp_host or not smtp_from:
        raise RuntimeError('Password reset email is not configured.')

    base_url = os.getenv('APP_BASE_URL', request.url_root).rstrip('/')
    reset_url = f'{base_url}{url_for("auth.reset_password", token=token)}'
    message = EmailMessage()
    message['Subject'] = 'Reset your Jarvis password'
    message['From'] = smtp_from
    message['To'] = user.email
    message.set_content(
        f'Hello {user.first_name},\n\n'
        'Use this one-time link to reset your Jarvis password. It expires in 30 minutes.\n\n'
        f'{reset_url}\n\n'
        'If you did not request this reset, you can ignore this email.'
    )

    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_username = os.getenv('SMTP_USERNAME')
    smtp_password = os.getenv('SMTP_PASSWORD')
    use_tls = os.getenv('SMTP_USE_TLS', 'true').casefold() in {'1', 'true', 'yes'}
    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=20) as server:
            if smtp_username:
                server.login(smtp_username, smtp_password or '')
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if use_tls:
            server.starttls(context=context)
        if smtp_username:
            server.login(smtp_username, smtp_password or '')
        server.send_message(message)


def password_reset_token(token):
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    record = PasswordResetToken.query.filter_by(token_hash=token_hash, used_at=None).with_for_update().first()
    if not record:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None
    return record

@auth.route('/company-lookup')
def company_lookup():
    email = request.args.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({'company_name': '', 'company_reg_no': ''})

    company = db.session.get(Company, user.company_id)
    return jsonify({
        'company_name': company.company_name if company else '',
        'company_reg_no': company.company_reg_no if company else '',
    })

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        company_password = request.form.get('companyPassword', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if not user:
            flash('Invalid user or password, please try again', category='error')
        else:
            company = Company.query.get(user.company_id)
            if not company or not check_password_hash(company.company_password_hash, company_password):
                flash('Invalid company password. Please refer to your admin.', category='error')
            elif not user.is_active:
                flash('This account has been deactivated. Please contact your company administrator.', category='error')
            elif not check_password_hash(user.password_hash, password):
                flash('Invalid user or password, please try again', category='error')
            else:
                login_date = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
                user_name = f'{user.first_name} {user.last_name}'.strip()
                db.session.add(AuditLog(
                    action='User Logged In',
                    description=(
                        f'User: {user_name}, Email: {user.email}, Role: {user.role}, '
                        f'Company: {company.company_name}, Date: {login_date}'
                    ),
                    user_id=user.id,
                    company_id=company.company_id,
                ))
                db.session.commit()
                session['user_id'] = user.id
                flash('Successfully logged in!', category='success')
                return redirect(url_for('views.home'))

    return render_template('login.html', boolean=True)

@auth.route('/forgot-password')
def forgot_password():
    return render_template('forgot_password.html')


@auth.route('/forgot-password', methods=['POST'])
def request_password_reset():
    email = request.form.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first() if email else None

    if user and user.is_active and (user.role or '').casefold() != 'admin':
        return render_template('forgot_password.html', message='Please contact your administrator to reset your password.')

    if user and user.is_active and (user.role or '').casefold() == 'admin':
        if not os.getenv('SMTP_HOST') or not os.getenv('SMTP_FROM'):
            return render_template(
                'forgot_password.html',
                error='Password reset email is not configured yet. Please contact your system administrator.',
            ), 503
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).delete(synchronize_session=False)
        record = PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(token.encode('utf-8')).hexdigest(),
            expires_at=now + timedelta(minutes=30),
        )
        db.session.add(record)
        try:
            send_password_reset_email(user, token)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Unable to send password reset email')
            return render_template(
                'forgot_password.html',
                error='We could not send the reset email. Please try again later or contact your administrator.',
            ), 503

    return render_template('forgot_password.html', message='A password reset link has been sent to this email. Please check your inbox and spam folder. If you do not receive the email, please contact your administrator.')   


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    record = password_reset_token(token)
    if not record or not record.user.is_active or (record.user.role or '').casefold() != 'admin':
        return render_template('reset_password.html', invalid=True), 400

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if len(password) < 7:
            return render_template('reset_password.html', error='Password must be at least 7 characters.'), 400
        if password != confirm_password:
            return render_template('reset_password.html', error='The passwords do not match.'), 400

        now = datetime.now(timezone.utc)
        user = record.user
        user.password_hash = generate_password_hash(password)
        record.used_at = now
        db.session.add(AuditLog(
            action='User Password Reset',
            description=f'User: {user.first_name} {user.last_name}, Email: {user.email}, Role: {user.role}. Password reset using the emailed recovery link.',
            user_id=user.id,
            company_id=user.company_id,
        ))
        db.session.commit()
        flash('Your password has been reset. You can now log in.', category='success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html')

@auth.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', category='info')
    return redirect(url_for('auth.login'))

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        first_name = request.form.get('firstName', '').strip()
        company_name = request.form.get('companyName', '').strip()
        company_reg_no = request.form.get('companyRegNo', '').strip()
        company_tax_no = request.form.get('companyTaxNo', '').strip()
        password1 = request.form.get('password1', '')
        password2 = request.form.get('password2', '')
        company_password1 = request.form.get('companyPassword1', '')
        company_password2 = request.form.get('companyPassword2', '')

        existing_company = Company.query.filter_by(company_reg_no=company_reg_no).first()
        existing_user = User.query.filter_by(email=email).first()

        if existing_company:
            flash('Company already registered. Please log in.', category='error')
        elif existing_user:
            flash('Email already exists.', category='error')
        elif len(email) < 4:
            flash('Email must be greater than 4 characters.', category='error')
        elif len(first_name) < 2:
            flash('First name must be greater than 1 character.', category='error')
        elif not company_name:
            flash('Company name is required.', category='error')
        elif not company_reg_no:
            flash('Company registration number is required.', category='error')
        elif not company_tax_no:
            flash('Company tax number is required.', category='error')
        elif password1 != password2:
            flash('Passwords do not match.', category='error')
        elif len(password1) < 7:
            flash('Password must be at least 7 characters.', category='error')
        elif company_password1 != company_password2:
            flash('Company passwords do not match.', category='error')
        elif len(company_password1) < 7:
            flash('Company password must be at least 7 characters.', category='error')
        else:
            company = Company(
                company_name=company_name,
                company_reg_no=company_reg_no,
                company_tax_no=company_tax_no,
                company_password_hash=generate_password_hash(company_password1),
            )
            db.session.add(company)
            db.session.flush()

            new_user = User(
                email=email,
                first_name=first_name,
                last_name='',
                password_hash=generate_password_hash(password1),
                role='Admin',
                company_id=company.company_id,
            )
            db.session.add(new_user)
            db.session.flush()
            new_user_name = f'{new_user.first_name} {new_user.last_name}'.strip()
            db.session.add(AuditLog(
                action='Business Account Sign Up Successful',
                description=(
                    f'Account for company {company.company_name} created. '
                    f'User: {new_user_name}, Email: {new_user.email}, Role: {new_user.role}, '
                    f'Company: {company.company_name}'
                ),
                user_id=new_user.id,
                company_id=company.company_id,
            ))
            db.session.commit()
        
            flash('Account created successfully!', category='success')
            return redirect(url_for('auth.login'))
    return render_template('sign_up.html')