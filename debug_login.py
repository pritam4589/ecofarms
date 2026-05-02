import os
import sqlite3
import pathlib
import app as eco

DB_PATH = os.path.join(os.getcwd(), 'test_eco_farms.db')
pathlib.Path(DB_PATH).unlink(missing_ok=True)
eco.DB = DB_PATH
eco.init_db()
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
admin = conn.execute('SELECT username, password_hash FROM users WHERE username=?', ('admin',)).fetchone()
print('admin', admin is not None)
if admin:
    print('hash', admin['password_hash'][:20])
conn.close()
client = eco.app.test_client()
resp = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
print('status', resp.status_code)
print(resp.get_data(as_text=True)[:1000])
