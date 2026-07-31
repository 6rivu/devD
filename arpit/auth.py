import streamlit as st
import hashlib
import secrets
from datetime import datetime
from database import get_user_data, create_user
import os

def hash_password(password):
    """Hash password with salt"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return salt + password_hash.hex()

def verify_password(password, stored_hash):
    """Verify password against stored hash"""
    salt = stored_hash[:32]
    stored_password_hash = stored_hash[32:]
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return password_hash.hex() == stored_password_hash

def authenticate_user(email, password, auth_provider):
    """Authenticate user with different providers"""
    if auth_provider == "email":
        return authenticate_email(email, password)
    elif auth_provider == "google":
        return authenticate_google()
    elif auth_provider == "linkedin":
        return authenticate_linkedin()
    return None

def authenticate_email(email, password):
    """Authenticate user with email and password (no auto-create)."""
    email = (email or "").strip().lower()
    user = get_user_data(email)
    if not user:
        return None  # no such user

    if user.get('auth_provider') != 'email':
        return None  # mismatch provider for this address

    # Block login until email is verified
    if not user.get('is_verified'):
        return None

    # Verify password
    stored = user.get('password_hash') or ""
    if stored and verify_password(password, stored):
        return user
    return None


def authenticate_google():
    """Authenticate user with Google (simplified implementation)"""
    # In a real implementation, you would use Google OAuth
    # For now, we'll simulate with a dynamic user based on time
    import time
    user_id = int(time.time()) % 1000  # Generate unique ID
    
    mock_user = {
        'email': f'user{user_id}@gmail.com',
        'name': f'Google User {user_id}',
        'auth_provider': 'google',
        'credits': 5,
        'total_cvs_generated': 0,
        'avg_ats_score': 0.0
    }
    
    user = get_user_data(mock_user['email'])
    if not user:
        create_user(mock_user['email'], mock_user['name'], 'google')
        user = get_user_data(mock_user['email'])
    
    return user

def authenticate_linkedin():
    """Authenticate user with LinkedIn (simplified implementation)"""
    # In a real implementation, you would use LinkedIn OAuth
    # For now, we'll simulate with a dynamic user based on time
    import time
    user_id = int(time.time()) % 1000  # Generate unique ID
    
    mock_user = {
        'email': f'user{user_id}@linkedin.com',
        'name': f'LinkedIn User {user_id}',
        'auth_provider': 'linkedin',
        'credits': 5,
        'total_cvs_generated': 0,
        'avg_ats_score': 0.0
    }
    
    user = get_user_data(mock_user['email'])
    if not user:
        create_user(mock_user['email'], mock_user['name'], 'linkedin')
        user = get_user_data(mock_user['email'])
    
    return user

def get_current_user():
    """Get current authenticated user from session"""
    if 'user_data' in st.session_state and st.session_state.user_data:
        return st.session_state.user_data
    return None

def logout_user():
    """Logout current user"""
    if 'user_data' in st.session_state:
        del st.session_state.user_data
    if 'cv_preview' in st.session_state:
        del st.session_state.cv_preview
    if 'auto_save' in st.session_state:
        del st.session_state.auto_save
