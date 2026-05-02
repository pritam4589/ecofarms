import os
import sqlite3
from datetime import datetime, timedelta
import app as eco

DB_PATH = os.path.join(os.getcwd(), "test_eco_farms.db")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

eco.DB = DB_PATH
eco.init_db()

eco.app.testing = True
client = eco.app.test_client()

# Helpers

def assert_contains(response, text):
    content = response.get_data(as_text=True)
    assert text in content, f"Expected '{text}' in response, got: {content[:300]}"

# 1. Public pages
resp = client.get('/login')
assert resp.status_code == 200
resp = client.get('/register')
assert resp.status_code == 200

# 2. Invalid login
resp = client.post('/login', data={'username': 'admin', 'password': 'wrong'}, follow_redirects=True)
assert resp.status_code == 200
assert_contains(resp, 'Invalid username or password')

# 3. Valid login
resp = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
assert resp.status_code == 200
assert_contains(resp, 'Welcome back, admin')
assert_contains(resp, 'Farm insights made simple')

with client:
    # Ensure dashboard is accessible after login
    resp = client.get('/')
    assert resp.status_code == 200

    # 4. Add farmer with invalid phone
    resp = client.post('/farmers/add', data={
        'name': 'Test Farmer',
        'email': 'test@example.com',
        'phone': '123',
        'address': 'Village Road',
        'id_number': 'ID12345',
    }, follow_redirects=True)
    assert_contains(resp, 'Please enter a valid phone number.')

    # 5. Add farmer with valid data
    resp = client.post('/farmers/add', data={
        'name': 'Test Farmer',
        'email': 'test@example.com',
        'phone': '+1234567890',
        'address': 'Village Road',
        'id_number': 'ID12345',
        'join_date': '2026-04-01'
    }, follow_redirects=True)
    assert_contains(resp, 'Farmer added successfully!')
    assert_contains(resp, 'Test Farmer')

    # Query farmer id
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    farmer = conn.execute("SELECT * FROM farmers WHERE name=?", ('Test Farmer',)).fetchone()
    assert farmer is not None
    farmer_id = farmer['id']

    # 6. Add farm for farmer
    resp = client.post('/farms/add', data={
        'farmer_id': farmer_id,
        'farm_name': 'Test Farm',
        'location': 'North Field',
        'area_acres': '5',
        'crop_type': 'Vegetables',
        'season': 'Spring',
        'start_date': '2026-04-10'
    }, follow_redirects=True)
    assert_contains(resp, 'Farm added!')
    farm = conn.execute("SELECT * FROM farms WHERE farm_name=?", ('Test Farm',)).fetchone()
    assert farm is not None
    farm_id = farm['id']

    # 7. Add supply before sowing
    resp = client.post(f'/farms/{farm_id}/supplies/add', data={
        'supply_name': 'Fertilizer',
        'supply_type': 'NPK',
        'quantity': '10',
        'unit': 'kg',
        'rate_per_unit': '20',
        'supply_date': '2026-04-15',
        'notes': 'Initial fertilizer'
    }, follow_redirects=True)
    assert_contains(resp, 'Supply recorded!')
    supply = conn.execute("SELECT * FROM supplies WHERE farm_id=? ORDER BY id DESC", (farm_id,)).fetchone()
    assert supply is not None
    assert abs(supply['total_cost'] - 200.0) < 1e-6
    assert supply['cost_deducted'] == 0

    # 8. Add seed for the farm
    resp = client.post(f'/farms/{farm_id}/seeds/add', data={
        'seed_name': 'Tomato',
        'variety': 'Cherry',
        'quantity_kg': '2',
        'sow_date': '2026-04-20',
        'notes': 'Good quality'
    }, follow_redirects=True)
    assert_contains(resp, 'Seed record added!')
    seed = conn.execute("SELECT * FROM seeds WHERE farm_id=? ORDER BY id DESC", (farm_id,)).fetchone()
    assert seed is not None

    # 9. Attempt harvest before sowing date
    resp = client.post(f'/farms/{farm_id}/harvest/add', data={
        'harvest_date': '2026-04-18',
        'total_output_kg': '15',
        'quality_grade': 'A',
        'rate_per_kg': '100',
        'notes': 'Early harvest'
    }, follow_redirects=True)
    assert_contains(resp, 'A harvest can only be recorded after seeds have been sown.')

    # 10. Add valid harvest and verify payment
    resp = client.post(f'/farms/{farm_id}/harvest/add', data={
        'harvest_date': '2026-04-20',
        'total_output_kg': '15',
        'quality_grade': 'A',
        'rate_per_kg': '100',
        'notes': 'Harvest ready'
    }, follow_redirects=True)
    assert_contains(resp, 'Harvest recorded! Net payment')
    payment = conn.execute("SELECT * FROM payments WHERE farm_id=? ORDER BY id DESC", (farm_id,)).fetchone()
    assert payment is not None
    assert payment['amount'] == 1300.0, f"Expected 1300.0, got {payment['amount']}"
    assert 'supplies' in payment['notes']
    assert payment['status'] == 'Pending'

    # 11. Pay the harvest payment and verify status
    pay_id = payment['id']
    resp = client.post(f'/payments/{pay_id}/pay', follow_redirects=True)
    assert_contains(resp, 'Payment marked as Paid!')
    payment2 = conn.execute("SELECT * FROM payments WHERE id=?", (pay_id,)).fetchone()
    assert payment2['status'] == 'Paid'

    # 12. Visit farm detail and confirm records show
    resp = client.get(f'/farms/{farm_id}')
    assert_contains(resp, 'Test Farm')
    assert_contains(resp, 'Tomato')
    assert_contains(resp, 'Fertilizer')
    assert_contains(resp, '15 kg')
    assert_contains(resp, '₹1300.0')

    conn.close()

print('All workflow tests passed successfully.')
