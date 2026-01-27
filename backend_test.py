#!/usr/bin/env python3

import requests
import sys
import json
import base64
from datetime import datetime
from typing import Dict, Any

class ClinomicAPITester:
    def __init__(self, base_url="https://fullstack-automate.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.session = requests.Session()

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, data: Dict[str, Any] = None, headers: Dict[str, str] = None) -> tuple[bool, Dict[str, Any]]:
        """Run a single API test"""
        # Add request ID parameter for all requests
        separator = '&' if '?' in endpoint else '?'
        url = f"{self.base_url}/api/{endpoint}{separator}r=test_{self.tests_run}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = self.session.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {"message": "Success but no JSON response"}
            else:
                print(f"❌ FAILED - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "response": response.text[:200]
                })
                try:
                    return False, response.json()
                except:
                    return False, {"error": response.text}

        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            self.failed_tests.append({
                "test": name,
                "error": str(e)
            })
            return False, {"error": str(e)}

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_login_admin(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin"}
        )
        if success and 'access_token' in response:
            self.token = response['access_token']
            print(f"   Admin token obtained: {self.token[:20]}...")
            return True, response
        return False, {}

    def test_login_lab(self):
        """Test lab login"""
        success, response = self.run_test(
            "Lab Login",
            "POST",
            "auth/login",
            200,
            data={"username": "lab", "password": "lab"}
        )
        if success and 'access_token' in response:
            self.token = response['access_token']
            print(f"   Lab token obtained: {self.token[:20]}...")
            return True
        return False

    def test_invalid_login(self):
        """Test invalid login credentials"""
        return self.run_test(
            "Invalid Login",
            "POST",
            "auth/login",
            401,
            data={"username": "invalid", "password": "invalid"}
        )

    def test_analytics_summary(self):
        """Test analytics summary endpoint"""
        return self.run_test("Analytics Summary", "GET", "analytics/summary", 200)

    def test_analytics_labs(self):
        """Test analytics labs endpoint (admin only)"""
        return self.run_test("Analytics Labs", "GET", "analytics/labs", 200)

    def test_analytics_doctors(self):
        """Test analytics doctors endpoint"""
        return self.run_test("Analytics Doctors", "GET", "analytics/doctors", 200)

    def test_analytics_cases(self):
        """Test analytics cases endpoint"""
        return self.run_test("Analytics Cases", "GET", "analytics/cases", 200)

    def test_pdf_upload(self):
        """Test PDF upload endpoint (mocked)"""
        # Create a dummy file for testing
        files = {'file': ('test.pdf', b'dummy pdf content', 'application/pdf')}
        url = f"{self.base_url}/api/lis/parse-pdf?r=test_{self.tests_run}"
        
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing PDF Upload...")
        print(f"   URL: {url}")
        
        try:
            response = self.session.post(url, files=files, headers=headers, timeout=30)
            success = response.status_code == 200
            
            if success:
                self.tests_passed += 1
                print(f"✅ PASSED - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {"message": "Success but no JSON response"}
            else:
                print(f"❌ FAILED - Expected 200, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.failed_tests.append({
                    "test": "PDF Upload",
                    "expected": 200,
                    "actual": response.status_code,
                    "response": response.text[:200]
                })
                return False, {"error": response.text}
                
        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            self.failed_tests.append({
                "test": "PDF Upload",
                "error": str(e)
            })
            return False, {"error": str(e)}

    def test_b12_screening(self):
        """Test B12 screening prediction"""
        screening_data = {
            "patientId": "TEST-001",
            "patientName": "Test Patient",
            "labId": "LAB-2024-001",
            "doctorId": "D201",
            "cbc": {
                "Hb_g_dL": 12.5,
                "RBC_million_uL": 4.2,
                "HCT_percent": 38.0,
                "MCV_fL": 85.0,
                "MCH_pg": 28.0,
                "MCHC_g_dL": 33.0,
                "RDW_percent": 13.5,
                "WBC_10_3_uL": 6.5,
                "Platelets_10_3_uL": 250.0,
                "Neutrophils_percent": 60.0,
                "Lymphocytes_percent": 30.0,
                "Age": 35,
                "Sex": "F"
            }
        }
        
        return self.run_test(
            "B12 Screening Prediction",
            "POST",
            "screening/predict",
            200,
            data=screening_data
        )

    def test_unauthorized_access(self):
        """Test unauthorized access without token"""
        old_token = self.token
        self.token = None
        
        success, _ = self.run_test(
            "Unauthorized Access",
            "GET",
            "analytics/summary",
            401
        )
        
        self.token = old_token
        return success

    def test_health_live(self):
        """Test health live endpoint"""
        return self.run_test("Health Live", "GET", "health/live", 200)

    def test_health_ready(self):
        """Test health ready endpoint"""
        return self.run_test("Health Ready", "GET", "health/ready", 200)

    def decode_jwt_payload(self, token):
        """Decode JWT payload to check claims"""
        try:
            # JWT has 3 parts separated by dots
            parts = token.split('.')
            if len(parts) != 3:
                return None
            
            # Decode the payload (second part)
            payload = parts[1]
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.b64decode(payload)
            return json.loads(decoded)
        except Exception as e:
            print(f"Error decoding JWT: {e}")
            return None

    def test_jwt_claims_admin(self):
        """Test JWT contains org_id and is_super_admin claims for admin"""
        success, response = self.run_test(
            "Admin Login for JWT Claims",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin"}
        )
        
        if success and 'access_token' in response:
            token = response['access_token']
            payload = self.decode_jwt_payload(token)
            
            if payload:
                print(f"   JWT Payload: {json.dumps(payload, indent=2)}")
                
                # Check required claims
                has_org_id = 'org_id' in payload
                has_is_super_admin = 'is_super_admin' in payload
                is_super_admin_true = payload.get('is_super_admin') == True
                
                if has_org_id and has_is_super_admin and is_super_admin_true:
                    print(f"✅ JWT Claims Valid - org_id: {payload['org_id']}, is_super_admin: {payload['is_super_admin']}")
                    self.tests_passed += 1
                    return True
                else:
                    print(f"❌ JWT Claims Invalid - org_id: {has_org_id}, is_super_admin: {has_is_super_admin}, value: {payload.get('is_super_admin')}")
                    self.failed_tests.append({
                        "test": "JWT Claims Admin",
                        "error": f"Missing or invalid claims: org_id={has_org_id}, is_super_admin={has_is_super_admin}"
                    })
                    return False
            else:
                print("❌ Failed to decode JWT payload")
                self.failed_tests.append({
                    "test": "JWT Claims Admin",
                    "error": "Failed to decode JWT payload"
                })
                return False
        
        return False

    def test_jwt_claims_lab(self):
        """Test JWT contains org_id and is_super_admin claims for lab user"""
        success, response = self.run_test(
            "Lab Login for JWT Claims",
            "POST",
            "auth/login",
            200,
            data={"username": "lab", "password": "lab"}
        )
        
        if success and 'access_token' in response:
            token = response['access_token']
            payload = self.decode_jwt_payload(token)
            
            if payload:
                print(f"   JWT Payload: {json.dumps(payload, indent=2)}")
                
                # Check required claims
                has_org_id = 'org_id' in payload
                has_is_super_admin = 'is_super_admin' in payload
                is_super_admin_false = payload.get('is_super_admin') == False
                
                if has_org_id and has_is_super_admin and is_super_admin_false:
                    print(f"✅ JWT Claims Valid - org_id: {payload['org_id']}, is_super_admin: {payload['is_super_admin']}")
                    self.tests_passed += 1
                    return True
                else:
                    print(f"❌ JWT Claims Invalid - org_id: {has_org_id}, is_super_admin: {has_is_super_admin}, value: {payload.get('is_super_admin')}")
                    self.failed_tests.append({
                        "test": "JWT Claims Lab",
                        "error": f"Missing or invalid claims: org_id={has_org_id}, is_super_admin={has_is_super_admin}"
                    })
                    return False
            else:
                print("❌ Failed to decode JWT payload")
                self.failed_tests.append({
                    "test": "JWT Claims Lab",
                    "error": "Failed to decode JWT payload"
                })
                return False
        
        return False

    def test_org_isolation_screening(self):
        """Test org isolation by creating screening under LAB-2024-001 and checking data isolation"""
        # First login as lab user
        success, response = self.run_test(
            "Lab Login for Org Isolation",
            "POST",
            "auth/login",
            200,
            data={"username": "lab", "password": "lab"}
        )
        
        if not success:
            return False
            
        self.token = response['access_token']
        
        # Create a screening under LAB-2024-001
        screening_data = {
            "patientId": "ORG-TEST-001",
            "patientName": "Org Isolation Test Patient",
            "labId": "LAB-2024-001",
            "doctorId": "D201",
            "cbc": {
                "Hb_g_dL": 11.5,
                "RBC_million_uL": 3.8,
                "HCT_percent": 35.0,
                "MCV_fL": 95.0,
                "MCH_pg": 30.0,
                "MCHC_g_dL": 32.0,
                "RDW_percent": 15.5,
                "WBC_10_3_uL": 5.5,
                "Platelets_10_3_uL": 200.0,
                "Neutrophils_percent": 65.0,
                "Lymphocytes_percent": 25.0,
                "Age": 45,
                "Sex": "M"
            }
        }
        
        success, screening_response = self.run_test(
            "Create Screening for Org Isolation",
            "POST",
            "screening/predict",
            200,
            data=screening_data
        )
        
        if not success:
            return False
            
        # Now check that lab user can see their analytics
        success, analytics_response = self.run_test(
            "Lab Analytics (Should See Own Data)",
            "GET",
            "analytics/summary",
            200
        )
        
        if success:
            print(f"✅ Lab user can access analytics - Total cases: {analytics_response.get('totalCases', 0)}")
            return True
        
        return False

    def test_admin_analytics_access(self):
        """Test admin can access all analytics endpoints"""
        # Login as admin
        success, response = self.run_test(
            "Admin Login for Analytics",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin"}
        )
        
        if not success:
            return False
            
        self.token = response['access_token']
        
        # Test all analytics endpoints
        endpoints = [
            ("analytics/summary", "Analytics Summary"),
            ("analytics/labs", "Analytics Labs"),
            ("analytics/doctors", "Analytics Doctors"),
            ("analytics/cases", "Analytics Cases")
        ]
        
        all_passed = True
        for endpoint, name in endpoints:
            success, response = self.run_test(f"Admin {name}", "GET", endpoint, 200)
            if not success:
                all_passed = False
            else:
                print(f"   {name} returned {len(response) if isinstance(response, list) else 'data'}")
        
        return all_passed

    def test_admin_screening_with_lab_mapping(self):
        """Test admin can create screening with labId and it maps to correct orgId"""
        # Login as admin
        success, response = self.run_test(
            "Admin Login for Lab Mapping",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin"}
        )
        
        if not success:
            return False
            
        self.token = response['access_token']
        
        # Create screening with specific labId
        screening_data = {
            "patientId": "ADMIN-LAB-MAP-001",
            "patientName": "Admin Lab Mapping Test",
            "labId": "LAB-2024-001",  # This should map to ORG-LAB-2024-001
            "doctorId": "D201",
            "cbc": {
                "Hb_g_dL": 10.5,
                "RBC_million_uL": 3.5,
                "HCT_percent": 32.0,
                "MCV_fL": 105.0,
                "MCH_pg": 32.0,
                "MCHC_g_dL": 31.0,
                "RDW_percent": 18.0,
                "WBC_10_3_uL": 4.0,
                "Platelets_10_3_uL": 180.0,
                "Neutrophils_percent": 70.0,
                "Lymphocytes_percent": 20.0,
                "Age": 55,
                "Sex": "F"
            }
        }
        
        success, screening_response = self.run_test(
            "Admin Create Screening with Lab Mapping",
            "POST",
            "screening/predict",
            200,
            data=screening_data
        )
        
        if success:
            print(f"✅ Admin successfully created screening with lab mapping")
            return True
        
        return False

    def test_login_returns_refresh_token(self):
        """Test that login returns both access_token and refresh_token"""
        success, response = self.run_test(
            "Login Returns Refresh Token",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin"}
        )
        
        if success:
            has_access = 'access_token' in response
            has_refresh = 'refresh_token' in response
            
            if has_access and has_refresh:
                print(f"✅ Login returns both tokens - access: {len(response['access_token'])} chars, refresh: {len(response['refresh_token'])} chars")
                return True, response
            else:
                print(f"❌ Missing tokens - access: {has_access}, refresh: {has_refresh}")
                self.failed_tests.append({
                    "test": "Login Returns Refresh Token",
                    "error": f"Missing tokens - access: {has_access}, refresh: {has_refresh}"
                })
                return False, {}
        
        return False, {}

    def test_access_token_on_protected_endpoint(self):
        """Test access token works on /api/auth/me and other protected endpoints"""
        # First get tokens
        success, response = self.test_login_returns_refresh_token()
        if not success:
            return False
            
        access_token = response['access_token']
        
        # Test /api/auth/me endpoint
        old_token = self.token
        self.token = access_token
        
        success, me_response = self.run_test(
            "Access Token on /auth/me",
            "GET",
            "auth/me",
            200
        )
        
        if success:
            print(f"✅ /auth/me returned: {me_response}")
            
            # Test another protected endpoint
            success2, analytics_response = self.run_test(
                "Access Token on Protected Analytics",
                "GET",
                "analytics/summary",
                200
            )
            
            self.token = old_token
            return success2
        
        self.token = old_token
        return False

    def test_refresh_token_rotation(self):
        """Test refresh token rotation: /api/auth/refresh returns new tokens and old token becomes revoked"""
        # First get initial tokens
        success, response = self.test_login_returns_refresh_token()
        if not success:
            return False
            
        initial_access = response['access_token']
        initial_refresh = response['refresh_token']
        
        print(f"   Initial refresh token: {initial_refresh[:20]}...")
        
        # Use refresh token to get new tokens
        success, refresh_response = self.run_test(
            "Refresh Token Rotation",
            "POST",
            "auth/refresh",
            200,
            data={"refresh_token": initial_refresh}
        )
        
        if success:
            new_access = refresh_response.get('access_token')
            new_refresh = refresh_response.get('refresh_token')
            
            if new_access and new_refresh:
                print(f"✅ Refresh returned new tokens")
                print(f"   New access token: {new_access[:20]}...")
                print(f"   New refresh token: {new_refresh[:20]}...")
                
                # Verify old refresh token is now revoked by trying to use it again
                success_old, old_response = self.run_test(
                    "Old Refresh Token Should Be Revoked",
                    "POST",
                    "auth/refresh",
                    401,  # Should fail
                    data={"refresh_token": initial_refresh}
                )
                
                if success_old:
                    print(f"✅ Old refresh token correctly revoked")
                    
                    # Verify new access token works
                    old_token = self.token
                    self.token = new_access
                    
                    success_new, me_response = self.run_test(
                        "New Access Token Works",
                        "GET",
                        "auth/me",
                        200
                    )
                    
                    self.token = old_token
                    return success_new
                else:
                    print(f"❌ Old refresh token was not revoked properly")
                    return False
            else:
                print(f"❌ Refresh response missing tokens")
                return False
        
        return False

    def test_logout_revokes_refresh_token(self):
        """Test logout revokes refresh token"""
        # First get tokens
        success, response = self.test_login_returns_refresh_token()
        if not success:
            return False
            
        refresh_token = response['refresh_token']
        
        # Logout
        success, logout_response = self.run_test(
            "Logout Revokes Refresh Token",
            "POST",
            "auth/logout",
            200,
            data={"refresh_token": refresh_token}
        )
        
        if success:
            print(f"✅ Logout successful: {logout_response}")
            
            # Try to use the refresh token after logout - should fail
            success_after, after_response = self.run_test(
                "Refresh Token After Logout Should Fail",
                "POST",
                "auth/refresh",
                401,  # Should fail
                data={"refresh_token": refresh_token}
            )
            
            if success_after:
                print(f"✅ Refresh token correctly revoked after logout")
                return True
            else:
                print(f"❌ Refresh token was not revoked after logout")
                return False
        
        return False

    def test_org_claims_in_jwt(self):
        """Test org claims are still present in JWT and org isolation unaffected"""
        # Test admin JWT claims
        success, response = self.run_test(
            "Admin Login for Org Claims",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin"}
        )
        
        if success:
            access_token = response['access_token']
            refresh_token = response['refresh_token']
            
            # Decode access token
            access_payload = self.decode_jwt_payload(access_token)
            refresh_payload = self.decode_jwt_payload(refresh_token)
            
            if access_payload and refresh_payload:
                # Check access token claims
                access_has_org = 'org_id' in access_payload
                access_has_super = 'is_super_admin' in access_payload
                
                # Check refresh token claims
                refresh_has_org = 'org_id' in refresh_payload
                refresh_has_super = 'is_super_admin' in refresh_payload
                
                print(f"   Access token org_id: {access_payload.get('org_id')}")
                print(f"   Access token is_super_admin: {access_payload.get('is_super_admin')}")
                print(f"   Refresh token org_id: {refresh_payload.get('org_id')}")
                print(f"   Refresh token is_super_admin: {refresh_payload.get('is_super_admin')}")
                
                if access_has_org and access_has_super and refresh_has_org and refresh_has_super:
                    print(f"✅ Both tokens contain org claims")
                    return True
                else:
                    print(f"❌ Missing org claims in tokens")
                    return False
            else:
                print(f"❌ Failed to decode token payloads")
                return False
        
        return False

    # ============================================================
    # MILESTONE 4 TESTS - Consent Management, Demo Data Seeding
    # ============================================================

    def test_milestone4_record_consent(self):
        """Test recording patient consent (Milestone 4)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        consent_data = {
            "patientId": "TEST-CONSENT-001",
            "patientName": "John Test Patient",
            "consentType": "verbal",
            "witnessName": "Lab Technician Smith"
        }
        
        success, response = self.run_test(
            "Record Patient Consent",
            "POST",
            "consent/record",
            200,
            data=consent_data
        )
        
        if success:
            required_fields = ['id', 'status']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ Consent Record contains all required fields:")
                print(f"   id: {response['id']}")
                print(f"   status: {response['status']}")
                return True, response
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ Consent Record missing fields: {missing}")
                self.failed_tests.append({
                    "test": "Record Patient Consent",
                    "error": f"Missing required fields: {missing}"
                })
                return False, {}
        
        return False, {}

    def test_milestone4_check_consent_status(self):
        """Test checking consent status (Milestone 4)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        # First record a consent to test against
        consent_success, consent_response = self.test_milestone4_record_consent()
        if not consent_success:
            print("❌ Failed to record consent for status test")
            return False
        
        success, response = self.run_test(
            "Check Consent Status",
            "GET",
            "consent/status/TEST-CONSENT-001",
            200
        )
        
        if success:
            required_fields = ['hasConsent']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields and response['hasConsent'] == True:
                print(f"✅ Consent Status contains all required fields:")
                print(f"   hasConsent: {response['hasConsent']}")
                if 'consentId' in response:
                    print(f"   consentId: {response['consentId']}")
                if 'consentType' in response:
                    print(f"   consentType: {response['consentType']}")
                return True
            else:
                print(f"❌ Consent Status invalid - hasConsent: {response.get('hasConsent')}")
                self.failed_tests.append({
                    "test": "Check Consent Status",
                    "error": f"Invalid consent status response: {response}"
                })
                return False
        
        return False

    def test_milestone4_seed_demo_data(self):
        """Test seeding demo data (Milestone 4)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "Seed Demo Data",
            "POST",
            "admin/demo/seed",
            200
        )
        
        if success:
            # Print the actual response to debug
            print(f"   Actual response: {response}")
            
            # Check if response has seeded counts (flexible field names)
            has_seeded_data = any(key in response for key in ['patients', 'screenings', 'doctors', 'labs', 'seeded'])
            
            if has_seeded_data:
                print(f"✅ Demo Data Seed successful:")
                for key, value in response.items():
                    print(f"   {key}: {value}")
                return True
            else:
                print(f"❌ Demo Data Seed response doesn't contain expected seeded counts")
                self.failed_tests.append({
                    "test": "Seed Demo Data",
                    "error": f"Response doesn't contain seeded counts: {response}"
                })
                return False
        
        return False

    def test_milestone4_verify_demo_labs(self):
        """Test verifying demo labs are seeded (Milestone 4)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "Verify Demo Labs Seeded",
            "GET",
            "analytics/labs",
            200
        )
        
        if success:
            if isinstance(response, list):
                demo_lab_ids = ["LAB-DEMO-001", "LAB-DEMO-002", "LAB-DEMO-003"]
                found_labs = [lab.get('id') for lab in response if lab.get('id') in demo_lab_ids]
                
                if len(found_labs) >= 3:
                    print(f"✅ Demo Labs verified - Found: {found_labs}")
                    return True
                else:
                    print(f"❌ Demo Labs not found - Expected: {demo_lab_ids}, Found: {found_labs}")
                    self.failed_tests.append({
                        "test": "Verify Demo Labs Seeded",
                        "error": f"Expected demo labs not found. Found: {found_labs}"
                    })
                    return False
            else:
                print(f"❌ Labs response is not a list: {type(response)}")
                self.failed_tests.append({
                    "test": "Verify Demo Labs Seeded",
                    "error": f"Response is not a list: {type(response)}"
                })
                return False
        
        return False

    def test_milestone4_verify_demo_doctors(self):
        """Test verifying demo doctors are seeded (Milestone 4)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "Verify Demo Doctors Seeded",
            "GET",
            "analytics/doctors",
            200
        )
        
        if success:
            if isinstance(response, list):
                demo_doctor_ids = ["DOC-DEMO-001", "DOC-DEMO-002", "DOC-DEMO-003", "DOC-DEMO-004", "DOC-DEMO-005"]
                found_doctors = [doc.get('id') for doc in response if doc.get('id') in demo_doctor_ids]
                
                if len(found_doctors) >= 3:
                    print(f"✅ Demo Doctors verified - Found: {found_doctors}")
                    return True
                else:
                    print(f"❌ Demo Doctors not found - Expected some of: {demo_doctor_ids}, Found: {found_doctors}")
                    self.failed_tests.append({
                        "test": "Verify Demo Doctors Seeded",
                        "error": f"Expected demo doctors not found. Found: {found_doctors}"
                    })
                    return False
            else:
                print(f"❌ Doctors response is not a list: {type(response)}")
                self.failed_tests.append({
                    "test": "Verify Demo Doctors Seeded",
                    "error": f"Response is not a list: {type(response)}"
                })
                return False
        
        return False

    def test_milestone4_verify_demo_cases(self):
        """Test verifying demo cases/screenings are seeded (Milestone 4)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "Verify Demo Cases Seeded",
            "GET",
            "analytics/cases",
            200
        )
        
        if success:
            if isinstance(response, list):
                demo_patient_ids = ["PAT-DEMO-001", "PAT-DEMO-002", "PAT-DEMO-003", "PAT-DEMO-004", "PAT-DEMO-005"]
                found_cases = [case.get('patientId') for case in response if case.get('patientId') in demo_patient_ids]
                
                if len(found_cases) >= 3:
                    print(f"✅ Demo Cases verified - Found cases for: {found_cases}")
                    return True
                else:
                    print(f"❌ Demo Cases not found - Expected some of: {demo_patient_ids}, Found: {found_cases}")
                    self.failed_tests.append({
                        "test": "Verify Demo Cases Seeded",
                        "error": f"Expected demo cases not found. Found: {found_cases}"
                    })
                    return False
            else:
                print(f"❌ Cases response is not a list: {type(response)}")
                self.failed_tests.append({
                    "test": "Verify Demo Cases Seeded",
                    "error": f"Response is not a list: {type(response)}"
                })
                return False
        
        return False

    # ============================================================
    # MILESTONE 3 TESTS - MFA, Immutable Audit, System Health
    # ============================================================

    def test_milestone3_login_with_mfa_fields(self):
        """Test login returns mfa_required field (Milestone 3)"""
        success, response = self.run_test(
            "Login with MFA Fields",
            "POST",
            "auth/login",
            200,
            data={"username": "admin", "password": "admin"}
        )
        
        if success:
            has_access_token = 'access_token' in response
            has_refresh_token = 'refresh_token' in response
            has_mfa_required = 'mfa_required' in response
            
            if has_access_token and has_refresh_token and has_mfa_required:
                print(f"✅ Login response contains MFA fields - mfa_required: {response['mfa_required']}")
                # Store token for subsequent tests
                self.token = response['access_token']
                return True, response
            else:
                print(f"❌ Missing MFA fields - access_token: {has_access_token}, refresh_token: {has_refresh_token}, mfa_required: {has_mfa_required}")
                self.failed_tests.append({
                    "test": "Login with MFA Fields",
                    "error": f"Missing fields in response: {list(response.keys())}"
                })
                return False, {}
        
        return False, {}

    def test_mfa_status(self):
        """Test MFA status endpoint (Milestone 3)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "MFA Status",
            "GET",
            "mfa/status",
            200
        )
        
        if success:
            required_fields = ['is_enabled', 'is_setup', 'backup_codes_remaining']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ MFA Status contains all required fields:")
                print(f"   is_enabled: {response['is_enabled']}")
                print(f"   is_setup: {response['is_setup']}")
                print(f"   backup_codes_remaining: {response['backup_codes_remaining']}")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ MFA Status missing fields: {missing}")
                self.failed_tests.append({
                    "test": "MFA Status",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_mfa_setup(self):
        """Test MFA setup endpoint (Milestone 3)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "MFA Setup",
            "POST",
            "mfa/setup",
            200,
            data={"email": "admin@test.com"}
        )
        
        if success:
            required_fields = ['provisioning_uri', 'backup_codes', 'message']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ MFA Setup contains all required fields:")
                print(f"   provisioning_uri: {response['provisioning_uri'][:50]}...")
                print(f"   backup_codes: {len(response['backup_codes'])} codes")
                print(f"   message: {response['message']}")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ MFA Setup missing fields: {missing}")
                self.failed_tests.append({
                    "test": "MFA Setup",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_immutable_audit_summary(self):
        """Test immutable audit summary endpoint (Milestone 3)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "Immutable Audit Summary",
            "GET",
            "admin/audit/v2/summary",
            200
        )
        
        if success:
            required_fields = ['totalEntries', 'chainIntegrity']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ Immutable Audit Summary contains all required fields:")
                print(f"   totalEntries: {response['totalEntries']}")
                print(f"   chainIntegrity: {response['chainIntegrity']}")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ Immutable Audit Summary missing fields: {missing}")
                self.failed_tests.append({
                    "test": "Immutable Audit Summary",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_immutable_audit_verify(self):
        """Test immutable audit verify endpoint (Milestone 3)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "Immutable Audit Verify",
            "GET",
            "admin/audit/v2/verify?limit=100",
            200
        )
        
        if success:
            required_fields = ['valid', 'totalVerified', 'issues']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ Immutable Audit Verify contains all required fields:")
                print(f"   valid: {response['valid']}")
                print(f"   totalVerified: {response['totalVerified']}")
                print(f"   issues: {len(response['issues'])} issues")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ Immutable Audit Verify missing fields: {missing}")
                self.failed_tests.append({
                    "test": "Immutable Audit Verify",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_system_config(self):
        """Test system config endpoint (Milestone 3)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "System Config",
            "GET",
            "admin/system/config",
            200
        )
        
        if success:
            required_fields = ['settings', 'secrets', 'model']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ System Config contains all required fields:")
                print(f"   settings: {type(response['settings'])}")
                print(f"   secrets: {type(response['secrets'])}")
                print(f"   model: {response['model']}")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ System Config missing fields: {missing}")
                self.failed_tests.append({
                    "test": "System Config",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_system_health(self):
        """Test system health endpoint (Milestone 3)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        success, response = self.run_test(
            "System Health",
            "GET",
            "admin/system/health",
            200
        )
        
        if success:
            required_fields = ['status', 'components']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ System Health contains all required fields:")
                print(f"   status: {response['status']}")
                print(f"   components: {list(response['components'].keys())}")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ System Health missing fields: {missing}")
                self.failed_tests.append({
                    "test": "System Health",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_b12_screening_milestone3(self):
        """Test B12 screening with audit logging (Milestone 3)"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_milestone3_login_with_mfa_fields()
            if not success:
                return False
        
        screening_data = {
            "patientId": "TEST-001",
            "patientName": "Test Patient",
            "cbc": {
                "Hb_g_dL": 12.5,
                "RBC_million_uL": 4.5,
                "HCT_percent": 38,
                "MCV_fL": 85,
                "MCH_pg": 28,
                "MCHC_g_dL": 33,
                "RDW_percent": 14,
                "WBC_10_3_uL": 7.5,
                "Platelets_10_3_uL": 250,
                "Neutrophils_percent": 60,
                "Lymphocytes_percent": 30,
                "Age": 45,
                "Sex": "M"
            }
        }
        
        success, response = self.run_test(
            "B12 Screening (Milestone 3)",
            "POST",
            "screening/predict",
            200,
            data=screening_data
        )
        
        if success:
            required_fields = ['riskClass', 'modelVersion']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ B12 Screening contains all required fields:")
                print(f"   riskClass: {response['riskClass']}")
                print(f"   modelVersion: {response['modelVersion']}")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ B12 Screening missing fields: {missing}")
                self.failed_tests.append({
                    "test": "B12 Screening (Milestone 3)",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_production_readiness_b12_screening(self):
        """Test B12 screening with exact sample data from review request"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_login_admin()
            if not success:
                return False
        
        screening_data = {
            "patientId": "TEST-PATIENT-001",
            "cbc": {
                "Hb_g_dL": 12.5,
                "RBC_million_uL": 4.5,
                "HCT_percent": 38,
                "MCV_fL": 85,
                "MCH_pg": 28,
                "MCHC_g_dL": 33,
                "RDW_percent": 13.5,
                "WBC_10_3_uL": 7.0,
                "Platelets_10_3_uL": 250,
                "Neutrophils_percent": 60,
                "Lymphocytes_percent": 30,
                "Age": 45,
                "Sex": "M"
            }
        }
        
        success, response = self.run_test(
            "B12 Screening (Production Readiness)",
            "POST",
            "screening/predict",
            200,
            data=screening_data
        )
        
        if success:
            required_fields = ['riskClass', 'label', 'probabilities', 'rulesFired', 'recommendation', 'modelVersion', 'indices']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields:
                print(f"✅ B12 Screening contains all required fields:")
                print(f"   riskClass: {response['riskClass']}")
                print(f"   label: {response['label']}")
                print(f"   probabilities: {response['probabilities']}")
                print(f"   modelVersion: {response['modelVersion']}")
                return True
            else:
                missing = [field for field in required_fields if field not in response]
                print(f"❌ B12 Screening missing fields: {missing}")
                self.failed_tests.append({
                    "test": "B12 Screening (Production Readiness)",
                    "error": f"Missing required fields: {missing}"
                })
                return False
        
        return False

    def test_production_readiness_consent_record(self):
        """Test consent record endpoint with production data"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_login_admin()
            if not success:
                return False
        
        consent_data = {
            "patientId": "TEST-PATIENT-001",
            "patientName": "John Smith",
            "consentType": "verbal",
            "witnessName": "Lab Technician"
        }
        
        success, response = self.run_test(
            "Consent Record (Production Readiness)",
            "POST",
            "consent/record",
            200,
            data=consent_data
        )
        
        if success:
            required_fields = ['id', 'status']
            has_all_fields = all(field in response for field in required_fields)
            
            if has_all_fields and response['status'] == 'recorded':
                print(f"✅ Consent Record successful:")
                print(f"   id: {response['id']}")
                print(f"   status: {response['status']}")
                return True, response
            else:
                print(f"❌ Consent Record invalid response: {response}")
                self.failed_tests.append({
                    "test": "Consent Record (Production Readiness)",
                    "error": f"Invalid response: {response}"
                })
                return False, {}
        
        return False, {}

    def test_production_readiness_consent_status(self):
        """Test consent status endpoint"""
        # Ensure we have a token
        if not self.token:
            success, _ = self.test_login_admin()
            if not success:
                return False
        
        # First record a consent
        consent_success, consent_response = self.test_production_readiness_consent_record()
        if not consent_success:
            print("❌ Failed to record consent for status test")
            return False
        
        success, response = self.run_test(
            "Consent Status (Production Readiness)",
            "GET",
            "consent/status/TEST-PATIENT-001",
            200
        )
        
        if success:
            if response.get('hasConsent') == True:
                print(f"✅ Consent Status successful:")
                print(f"   hasConsent: {response['hasConsent']}")
                if 'consentId' in response:
                    print(f"   consentId: {response['consentId']}")
                if 'consentType' in response:
                    print(f"   consentType: {response['consentType']}")
                return True
            else:
                print(f"❌ Consent Status invalid - hasConsent: {response.get('hasConsent')}")
                self.failed_tests.append({
                    "test": "Consent Status (Production Readiness)",
                    "error": f"Invalid consent status: {response}"
                })
                return False
        
        return False

def main():
    print("🧪 Starting Clinomic B12 Screening Platform Backend Tests")
    print("🎯 Testing: Production Readiness after Improvements")
    print("=" * 70)
    
    tester = ClinomicAPITester()
    
    # 1. Test Health Endpoints (as specified in review request)
    print("\n🏥 Testing Health Endpoints...")
    tester.test_health_live()
    tester.test_health_ready()
    
    # 2. Test Authentication with admin/admin credentials
    print("\n🔐 Testing Authentication (admin/admin)...")
    success, login_response = tester.test_login_admin()
    
    if success:
        print(f"✅ Admin login successful - Token obtained")
        
        # Verify token is returned
        if 'access_token' in login_response:
            print(f"   Access token: {login_response['access_token'][:20]}...")
        
        # 3. Test Core B12 Screening Prediction (with sample CBC data)
        print("\n🧬 Testing Core B12 Screening Prediction...")
        tester.test_production_readiness_b12_screening()
        
        # 4. Test Consent Endpoints (requires auth)
        print("\n📝 Testing Consent Endpoints...")
        tester.test_production_readiness_consent_record()
        tester.test_production_readiness_consent_status()
        
        # 5. Test Analytics Endpoints (requires admin role)
        print("\n📊 Testing Analytics Endpoints...")
        tester.test_analytics_summary()
        tester.test_analytics_labs()
        tester.test_analytics_doctors()
    else:
        print("❌ Admin login failed - Cannot proceed with authenticated tests")
    
    # Test invalid credentials
    print("\n🚫 Testing Invalid Credentials...")
    tester.test_invalid_login()
    
    # Test unauthorized access
    print("\n🔒 Testing Unauthorized Access...")
    tester.test_unauthorized_access()
    
    # Print results
    print("\n" + "=" * 70)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} passed")
    
    if tester.failed_tests:
        print("\n❌ Failed Tests:")
        for failure in tester.failed_tests:
            print(f"   - {failure.get('test', 'Unknown')}: {failure.get('error', failure.get('response', 'Unknown error'))}")
    
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"\n🎯 Success Rate: {success_rate:.1f}%")
    
    # Determine overall result
    if tester.tests_run == 0:
        print("\n⚠️  No tests were run")
        return 1
    elif tester.tests_passed == tester.tests_run:
        print("\n🎉 All tests passed! Backend is ready for production.")
        return 0
    else:
        print(f"\n⚠️  {tester.tests_run - tester.tests_passed} test(s) failed. Review issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())