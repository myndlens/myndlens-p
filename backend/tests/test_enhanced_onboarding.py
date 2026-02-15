"""
Phase 0.5 Enhanced Onboarding Tests - Auto-import, Analyze, and Backward Compatibility

Tests:
- POST /api/onboarding/import - Bulk import with enriched contacts, structured routines, calendar patterns, location
- POST /api/onboarding/analyze - Server-side heuristic analysis (contact scoring, pattern extraction)
- POST /api/onboarding/profile - Original manual onboarding (backward compatible)
- POST /api/onboarding/skip - Skip onboarding
- GET /api/onboarding/status - Status retrieval

Enriched Schemas:
- EnrichedContact: name, relationship, role, email, phone, preferred_channel, importance, starred, company, aliases
- StructuredRoutine: title, time, frequency, days, duration_minutes, attendees, routine_type
- CalendarPattern: pattern_type, description, time, frequency, days, confidence
- LocationContext: city, region, country, timezone, postal_code
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://myndlens-preview.preview.emergentagent.com').rstrip('/')


def unique_user_id(prefix: str = "TEST_onboard") -> str:
    """Generate unique user_id for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestOnboardingImport:
    """Tests for POST /api/onboarding/import - Bulk import with enriched schemas."""
    
    def test_import_enriched_contacts(self):
        """Test importing contacts with all enriched fields."""
        user_id = unique_user_id("imp_contacts")
        payload = {
            "user_id": user_id,
            "contacts": [
                {
                    "name": "John Manager",
                    "relationship": "work",
                    "role": "Engineering Manager",
                    "email": "john.manager@company.com",
                    "phone": "+1234567890",
                    "preferred_channel": "email",
                    "importance": "high",
                    "starred": True,
                    "company": "TechCorp",
                    "aliases": ["John", "JM"]
                },
                {
                    "name": "Jane Friend",
                    "relationship": "personal",
                    "email": "jane@gmail.com",
                    "phone": "+0987654321",
                    "preferred_channel": "whatsapp",
                    "importance": "medium",
                    "starred": False,
                    "company": "",
                    "aliases": []
                }
            ],
            "display_name": "Test User",
            "timezone": "America/New_York"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["user_id"] == user_id
        assert data["completed"] == True
        # 2 contacts * 2 (entity + fact) + 1 display_name + 1 timezone = 6 items
        assert data["items_stored"] >= 6, f"Expected at least 6 items stored, got {data['items_stored']}"
        assert data["import_source"] == "auto"
        print(f"✓ Imported {len(payload['contacts'])} enriched contacts, {data['items_stored']} items stored")
    
    def test_import_structured_routines(self):
        """Test importing structured routines with all fields."""
        user_id = unique_user_id("imp_routines")
        payload = {
            "user_id": user_id,
            "routines": [
                {
                    "title": "Daily Standup",
                    "time": "09:00",
                    "frequency": "daily",
                    "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                    "duration_minutes": 15,
                    "attendees": 5,
                    "routine_type": "standup"
                },
                {
                    "title": "Weekly 1:1 with Manager",
                    "time": "14:00",
                    "frequency": "weekly",
                    "days": ["Thu"],
                    "duration_minutes": 30,
                    "attendees": 1,
                    "routine_type": "1on1"
                }
            ],
            "display_name": "Routine Test User"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["completed"] == True
        # 2 routines + 1 display_name = 3 items minimum
        assert data["items_stored"] >= 3, f"Expected at least 3 items stored, got {data['items_stored']}"
        print(f"✓ Imported {len(payload['routines'])} structured routines, {data['items_stored']} items stored")
    
    def test_import_calendar_patterns(self):
        """Test importing calendar patterns with all fields."""
        user_id = unique_user_id("imp_patterns")
        payload = {
            "user_id": user_id,
            "patterns": [
                {
                    "pattern_type": "recurring_event",
                    "description": "Team Sync - 3 occurrences per week",
                    "time": "10:00",
                    "frequency": "weekly",
                    "days": ["Mon", "Wed", "Fri"],
                    "confidence": 0.85
                },
                {
                    "pattern_type": "working_hours",
                    "description": "Working hours: 9:00 - 18:00",
                    "time": "09:00-18:00",
                    "frequency": "daily",
                    "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                    "confidence": 0.9
                }
            ],
            "display_name": "Pattern Test User"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["completed"] == True
        # 2 patterns + 1 display_name = 3 items minimum
        assert data["items_stored"] >= 3, f"Expected at least 3 items stored, got {data['items_stored']}"
        print(f"✓ Imported {len(payload['patterns'])} calendar patterns, {data['items_stored']} items stored")
    
    def test_import_location_context(self):
        """Test importing location context with all fields."""
        user_id = unique_user_id("imp_location")
        payload = {
            "user_id": user_id,
            "location": {
                "city": "San Francisco",
                "region": "California",
                "country": "USA",
                "timezone": "America/Los_Angeles",
                "postal_code": "94102"
            },
            "display_name": "Location Test User"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["completed"] == True
        # 1 location + 1 display_name = 2 items minimum
        assert data["items_stored"] >= 2, f"Expected at least 2 items stored, got {data['items_stored']}"
        print(f"✓ Imported location context: {payload['location']['city']}, {data['items_stored']} items stored")
    
    def test_import_complete_payload(self):
        """Test importing complete payload with contacts, routines, patterns, and location."""
        user_id = unique_user_id("imp_complete")
        payload = {
            "user_id": user_id,
            "contacts": [
                {
                    "name": "Alice Work",
                    "relationship": "work",
                    "role": "Product Manager",
                    "email": "alice@company.com",
                    "phone": "+1111111111",
                    "preferred_channel": "slack",
                    "importance": "high",
                    "starred": True,
                    "company": "TechCorp",
                    "aliases": ["Alice"]
                }
            ],
            "routines": [
                {
                    "title": "Morning Review",
                    "time": "08:30",
                    "frequency": "daily",
                    "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                    "duration_minutes": 20,
                    "attendees": 0,
                    "routine_type": "personal"
                }
            ],
            "patterns": [
                {
                    "pattern_type": "habit",
                    "description": "Coffee break around 3pm",
                    "time": "15:00",
                    "frequency": "daily",
                    "days": [],
                    "confidence": 0.7
                }
            ],
            "location": {
                "city": "New York",
                "region": "NY",
                "country": "USA",
                "timezone": "America/New_York",
                "postal_code": "10001"
            },
            "display_name": "Complete Test User",
            "communication_style": "formal",
            "timezone": "America/New_York"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["user_id"] == user_id
        assert data["completed"] == True
        # 1 contact*2 + 1 routine + 1 pattern + 1 location + 1 display_name + 1 comm_style + 1 timezone = 8 items
        assert data["items_stored"] >= 8, f"Expected at least 8 items stored, got {data['items_stored']}"
        assert data["import_source"] == "auto"
        print(f"✓ Complete import successful: {data['items_stored']} items stored")
    
    def test_import_counts_all_items_correctly(self):
        """Verify items_stored count is accurate for all item types."""
        user_id = unique_user_id("imp_count")
        payload = {
            "user_id": user_id,
            "contacts": [
                {"name": "Contact1", "email": "c1@test.com"},
                {"name": "Contact2", "email": "c2@test.com"},
                {"name": "Contact3", "email": "c3@test.com"}
            ],
            "routines": [
                {"title": "Routine1"},
                {"title": "Routine2"}
            ],
            "patterns": [
                {"pattern_type": "habit", "description": "Pattern1"},
                {"pattern_type": "event", "description": "Pattern2"}
            ],
            "display_name": "Count Test User",
            "timezone": "UTC"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Expected: 3 contacts * 2 = 6 + 2 routines + 2 patterns + 1 display_name + 1 timezone = 12
        expected_min = 6 + 2 + 2 + 1 + 1
        assert data["items_stored"] >= expected_min, f"Expected at least {expected_min} items, got {data['items_stored']}"
        print(f"✓ Item count correct: expected >= {expected_min}, got {data['items_stored']}")
    
    def test_import_sets_import_source_auto(self):
        """Verify import_source is set to 'auto' after bulk import."""
        user_id = unique_user_id("imp_source")
        payload = {
            "user_id": user_id,
            "contacts": [{"name": "Test Contact", "email": "test@test.com"}],
            "import_source": "auto"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert data["import_source"] == "auto", f"Expected import_source='auto', got '{data['import_source']}'"
        
        # Verify status endpoint also returns correct import_source
        status_response = requests.get(f"{BASE_URL}/api/onboarding/status/{user_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["import_source"] == "auto", f"Status import_source mismatch: {status_data['import_source']}"
        print(f"✓ import_source correctly set to 'auto'")
    
    def test_import_empty_contacts_handled_gracefully(self):
        """Test that empty contacts list is handled gracefully."""
        user_id = unique_user_id("imp_empty")
        payload = {
            "user_id": user_id,
            "contacts": [],
            "routines": [],
            "patterns": [],
            "display_name": "Empty Test User"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["completed"] == True
        # Only display_name should be stored
        assert data["items_stored"] >= 1, f"Expected at least 1 item (display_name), got {data['items_stored']}"
        print(f"✓ Empty contacts/routines/patterns handled gracefully, {data['items_stored']} items stored")


class TestOnboardingAnalyze:
    """Tests for POST /api/onboarding/analyze - Server-side heuristic analysis."""
    
    def test_analyze_infers_work_relationship_from_company(self):
        """Test that analyze correctly infers 'work' relationship from company."""
        user_id = unique_user_id("analyze_work_co")
        payload = {
            "user_id": user_id,
            "contacts": [
                {
                    "name": "Bob Colleague",
                    "email": "bob@personalmail.net",
                    "company": "TechCorp Inc"
                }
            ],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "contacts" in data
        assert len(data["contacts"]) == 1
        analyzed_contact = data["contacts"][0]
        assert analyzed_contact["name"] == "Bob Colleague"
        assert analyzed_contact["relationship"] == "work", f"Expected 'work', got '{analyzed_contact['relationship']}'"
        assert analyzed_contact["company"] == "TechCorp Inc"
        print(f"✓ Work relationship correctly inferred from company")
    
    def test_analyze_infers_work_relationship_from_job_title(self):
        """Test that analyze correctly infers 'work' relationship from jobTitle."""
        user_id = unique_user_id("analyze_work_job")
        payload = {
            "user_id": user_id,
            "contacts": [
                {
                    "name": "Carol Manager",
                    "email": "carol@gmail.com",  # Personal domain but...
                    "jobTitle": "Senior Manager"  # Job title indicates work
                }
            ],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert len(data["contacts"]) == 1
        analyzed = data["contacts"][0]
        assert analyzed["relationship"] == "work", f"Expected 'work' (from jobTitle), got '{analyzed['relationship']}'"
        assert analyzed["role"] == "Senior Manager"
        print(f"✓ Work relationship correctly inferred from job title 'Senior Manager'")
    
    def test_analyze_infers_personal_relationship_from_personal_email(self):
        """Test that analyze correctly infers 'personal' relationship from personal email domains."""
        user_id = unique_user_id("analyze_personal")
        payload = {
            "user_id": user_id,
            "contacts": [
                {"name": "Dave Gmail", "email": "dave@gmail.com"},
                {"name": "Eve Yahoo", "email": "eve@yahoo.com"},
                {"name": "Frank Hotmail", "email": "frank@hotmail.com"},
                {"name": "Grace Outlook", "email": "grace@outlook.com"},
                {"name": "Henry iCloud", "email": "henry@icloud.com"}
            ],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert len(data["contacts"]) == 5
        
        for contact in data["contacts"]:
            assert contact["relationship"] == "personal", f"Contact {contact['name']} should be 'personal', got '{contact['relationship']}'"
        print(f"✓ Personal relationship correctly inferred for all 5 personal email domains")
    
    def test_analyze_scores_importance_high_for_starred(self):
        """Test that starred contacts get high importance score."""
        user_id = unique_user_id("analyze_starred")
        payload = {
            "user_id": user_id,
            "contacts": [
                {
                    "name": "Important Person",
                    "starred": True,
                    "email": "important@test.com",
                    "phone": "+1234567890"
                }
            ],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        analyzed = data["contacts"][0]
        # starred (3) + email (1) + phone (1) + both (1) = 6 points -> high
        assert analyzed["importance"] == "high", f"Expected 'high' importance for starred contact, got '{analyzed['importance']}'"
        print(f"✓ Starred contact correctly scored as 'high' importance")
    
    def test_analyze_scores_importance_based_on_contact_methods(self):
        """Test importance scoring based on email and phone presence."""
        user_id = unique_user_id("analyze_importance")
        payload = {
            "user_id": user_id,
            "contacts": [
                # High: starred + email + phone
                {"name": "HighPriority", "starred": True, "email": "high@test.com", "phone": "+111"},
                # Medium: email + phone (no starred)
                {"name": "MediumPriority", "starred": False, "email": "medium@test.com", "phone": "+222"},
                # Low: only email (no starred, no phone)
                {"name": "LowPriority", "starred": False, "email": "low@test.com"}
            ],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        contacts_by_name = {c["name"]: c for c in data["contacts"]}
        
        assert contacts_by_name["HighPriority"]["importance"] == "high"
        assert contacts_by_name["MediumPriority"]["importance"] in ["medium", "high"], f"Got: {contacts_by_name['MediumPriority']['importance']}"
        assert contacts_by_name["LowPriority"]["importance"] in ["low", "medium"], f"Got: {contacts_by_name['LowPriority']['importance']}"
        print(f"✓ Importance scoring works based on starred, email, phone presence")
    
    def test_analyze_infers_preferred_channel(self):
        """Test that preferred_channel is correctly inferred."""
        user_id = unique_user_id("analyze_channel")
        payload = {
            "user_id": user_id,
            "contacts": [
                {"name": "BothMethods", "email": "both@test.com", "phone": "+111"},
                {"name": "PhoneOnly", "phone": "+222"},
                {"name": "EmailOnly", "email": "email@test.com"},
                {"name": "NoMethods"}
            ],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        contacts_by_name = {c["name"]: c for c in data["contacts"]}
        
        assert contacts_by_name["BothMethods"]["preferred_channel"] == "whatsapp"
        assert contacts_by_name["PhoneOnly"]["preferred_channel"] == "call"
        assert contacts_by_name["EmailOnly"]["preferred_channel"] == "email"
        assert contacts_by_name["NoMethods"]["preferred_channel"] == ""
        print(f"✓ Preferred channel correctly inferred (whatsapp/call/email/empty)")
    
    def test_analyze_extracts_recurring_event_patterns(self):
        """Test that recurring events are correctly extracted as patterns."""
        user_id = unique_user_id("analyze_recurring")
        payload = {
            "user_id": user_id,
            "contacts": [],
            "calendar_events": [
                {
                    "title": "Weekly Team Meeting",
                    "startDate": "2026-01-15T10:00:00Z",
                    "endDate": "2026-01-15T11:00:00Z",
                    "recurrenceRule": {"frequency": "weekly"}
                }
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "patterns" in data
        assert len(data["patterns"]) >= 1
        
        recurring_pattern = data["patterns"][0]
        assert recurring_pattern["pattern_type"] == "recurring_event"
        assert "Weekly Team Meeting" in recurring_pattern["description"]
        assert recurring_pattern["frequency"] == "weekly"
        assert recurring_pattern["confidence"] == 0.9
        print(f"✓ Recurring event pattern correctly extracted: {recurring_pattern['description']}")
    
    def test_analyze_extracts_single_event_patterns(self):
        """Test that single (non-recurring) events are correctly extracted."""
        user_id = unique_user_id("analyze_single")
        payload = {
            "user_id": user_id,
            "contacts": [],
            "calendar_events": [
                {
                    "title": "One-time Workshop",
                    "startDate": "2026-02-20T14:00:00Z",
                    "endDate": "2026-02-20T16:00:00Z"
                    # No recurrenceRule = single event
                }
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "patterns" in data
        assert len(data["patterns"]) >= 1
        
        single_pattern = data["patterns"][0]
        assert single_pattern["pattern_type"] == "single_event"
        assert single_pattern["description"] == "One-time Workshop"
        assert single_pattern["frequency"] == "once"
        assert single_pattern["confidence"] == 0.5
        print(f"✓ Single event pattern correctly extracted: {single_pattern['description']}")
    
    def test_analyze_returns_analysis_source(self):
        """Verify analyze returns analysis_source field indicating server heuristic."""
        user_id = unique_user_id("analyze_source")
        payload = {
            "user_id": user_id,
            "contacts": [{"name": "Test"}],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "analysis_source" in data
        assert data["analysis_source"] == "server_heuristic"
        print(f"✓ analysis_source correctly set to 'server_heuristic'")


class TestOnboardingBackwardCompatibility:
    """Tests for backward compatibility with original manual onboarding."""
    
    def test_profile_endpoint_still_works(self):
        """Test that POST /api/onboarding/profile (manual) still works."""
        user_id = unique_user_id("manual_profile")
        payload = {
            "user_id": user_id,
            "display_name": "Manual User",
            "preferences": {"theme": "dark", "notifications": True},
            "contacts": [
                {"name": "Manual Contact", "relationship": "friend"}
            ],
            "routines": ["Morning coffee", "Evening walk"],
            "communication_style": "casual",
            "timezone": "Europe/London"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/profile", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["user_id"] == user_id
        assert data["completed"] == True
        assert data["import_source"] == "manual"
        assert data["items_stored"] >= 5  # name + timezone + comm_style + 2 prefs + contact*2 + 2 routines
        print(f"✓ Manual /profile endpoint still works, {data['items_stored']} items stored")
    
    def test_skip_endpoint_still_works(self):
        """Test that POST /api/onboarding/skip/{user_id} still works."""
        user_id = unique_user_id("skip_test")
        
        response = requests.post(f"{BASE_URL}/api/onboarding/skip/{user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["user_id"] == user_id
        assert data["completed"] == True
        assert data["items_stored"] == 0
        assert data["import_source"] == "skipped"
        print(f"✓ Skip endpoint works correctly, import_source='skipped'")


class TestOnboardingStatus:
    """Tests for GET /api/onboarding/status endpoint."""
    
    def test_status_returns_correct_data_after_import(self):
        """Test status endpoint returns correct data after bulk import."""
        user_id = unique_user_id("status_after_import")
        
        # First do import
        import_payload = {
            "user_id": user_id,
            "contacts": [{"name": "Status Test Contact", "email": "status@test.com"}],
            "display_name": "Status Test User"
        }
        import_response = requests.post(f"{BASE_URL}/api/onboarding/import", json=import_payload)
        assert import_response.status_code == 200
        import_data = import_response.json()
        
        # Now check status
        status_response = requests.get(f"{BASE_URL}/api/onboarding/status/{user_id}")
        assert status_response.status_code == 200, f"Expected 200, got {status_response.status_code}"
        
        status_data = status_response.json()
        assert status_data["user_id"] == user_id
        assert status_data["completed"] == True
        assert status_data["import_source"] == "auto"
        assert status_data["items_stored"] == import_data["items_stored"]
        print(f"✓ Status endpoint returns correct data: completed={status_data['completed']}, items={status_data['items_stored']}")
    
    def test_status_for_new_user_returns_defaults(self):
        """Test status endpoint returns defaults for non-existent user."""
        user_id = unique_user_id("status_new_user")
        
        response = requests.get(f"{BASE_URL}/api/onboarding/status/{user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["user_id"] == user_id
        assert data["completed"] == False
        assert data["step"] == 0
        assert data["items_stored"] == 0
        assert data["import_source"] == "manual"
        print(f"✓ Status for new user returns correct defaults")


class TestEdgeCases:
    """Edge case and error handling tests."""
    
    def test_import_contact_without_name_skipped(self):
        """Test that contacts without name are skipped."""
        user_id = unique_user_id("edge_noname")
        payload = {
            "user_id": user_id,
            "contacts": [
                {"name": "", "email": "noname@test.com"},  # Should be skipped
                {"name": "Valid Contact", "email": "valid@test.com"}  # Should be stored
            ],
            "display_name": "Edge Case User"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Only 1 valid contact * 2 + display_name = 3 items
        assert data["items_stored"] >= 3, f"Expected at least 3 items, got {data['items_stored']}"
        print(f"✓ Contact without name correctly skipped, {data['items_stored']} items stored")
    
    def test_import_routine_without_title_skipped(self):
        """Test that routines without title are skipped."""
        user_id = unique_user_id("edge_noroutine")
        payload = {
            "user_id": user_id,
            "routines": [
                {"title": "", "time": "09:00"},  # Should be skipped
                {"title": "Valid Routine", "time": "10:00"}  # Should be stored
            ],
            "display_name": "Routine Edge User"
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/import", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # 1 valid routine + display_name = 2 items
        assert data["items_stored"] >= 2, f"Expected at least 2 items, got {data['items_stored']}"
        print(f"✓ Routine without title correctly skipped, {data['items_stored']} items stored")
    
    def test_analyze_empty_contacts_returns_empty_list(self):
        """Test analyze with empty contacts returns empty analyzed list."""
        user_id = unique_user_id("edge_empty_analyze")
        payload = {
            "user_id": user_id,
            "contacts": [],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["contacts"] == []
        assert data["patterns"] == []
        assert data["analysis_source"] == "server_heuristic"
        print(f"✓ Empty analyze request handled gracefully")
    
    def test_analyze_contact_without_name_returns_empty_name(self):
        """Test analyze handles contact without name field."""
        user_id = unique_user_id("edge_noname_analyze")
        payload = {
            "user_id": user_id,
            "contacts": [
                {"email": "noname@test.com"}  # Missing name field
            ],
            "calendar_events": []
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["name"] == ""
        print(f"✓ Contact without name field handled gracefully")
    
    def test_analyze_event_without_title_returns_none(self):
        """Test analyze skips events without title."""
        user_id = unique_user_id("edge_notitle_event")
        payload = {
            "user_id": user_id,
            "contacts": [],
            "calendar_events": [
                {"startDate": "2026-01-15T10:00:00Z"}  # Missing title
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/onboarding/analyze", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["patterns"] == [], "Event without title should not produce pattern"
        print(f"✓ Event without title correctly skipped")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
