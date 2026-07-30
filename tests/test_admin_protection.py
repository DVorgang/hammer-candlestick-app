import pytest
import os
import sys
from core import database

def test_admin_subscriber_check():
    # Admin email check
    admin_sub = {"email": "devin.vorgang@gmail.com", "is_admin": 1}
    assert database.is_admin_subscriber(admin_sub) is True

    # Regular subscriber check
    regular_sub = {"email": "user@example.com", "is_admin": 0}
    assert database.is_admin_subscriber(regular_sub) is False

    # Invalid input
    assert database.is_admin_subscriber(None) is False
    assert database.is_admin_subscriber({}) is False

def test_custom_admin_email_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@mycompany.com, ceo@mycompany.com")
    
    sub1 = {"email": "admin@mycompany.com", "is_admin": 0}
    sub2 = {"email": "ceo@mycompany.com", "is_admin": 0}
    sub3 = {"email": "other@mycompany.com", "is_admin": 0}

    assert database.is_admin_subscriber(sub1) is True
    assert database.is_admin_subscriber(sub2) is True
    assert database.is_admin_subscriber(sub3) is False
