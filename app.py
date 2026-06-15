from flask import Flask, render_template, request, jsonify, session, send_file, Response
import sqlite3, hashlib, os, io, datetime, threading, json
from functools import wraps

app = Flask(__name__)
app.secret_key = 'nc_on_mattress_2024_secure'

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mattress.db')

# ───────────────────────────── DB helpers ─────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_pw(p):
    return hashlib.sha256(p.strip().encode()).hexdigest()

# ───────────────────────────── Auth decorators ─────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('role'):
            return jsonify({'error': 'Not logged in'}), 401
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return wrapper

# ───────────────────────────── DB init ─────────────────────────────

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            discount_value REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS price_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            product TEXT NOT NULL,
            size_code TEXT NOT NULL,
            size_metric TEXT NOT NULL,
            thickness TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(brand, product, size_code, thickness)
        );
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_no TEXT,
            packing_slip_no TEXT DEFAULT '',
            client_id INTEGER,
            client_name TEXT NOT NULL,
            despatch_date TEXT DEFAULT '',
            grand_total REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            created_by TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS bill_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            sno INTEGER,
            brand TEXT,
            product TEXT,
            size_code TEXT,
            size_metric TEXT,
            thickness TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0,
            discount_type TEXT DEFAULT 'amount',
            discount_value REAL DEFAULT 0,
            total_value REAL DEFAULT 0,
            FOREIGN KEY(bill_id) REFERENCES bills(id) ON DELETE CASCADE
        );
    ''')

    # Add created_by column if it doesn't exist (migration for existing DBs)
    try:
        conn.execute("ALTER TABLE bills ADD COLUMN created_by TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    c.execute("INSERT OR IGNORE INTO settings VALUES ('bill_counter', '1')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('company_name', 'My Company')")
    # Seed default users if none exist
    if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        c.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,?)",
                  ('admin', hash_pw('admin123'), 'admin'))
        c.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,?)",
                  ('user', hash_pw('user123'), 'user'))
    conn.commit()

    if c.execute("SELECT COUNT(*) FROM price_list").fetchone()[0] == 0:
        _seed_prices(c)
        conn.commit()

    conn.close()
    print("✔ Database ready.")

def _seed_prices(c):
    NC = [   # Napcat size_code → size_metric
        ('78 x 30','198 X 76 CM'), ('78 x 36','198 X 91 CM'), ('78 x 42','198 X 106 CM'),
        ('78 x 48','198 X 121 CM'),('78 x 54','198 X 137 CM'),('78 x 60','198 X 152 CM'),
        ('78 x 66','198 X 167 CM'),('78 x 72','198 X 182 CM'),
    ]
    ON = [   # Orthonap size_code → size_metric
        ('75 x 30','198 X 76 CM'), ('75 x 36','198 X 91 CM'), ('75 x 42','198 X 106 CM'),
        ('75 x 48','198 X 121 CM'),('75 x 54','198 X 137 CM'),('75 x 60','198 X 152 CM'),
        ('75 x 66','198 X 167 CM'),('75 x 72','198 X 182 CM'),
    ]

    napcat = {
        'Eco': {
            '3"':[3862,4635,5407,6180,6952,7725,8497,9270],
            '4"':[4651,5581,6512,7442,8372,9302,10232,11163],
            '5"':[5461,6553,7646,8738,9830,10922,12015,13107],
            '6"':[6273,7528,8783,10037,11292,12547,13801,15056],
        },
        'Eco Plus': {
            '3"':[5725,6870,8015,9160,10305,11450,12595,13740],
            '4"':[7098,8518,9938,11358,12777,14197,15617,17036],
            '5"':[8547,10257,11966,13676,15385,17095,18804,20514],
            '6"':[9998,11998,13998,15998,17997,19997,21997,23996],
        },
        'Toss': {
            '4"':[8104,9725,11346,12967,14588,16209,17830,19451],
            '5"':[9553,11464,13375,15285,17196,19107,21017,22928],
            '6"':[11002,13203,15403,17604,19804,22005,24205,26406],
            '8"':[13970,16764,19558,22352,25146,27940,30734,33528],
        },
        'Spinal Aligner': {
            '5"':[8360,10032,11704,13376,15049,16721,18393,20065],
            '6"':[9551,11461,13371,15281,17191,19101,21011,22921],
            '8"':[11998,14398,16798,19197,21597,23997,26396,28796],
        },
        'Snuggle': {
            '5"':[8826,10591,12356,14121,15886,17651,19416,21181],
            '6"':[10275,12329,14384,16439,18494,20549,22604,24659],
            '8"':[11795,14154,16513,18872,21231,23590,25949,28308],
        },
        'Hybrid Siesta': {
            '6"':[11657,13988,16320,18651,20983,23314,25645,27977],
            '8"':[14547,17457,20366,23276,26185,29094,32004,34913],
        },
        'Guardian': {
            '5"':[13163,15796,18428,21061,23694,26326,28959,31592],
            '6"':[14564,17477,20390,23303,26216,29129,32042,34955],
            '8"':[17482,20979,24475,27972,31468,34965,38461,41957],
            '10"':[20417,24501,28584,32667,36751,40834,44918,49001],
        },
        'Empress': {
            '6"':[15616,18739,21862,24985,28109,31232,34355,37478],
            '8"':[18654,22385,26116,29847,33578,37309,41040,44771],
            '10"':[21721,26066,30410,34754,39099,43443,47787,52131],
            '12"':[24791,29750,34708,39666,44624,49583,54541,59499],
        },
        'Empress Plus': {
            '6"':[19185,23021,26858,30695,34532,38369,42206,46043],
            '8"':[22223,26668,31112,35557,40001,44446,48891,53335],
            '10"':[25290,30348,35406,40464,45522,50580,55638,60696],
            '12"':[28360,34032,39704,45376,51048,56720,62392,68064],
        },
        'Legend': {
            '6"':[16391,19669,22948,26226,29504,32782,36061,39339],
            '8"':[19493,23392,27291,31189,35088,38986,42885,46784],
            '10"':[22637,27164,31691,36218,40746,45273,49800,54328],
            '12"':[25783,30939,36096,41252,46409,51565,56722,61878],
        },
        'Monarch': {
            '10"':[27529,33035,38541,44046,49552,55058,60564,66070],
            '12"':[30501,36601,42701,48801,54901,61001,67102,73202],
        },
        'Nirvana': {
            '6"':[35785,42942,50099,57256,64413,71570,78727,85884],
            '8"':[46751,56101,65451,74802,84152,93502,102852,112202],
        },
    }

    orthonap = {
        'Comfort': {
            '4"':[3406,4087,4768,5449,6130,6811,7493,8174],
            '5"':[4039,4847,5655,6463,7270,8078,8886,9694],
            '6"':[4743,5692,6640,7589,8538,9486,10435,11383],
            '8"':[6170,7404,8637,9871,11105,12339,13573,14807],
        },
        'Comfort Plus': {
            '4"':[4512,5414,6317,7219,8121,9024,9926,10829],
            '5"':[5330,6396,7462,8527,9593,10659,11725,12791],
            '6"':[6003,7204,8404,9605,10805,12006,13206,14407],
            '8"':[7452,8942,10433,11923,13413,14904,16394,17884],
        },
        'Signature': {
            '6"':[6548,7857,9167,10476,11786,13095,13297,15714],
            '8"':[6812,8174,9536,10899,12261,13623,14986,16348],
            '6" (EuroTop)':[6982,8378,9775,11171,12567,13964,15360,16757],
            '8" (EuroTop)':[7268,8721,10175,11628,13082,14536,15989,17443],
        },
        'Aurora': {
            '6"':[9190,11029,12867,14705,16543,18381,20219,22057],
            '8"':[10373,12447,14522,16596,18671,20746,22820,24895],
            '10"':[12832,15399,17965,20532,23098,25665,28231,30797],
            '12"':[15295,18353,21412,24471,27530,30589,33648,36707],
        },
        'Aurora Pro': {
            '6"':[10093,12112,14131,16150,18168,20187,22206,24224],
            '8"':[11286,13544,15801,18058,20315,22573,24830,27087],
            '10"':[13732,16478,19224,21971,24717,27463,30210,32956],
            '12"':[15964,19157,22350,25542,28735,31928,35121,38314],
        },
        'Italiano': {
            '6"':[24623,29548,34472,39397,44322,49246,54171,59095],
            '8"':[30307,36368,42429,48491,54552,60613,66675,72736],
        },
    }

    for brand, sizes, data in [('Napcat', NC, napcat), ('Orthonap', ON, orthonap)]:
        for product, thicknesses in data.items():
            for thickness, prices in thicknesses.items():
                for i, (sc, sm) in enumerate(sizes):
                    c.execute(
                        "INSERT OR IGNORE INTO price_list (brand,product,size_code,size_metric,thickness,price) VALUES (?,?,?,?,?,?)",
                        (brand, product, sc, sm, thickness, prices[i])
                    )

    # Placeholder rows for Aura Cloud & Nova Plus (prices TBD)
    for product in ['Aura Cloud', 'Nova Plus']:
        for sc, sm in ON:
            c.execute(
                "INSERT OR IGNORE INTO price_list (brand,product,size_code,size_metric,thickness,price) VALUES (?,?,?,?,?,?)",
                ('Orthonap', product, sc, sm, 'TBD', 0)
            )

# ───────────────────────────── Auth routes ─────────────────────────────

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    pw       = data.get('password', '')
    conn     = get_db()
    row      = conn.execute(
        "SELECT role, password_hash FROM users WHERE username=?", (username,)
    ).fetchone()
    conn.close()
    if row and hash_pw(pw) == row['password_hash']:
        session['role']     = row['role']
        session['username'] = username
        return jsonify({'success': True, 'role': row['role'], 'username': username})
    return jsonify({'error': 'Incorrect username or password'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/me')
def me():
    return jsonify({'role': session.get('role'), 'username': session.get('username')})

# ───────────────────────────── User management routes ─────────────────────────────

@app.route('/api/users')
@admin_required
def list_users():
    conn = get_db()
    rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY role DESC, username").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data     = request.json or {}
    username = (data.get('username') or '').strip()
    pw       = data.get('password', '')
    role     = data.get('role', 'user')
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    if len(pw) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    if role not in ('admin', 'user'):
        return jsonify({'error': 'Role must be admin or user'}), 400
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
            (username, hash_pw(pw), role)
        )
        uid = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT id, username, role, created_at FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        return jsonify(dict(row))
    except Exception as e:
        conn.close()
        return jsonify({'error': f'Username already exists'}), 400

@app.route('/api/users/<int:uid>/password', methods=['PUT'])
@admin_required
def change_user_password(uid):
    data = request.json or {}
    pw   = data.get('password', '')
    if len(pw) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    conn = get_db()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pw(pw), uid))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@admin_required
def delete_user(uid):
    # Prevent deleting yourself
    conn = get_db()
    row  = conn.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    if row['username'] == session.get('username'):
        conn.close()
        return jsonify({'error': 'You cannot delete your own account'}), 400
    # Ensure at least one admin remains
    admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
    is_admin = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()['role'] == 'admin'
    if is_admin and admins <= 1:
        conn.close()
        return jsonify({'error': 'Cannot delete the last admin account'}), 400
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ───────────────────────────── Price list routes ─────────────────────────────

@app.route('/api/products')
@login_required
def get_products():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT brand, product FROM price_list ORDER BY brand, product").fetchall()
    conn.close()
    result = {}
    for r in rows:
        result.setdefault(r['brand'], [])
        if r['product'] not in result[r['brand']]:
            result[r['brand']].append(r['product'])
    return jsonify(result)

@app.route('/api/sizes')
@login_required
def get_sizes():
    brand   = request.args.get('brand', '')
    product = request.args.get('product', '')
    conn    = get_db()
    rows    = conn.execute(
        "SELECT DISTINCT size_code, size_metric FROM price_list WHERE brand=? AND product=? ORDER BY size_code",
        (brand, product)
    ).fetchall()
    conn.close()
    return jsonify([{'code': r['size_code'], 'metric': r['size_metric']} for r in rows])

@app.route('/api/thicknesses')
@login_required
def get_thicknesses():
    brand   = request.args.get('brand', '')
    product = request.args.get('product', '')
    sc      = request.args.get('size_code', '')
    conn    = get_db()
    rows    = conn.execute(
        "SELECT thickness, price FROM price_list WHERE brand=? AND product=? AND size_code=? ORDER BY thickness",
        (brand, product, sc)
    ).fetchall()
    conn.close()
    return jsonify([{'thickness': r['thickness'], 'price': r['price']} for r in rows])

@app.route('/api/price')
@login_required
def get_price():
    conn = get_db()
    row  = conn.execute(
        "SELECT price FROM price_list WHERE brand=? AND product=? AND size_code=? AND thickness=?",
        (request.args.get('brand'), request.args.get('product'),
         request.args.get('size_code'), request.args.get('thickness'))
    ).fetchone()
    conn.close()
    return jsonify({'price': row['price'] if row else 0})

@app.route('/api/pricelist')
@login_required
def get_pricelist():
    brand   = request.args.get('brand', '')
    product = request.args.get('product', '')
    q  = "SELECT * FROM price_list WHERE 1=1"
    ps = []
    if brand:   q += " AND brand=?";   ps.append(brand)
    if product: q += " AND product=?"; ps.append(product)
    q += " ORDER BY brand, product, size_code, thickness"
    conn = get_db()
    rows = conn.execute(q, ps).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/pricelist/<int:pid>', methods=['PUT'])
@admin_required
def update_price(pid):
    data = request.json or {}
    conn = get_db()
    conn.execute(
        "UPDATE price_list SET price=?, updated_at=datetime('now','localtime') WHERE id=?",
        (data.get('price', 0), pid)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/pricelist', methods=['POST'])
@admin_required
def add_price_entry():
    data = request.json or {}
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO price_list (brand,product,size_code,size_metric,thickness,price) VALUES (?,?,?,?,?,?)",
            (data['brand'], data['product'], data['size_code'], data['size_metric'], data['thickness'], data.get('price', 0))
        )
        conn.commit()
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM price_list WHERE id=?", (new_id,)).fetchone()
        conn.close()
        return jsonify(dict(row))
    except (sqlite3.IntegrityError, KeyError) as e:
        conn.close()
        return jsonify({'error': str(e)}), 400

@app.route('/api/pricelist/<int:pid>/full', methods=['PUT'])
@admin_required
def update_price_full(pid):
    """Update ALL details of a price entry (brand, product, size, thickness, price)."""
    data = request.json or {}
    conn = get_db()
    try:
        conn.execute(
            """UPDATE price_list SET brand=?, product=?, size_code=?, size_metric=?,
               thickness=?, price=?, updated_at=datetime('now','localtime') WHERE id=?""",
            (data['brand'], data['product'], data['size_code'], data['size_metric'],
             data['thickness'], data.get('price', 0), pid)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM price_list WHERE id=?", (pid,)).fetchone()
        conn.close()
        return jsonify(dict(row))
    except (sqlite3.IntegrityError, KeyError) as e:
        conn.close()
        return jsonify({'error': str(e)}), 400

@app.route('/api/pricelist/export')
@admin_required
def export_pricelist():
    """Download all prices as an Excel template (no Size Metric column)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    conn = get_db()
    rows = conn.execute(
        "SELECT brand, product, size_code, thickness, price FROM price_list "
        "ORDER BY brand, product, size_code, thickness"
    ).fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prices"

    headers = ['Brand', 'Product', 'Size Code', 'Thickness', 'Price']
    ws.append(headers)

    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for r in rows:
        ws.append([r['brand'], r['product'], r['size_code'], r['thickness'], r['price']])

    for col, w in zip('ABCDE', [16, 24, 14, 12, 12]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name='mattress_prices.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/api/pricelist/import', methods=['POST'])
@admin_required
def import_pricelist():
    """Full replace: wipe all prices and insert exactly what the Excel contains."""
    import openpyxl

    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file uploaded'}), 400
    try:
        wb = openpyxl.load_workbook(f, data_only=True)
    except Exception:
        return jsonify({'error': 'Could not read the file. Please upload a valid .xlsx Excel file.'}), 400

    ws = wb.active

    # Detect whether the file has the old 6-column format (with Size Metric) or new 5-column
    header = [str(ws.cell(1, c).value or '').strip().lower() for c in range(1, ws.max_column + 1)]
    has_size_metric = 'size metric' in header

    new_rows = []
    skipped  = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or all(c is None for c in row):
            continue

        if has_size_metric:
            cells = (list(row) + [None] * 6)[:6]
            brand, product, size_code, size_metric, thickness, price = cells
        else:
            cells = (list(row) + [None] * 5)[:5]
            brand, product, size_code, thickness, price = cells
            size_metric = ''

        if not (brand and product and size_code and thickness):
            skipped += 1
            continue

        brand       = str(brand).strip()
        product     = str(product).strip()
        size_code   = str(size_code).strip()
        size_metric = str(size_metric).strip() if size_metric else ''
        thickness   = str(thickness).strip()
        try:
            price = float(price) if price not in (None, '') else 0
        except (ValueError, TypeError):
            price = 0

        new_rows.append((brand, product, size_code, size_metric, thickness, price))

    if not new_rows:
        return jsonify({'error': 'No valid rows found in the file. Nothing was changed.'}), 400

    conn = get_db()
    conn.execute("DELETE FROM price_list")
    conn.executemany(
        "INSERT INTO price_list (brand,product,size_code,size_metric,thickness,price) VALUES (?,?,?,?,?,?)",
        new_rows
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'total': len(new_rows), 'skipped': skipped})

@app.route('/api/pricelist/<int:pid>', methods=['DELETE'])
@admin_required
def delete_price_entry(pid):
    conn = get_db()
    conn.execute("DELETE FROM price_list WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ───────────────────────────── Client routes ─────────────────────────────

@app.route('/api/clients')
@login_required
def get_clients():
    q  = request.args.get('q', '')
    conn = get_db()
    if q:
        rows = conn.execute("SELECT * FROM clients WHERE name LIKE ? ORDER BY name", (f'%{q}%',)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/clients', methods=['POST'])
@login_required
def add_client():
    data = request.json or {}
    conn = get_db()
    cur  = conn.execute(
        "INSERT INTO clients (name,phone,address,discount_value) VALUES (?,?,?,?)",
        (data['name'], data.get('phone',''), data.get('address',''), data.get('discount_value', 0))
    )
    cid  = cur.lastrowid
    conn.commit()
    row  = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    return jsonify(dict(row))

@app.route('/api/clients/<int:cid>', methods=['PUT'])
@login_required
def update_client(cid):
    data = request.json or {}
    conn = get_db()
    conn.execute(
        "UPDATE clients SET name=?,phone=?,address=?,discount_value=? WHERE id=?",
        (data['name'], data.get('phone',''), data.get('address',''), data.get('discount_value', 0), cid)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    return jsonify(dict(row))

@app.route('/api/clients/<int:cid>', methods=['DELETE'])
@admin_required
def delete_client(cid):
    conn = get_db()
    conn.execute("DELETE FROM clients WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ───────────────────────────── Bill routes ─────────────────────────────

@app.route('/api/bills')
@login_required
def get_bills():
    date_from = request.args.get('from', '')
    date_to   = request.args.get('to', '')
    client    = request.args.get('client', '')
    slip      = request.args.get('slip', '')
    q  = "SELECT * FROM bills WHERE 1=1"
    ps = []
    if date_from: q += " AND date(created_at)>=?"; ps.append(date_from)
    if date_to:   q += " AND date(created_at)<=?"; ps.append(date_to)
    if client:    q += " AND client_name LIKE ?";  ps.append(f'%{client}%')
    if slip:      q += " AND packing_slip_no LIKE ?"; ps.append(f'%{slip}%')
    q += " ORDER BY created_at DESC"
    conn = get_db()
    rows = conn.execute(q, ps).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/bills/<int:bid>')
@login_required
def get_bill(bid):
    conn  = get_db()
    bill  = conn.execute("SELECT * FROM bills WHERE id=?", (bid,)).fetchone()
    if not bill:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    items = conn.execute("SELECT * FROM bill_items WHERE bill_id=? ORDER BY sno", (bid,)).fetchall()
    conn.close()
    return jsonify({'bill': dict(bill), 'items': [dict(i) for i in items]})

@app.route('/api/bills', methods=['POST'])
@login_required
def create_bill():
    data = request.json or {}
    conn = get_db()

    counter  = conn.execute("SELECT value FROM settings WHERE key='bill_counter'").fetchone()['value']
    bill_no  = f"BILL-{int(counter):04d}"
    conn.execute("UPDATE settings SET value=? WHERE key='bill_counter'", (int(counter)+1,))

    created_by = session.get('username', '')
    cur = conn.execute(
        "INSERT INTO bills (bill_no,packing_slip_no,client_id,client_name,despatch_date,grand_total,created_by) VALUES (?,?,?,?,?,?,?)",
        (bill_no, data.get('packing_slip_no',''), data.get('client_id'),
         data['client_name'], data.get('despatch_date',''), data.get('grand_total', 0), created_by)
    )
    bid = cur.lastrowid

    for item in data.get('items', []):
        conn.execute(
            "INSERT INTO bill_items (bill_id,sno,brand,product,size_code,size_metric,thickness,quantity,unit_price,discount_type,discount_value,total_value) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (bid, item['sno'], item['brand'], item['product'], item['size_code'], item['size_metric'],
             item['thickness'], item['quantity'], item['unit_price'],
             item.get('discount_type','amount'), item.get('discount_value', 0), item['total_value'])
        )

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'bill_no': bill_no, 'id': bid})

@app.route('/api/bills/<int:bid>', methods=['DELETE'])
@admin_required
def delete_bill(bid):
    conn = get_db()
    conn.execute("DELETE FROM bills WHERE id=?", (bid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/bills/next_no')
@login_required
def next_bill_no():
    conn    = get_db()
    counter = conn.execute("SELECT value FROM settings WHERE key='bill_counter'").fetchone()['value']
    conn.close()
    return jsonify({'bill_no': f"BILL-{int(counter):04d}"})

@app.route('/api/backup')
@admin_required
def backup_db():
    date_str  = datetime.date.today().strftime('%Y-%m-%d')
    filename  = f'mattress_backup_{date_str}.db'
    with open(DB_PATH, 'rb') as f:
        data = f.read()
    return Response(
        data,
        mimetype='application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/print/bills')
@login_required
def print_bills():
    ids_str = request.args.get('ids', '')
    if not ids_str:
        return 'No bill IDs provided', 400
    try:
        ids = [int(i.strip()) for i in ids_str.split(',') if i.strip()]
    except ValueError:
        return 'Invalid bill IDs', 400

    conn = get_db()
    # Load company name
    company_row = conn.execute("SELECT value FROM settings WHERE key='company_name'").fetchone()
    company_name = company_row['value'] if company_row else 'My Company'

    bills_data = []
    for bid in ids:
        bill  = conn.execute("SELECT * FROM bills WHERE id=?", (bid,)).fetchone()
        if not bill:
            continue
        items = conn.execute("SELECT * FROM bill_items WHERE bill_id=? ORDER BY sno", (bid,)).fetchall()
        bills_data.append({'bill': dict(bill), 'bill_items': [dict(i) for i in items]})
    conn.close()

    return render_template('print_bills.html', bills=bills_data, company_name=company_name)

# ───────────────────────────── Google Drive backup ─────────────────────────────

GDRIVE_SCOPES       = ['https://www.googleapis.com/auth/drive.file']
GDRIVE_TOKEN_KEY    = 'gdrive_token'       # stored as JSON in settings
GDRIVE_CLIENT_KEY   = 'gdrive_client'      # stores {client_id, client_secret}
GDRIVE_FOLDER_KEY   = 'gdrive_folder_id'   # Google Drive folder ID (optional)

def _gdrive_flow(client_id, client_secret):
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        return None
    return Flow.from_client_config(
        {'web': {'client_id': client_id, 'client_secret': client_secret,
                 'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                 'token_uri': 'https://oauth2.googleapis.com/token',
                 'redirect_uris': ['http://localhost:5000/api/gdrive/callback']}},
        scopes=GDRIVE_SCOPES,
        redirect_uri='http://localhost:5000/api/gdrive/callback'
    )

def _gdrive_credentials():
    """Return valid Credentials or None."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GRequest
    except ImportError:
        return None
    conn = get_db()
    token_row  = conn.execute("SELECT value FROM settings WHERE key=?", (GDRIVE_TOKEN_KEY,)).fetchone()
    client_row = conn.execute("SELECT value FROM settings WHERE key=?", (GDRIVE_CLIENT_KEY,)).fetchone()
    conn.close()
    if not token_row or not client_row:
        return None
    token_data  = json.loads(token_row['value'])
    client_data = json.loads(client_row['value'])
    creds = Credentials(
        token=token_data.get('token'),
        refresh_token=token_data.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_data['client_id'],
        client_secret=client_data['client_secret'],
        scopes=GDRIVE_SCOPES,
    )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GRequest())
            _save_gdrive_token(creds)
        except Exception:
            return None
    return creds if creds.valid else None

def _save_gdrive_token(creds):
    token_data = json.dumps({
        'token': creds.token,
        'refresh_token': creds.refresh_token,
    })
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (GDRIVE_TOKEN_KEY, token_data))
    conn.commit()
    conn.close()

def _gdrive_upload_backup():
    """Upload today's backup to Google Drive. Called by background scheduler."""
    creds = _gdrive_credentials()
    if not creds:
        return False
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return False
    date_str = datetime.date.today().strftime('%Y-%m-%d')
    filename = f'mattress_backup_{date_str}.db'
    conn = get_db()
    folder_row = conn.execute("SELECT value FROM settings WHERE key=?", (GDRIVE_FOLDER_KEY,)).fetchone()
    conn.close()
    folder_id = folder_row['value'] if folder_row else None

    service  = build('drive', 'v3', credentials=creds)
    metadata = {'name': filename}
    if folder_id:
        metadata['parents'] = [folder_id]

    # Delete existing file with same name to avoid duplicates
    q = f"name='{filename}'"
    if folder_id:
        q += f" and '{folder_id}' in parents"
    existing = service.files().list(q=q, spaces='drive', fields='files(id)').execute()
    for f in existing.get('files', []):
        service.files().delete(fileId=f['id']).execute()

    media = MediaFileUpload(DB_PATH, mimetype='application/octet-stream')
    service.files().create(body=metadata, media_body=media, fields='id').execute()
    return True

def _schedule_daily_backup():
    """Run backup now, then re-schedule for next midnight."""
    _gdrive_upload_backup()
    now    = datetime.datetime.now()
    nxt    = (now + datetime.timedelta(days=1)).replace(hour=2, minute=0, second=0, microsecond=0)
    delay  = (nxt - now).total_seconds()
    t = threading.Timer(delay, _schedule_daily_backup)
    t.daemon = True
    t.start()

@app.route('/api/gdrive/status')
@admin_required
def gdrive_status():
    conn = get_db()
    has_client = conn.execute("SELECT 1 FROM settings WHERE key=?", (GDRIVE_CLIENT_KEY,)).fetchone()
    has_token  = conn.execute("SELECT 1 FROM settings WHERE key=?", (GDRIVE_TOKEN_KEY,)).fetchone()
    folder_row = conn.execute("SELECT value FROM settings WHERE key=?", (GDRIVE_FOLDER_KEY,)).fetchone()
    conn.close()
    return jsonify({
        'configured': bool(has_client),
        'connected':  bool(has_token),
        'folder_id':  folder_row['value'] if folder_row else '',
    })

@app.route('/api/gdrive/configure', methods=['POST'])
@admin_required
def gdrive_configure():
    data          = request.json or {}
    client_id     = (data.get('client_id') or '').strip()
    client_secret = (data.get('client_secret') or '').strip()
    folder_id     = (data.get('folder_id') or '').strip()
    if not client_id or not client_secret:
        return jsonify({'error': 'Client ID and Client Secret are required'}), 400
    client_data = json.dumps({'client_id': client_id, 'client_secret': client_secret})
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (GDRIVE_CLIENT_KEY, client_data))
    if folder_id:
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (GDRIVE_FOLDER_KEY, folder_id))
    # Clear any old token so user must re-authenticate
    conn.execute("DELETE FROM settings WHERE key=?", (GDRIVE_TOKEN_KEY,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/gdrive/connect')
@admin_required
def gdrive_connect():
    conn = get_db()
    client_row = conn.execute("SELECT value FROM settings WHERE key=?", (GDRIVE_CLIENT_KEY,)).fetchone()
    conn.close()
    if not client_row:
        return jsonify({'error': 'Configure Google credentials first'}), 400
    d    = json.loads(client_row['value'])
    flow = _gdrive_flow(d['client_id'], d['client_secret'])
    if not flow:
        return jsonify({'error': 'google-auth-oauthlib not installed'}), 500
    auth_url, _ = flow.authorization_url(access_type='offline', prompt='consent')
    return jsonify({'auth_url': auth_url})

@app.route('/api/gdrive/callback')
def gdrive_callback():
    conn = get_db()
    client_row = conn.execute("SELECT value FROM settings WHERE key=?", (GDRIVE_CLIENT_KEY,)).fetchone()
    conn.close()
    if not client_row:
        return 'Not configured', 400
    d    = json.loads(client_row['value'])
    flow = _gdrive_flow(d['client_id'], d['client_secret'])
    flow.fetch_token(authorization_response=request.url.replace('http://', 'https://').replace(':5000', ':5000'))
    _save_gdrive_token(flow.credentials)
    # Kick off the daily schedule
    threading.Thread(target=_schedule_daily_backup, daemon=True).start()
    return '''<html><body style="font-family:sans-serif;text-align:center;padding:60px;">
    <h2 style="color:#4f46e5;">✅ Google Drive connected!</h2>
    <p>Your database will be backed up to Google Drive automatically every day at 2 AM.</p>
    <p><a href="/" style="color:#4f46e5;">← Back to app</a></p></body></html>'''

@app.route('/api/gdrive/backup_now', methods=['POST'])
@admin_required
def gdrive_backup_now():
    ok = _gdrive_upload_backup()
    if ok:
        return jsonify({'success': True, 'message': 'Backup uploaded to Google Drive successfully'})
    return jsonify({'error': 'Backup failed. Check Google Drive connection.'}), 500

@app.route('/api/gdrive/disconnect', methods=['POST'])
@admin_required
def gdrive_disconnect():
    conn = get_db()
    conn.execute("DELETE FROM settings WHERE key IN (?,?,?)",
                 (GDRIVE_TOKEN_KEY, GDRIVE_CLIENT_KEY, GDRIVE_FOLDER_KEY))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ───────────────────────────── Settings routes ─────────────────────────────

@app.route('/api/settings')
@admin_required
def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key,value FROM settings WHERE key NOT IN ('admin_pw','user_pw')").fetchall()
    conn.close()
    return jsonify({r['key']: r['value'] for r in rows})

@app.route('/api/settings/company', methods=['PUT'])
@admin_required
def update_company():
    data = request.json or {}
    conn = get_db()
    conn.execute("UPDATE settings SET value=? WHERE key='company_name'", (data.get('name',''),))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ───────────────────────────── Main ─────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    init_db()
    # If Google Drive was already connected, start the daily backup scheduler
    if _gdrive_credentials():
        threading.Thread(target=_schedule_daily_backup, daemon=True).start()
        print("📦 Google Drive auto-backup scheduled (runs daily at 2 AM)")
    print("\n🛏  Mattress Price App running at http://localhost:5000")
    print("   For network access, use this computer's IP address on port 5000\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
