import io
import os
import uuid
import qrcode
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, session, send_file, jsonify
import mysql.connector
import razorpay
from flask_mail import Mail, Message

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm

# ==========================
# App & Config
# ==========================

load_dotenv()

app = Flask(__name__, static_folder="static")
app.secret_key = "mallhub_secret_key"

razorpay_client = razorpay.Client(
    auth=(
        os.getenv("RAZORPAY_KEY_ID"),
        os.getenv("RAZORPAY_KEY_SECRET")
    )
)

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

mail = Mail(app)


# ==========================
# Database Connection
# ==========================

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Rupin@23",
            database="mallhub"
        )
        print("MySQL Connected")
        return conn
    except mysql.connector.Error as e:
        print("Database Error:", e)
        return None


# ==========================
# Home
# ==========================

@app.route('/')
def home():
    return render_template('index.html')


# ==========================
# Dashboard
# ==========================

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')
    return render_template('dashboard.html', username=session['user'])


# ==========================
# Auth - Register / Login / Logout
# ==========================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            return "Database Connection Failed", 500

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (fullname, email, phone, password) VALUES (%s, %s, %s, %s)",
            (fullname, email, phone, password)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            return "Database Connection Failed", 500

        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s",
            (email, password)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['user'] = user['fullname']
            session['username'] = user['fullname']
            session['email'] = user['email']
            session['role'] = user['role']
            return redirect('/dashboard')

        return "Invalid Login"

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')


# ==========================
# User Profile
# ==========================

@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE fullname=%s", (session['user'],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('profile.html', user=user)


# ==========================
# Shopping
# ==========================

@app.route('/shopping')
def shopping():
    if 'user' not in session:
        return redirect('/login')

    search = request.args.get("search", "")

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    if search:
        cursor.execute(
            "SELECT * FROM products WHERE product_name LIKE %s OR category LIKE %s",
            (f"%{search}%", f"%{search}%")
        )
    else:
        cursor.execute("SELECT * FROM products")

    products = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("shopping.html", products=products, search=search)


@app.route('/product/<int:id>')
def product_details(id):
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE id=%s", (id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if product is None:
        return "Product Not Found", 404

    return render_template("product_details.html", product=product)


@app.route('/add_product_cart', methods=['POST'])
def add_product_cart():
    if 'user' not in session:
        return redirect('/login')

    product_name = request.form['product_name']
    price = float(request.form['price'])

    if 'shopping_cart' not in session:
        session['shopping_cart'] = []

    cart = session['shopping_cart']
    found = False
    for item in cart:
        if item.get('product_name') == product_name:
            item['quantity'] += 1
            found = True
            break

    if not found:
        cart.append({"product_name": product_name, "price": price, "quantity": 1})

    session['shopping_cart'] = cart
    session.modified = True
    return redirect('/shopping_checkout')


@app.route('/shopping_checkout')
def shopping_checkout():
    if 'user' not in session:
        return redirect('/login')

    items = session.get('shopping_cart', [])
    total = sum(item['price'] * item['quantity'] for item in items)
    return render_template('shopping_checkout.html', items=items, total=total)


@app.route('/apply_coupon', methods=['POST'])
def apply_coupon():
    if 'user' not in session:
        return redirect('/login')

    code = request.form['coupon']

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM coupons WHERE coupon_code=%s", (code,))
    coupon = cursor.fetchone()
    cursor.close()
    conn.close()

    if coupon:
        return f"Coupon Applied! Discount: {coupon['discount']}%"
    return "Invalid Coupon"


@app.route('/shopping_payment', methods=['POST'])
def shopping_payment():
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('shopping_cart', [])
    if not cart:
        return redirect('/shopping')

    amount = sum(item['price'] * item['quantity'] for item in cart)
    payment = request.form.get('payment')
    if not payment:
        return "Payment method is required", 400

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    order_id = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shopping_orders (username, total_amount, payment_method) VALUES (%s, %s, %s)",
            (session['user'], amount, payment)
        )
        conn.commit()
        order_id = cursor.lastrowid
    except mysql.connector.Error as e:
        conn.rollback()
        print("Payment Error:", e)
        return "Payment Failed", 500
    finally:
        cursor.close()
        conn.close()

    session['last_order'] = {
        "order_id": order_id,
        "items": cart,
        "amount": amount,
        "payment_method": payment
    }
    session.pop('shopping_cart', None)
    return render_template("payment_success.html", amount=amount, method=payment, order_id=order_id)


# ==========================
# Wishlist
# ==========================

@app.route('/add_wishlist', methods=['POST'])
def add_wishlist():
    if 'user' not in session:
        return redirect('/login')

    product_id = request.form['id']
    product_name = request.form['product_name']
    price = request.form['price']
    image = request.form['images']

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO wishlist (username, product_id, product_name, price, images) VALUES (%s, %s, %s, %s, %s)",
        (session['user'], product_id, product_name, price, image)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/shopping')


# ==========================
# Product Reviews
# ==========================

@app.route('/review/<int:product_id>')
def review(product_id):
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE id=%s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if product is None:
        return "Product Not Found", 404
    return render_template("review.html", product=product)


@app.route('/submit_review', methods=['POST'])
def submit_review():
    if 'user' not in session:
        return redirect('/login')

    product_id = request.form['product_id']
    product_name = request.form['product_name']
    rating = request.form['rating']
    review_text = request.form['review']

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reviews (username, product_id, product_name, rating, review) VALUES (%s, %s, %s, %s, %s)",
        (session['user'], product_id, product_name, rating, review_text)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return redirect('/shopping')


# ==========================
# Food Court
# ==========================

@app.route('/foodcourt')
def foodcourt():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM food_items")
    foods = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('foodcourt.html', foods=foods)


@app.route('/add_cart', methods=['POST'])
def add_cart():
    if 'user' not in session:
        return redirect('/login')

    food = request.form['food']
    price = float(request.form['price'])

    if 'cart' not in session:
        session['cart'] = []

    cart = session['cart']
    found = False
    for item in cart:
        if item.get('food') == food:
            item['quantity'] += 1
            found = True
            break

    if not found:
        cart.append({"food": food, "price": price, "quantity": 1})

    session['cart'] = cart
    session.modified = True
    return redirect('/foodcourt')


@app.route('/cart')
def cart():
    if 'user' not in session:
        return redirect('/login')

    items = session.get('cart', [])
    total = 0
    for item in items:
        item['total'] = item['price'] * item['quantity']
        total += item['total']

    return render_template("cart.html", items=items, total=total)


@app.route('/remove_cart/<int:index>')
def remove_cart(index):
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart.pop(index)
    session['cart'] = cart
    session.modified = True
    return redirect('/cart')


@app.route('/place_order')
def place_order():
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('cart', [])

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor()
    for item in cart:
        total = item['price'] * item['quantity']  # compute inline - avoids KeyError
        cursor.execute(
            "INSERT INTO orders (username, food_name, price, quantity, total) VALUES (%s, %s, %s, %s, %s)",
            (session['user'], item['food'], item['price'], item['quantity'], total)
        )

    conn.commit()
    cursor.close()
    conn.close()
    session.pop('cart', None)
    return render_template('order_success.html')


# ==========================
# Movies
# ==========================

@app.route('/movies')
def movies():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM movies")
    movies_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('movies.html', movies=movies_list)


@app.route('/movie/<int:id>')
def movie_details(id):
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM movies WHERE id=%s", (id,))
    movie = cursor.fetchone()

    if movie is None:
        cursor.close()
        conn.close()
        return "Movie Not Found", 404

    cursor.execute("""
        SELECT * FROM movie_reviews
        WHERE movie_name=%s
        ORDER BY id DESC
    """, (movie["movie_name"],))
    reviews = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "movie_details.html",
        movie=movie,
        reviews=reviews
    )


@app.route('/book_movie', methods=['POST'])
def book_movie():
    if 'user' not in session:
        return redirect('/login')

    movie = request.form['movie']
    time = request.form['time']

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO movie_bookings (username, movie_name, show_time) VALUES (%s, %s, %s)",
        (session['user'], movie, time)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return render_template('booking_success.html', movie=movie, time=time)


@app.route("/seat_selection", methods=["POST"])
def seat_selection():
    movie_name = request.form["movie_name"]
    theatre = request.form["theatre"]
    show_date = request.form["show_date"]
    show_time = request.form["show_time"]

    return render_template(
        "seat_selection.html",
        movie_name=movie_name,
        theatre=theatre,
        show_date=show_date,
        show_time=show_time
    )


@app.route("/confirm_seats", methods=["POST"])
def confirm_seats():

    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    movie_name = request.form["movie_name"]
    theatre = request.form["theatre"]
    show_date = request.form["show_date"]
    show_time = request.form["show_time"]

    seats = request.form.getlist("seat_no")

    username = session["username"]

    for seat in seats:
        cursor.execute("""
        INSERT INTO movie_seats
        (movie_name, theatre, show_date, show_time, seat_no, username)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (movie_name, theatre, show_date, show_time, seat, username))

    conn.commit()
    conn.close()

    session["movie_name"] = movie_name
    session["theatre"] = theatre
    session["show_date"] = show_date
    session["show_time"] = show_time
    session["seats"] = seats

    return redirect("/food_combo")


@app.route("/food_combo")
def food_combo():
    return render_template("food_combo.html")


@app.route("/movie_payment_page", methods=["GET", "POST"])
def movie_payment_page():

    if request.method == "POST":
        session["food"] = request.form.get("food", "No Food")
        session["food_price"] = int(request.form.get("price", 0))

    movie = session.get("movie_name")
    theatre = session.get("theatre")
    seats = ",".join(session.get("seats", []))

    food = session.get("food", "No Food")

    ticket_amount = len(session.get("seats", [])) * 250

    food_amount = session.get("food_price", 0)

    total = ticket_amount + food_amount

    return render_template(
        "movie_payment.html",
        movie=movie,
        theatre=theatre,
        seats=seats,
        food=food,
        ticket_amount=ticket_amount,
        food_amount=food_amount,
        total=total
    )


@app.route("/movie_payment", methods=["POST"])
def movie_payment():

    total = request.form["total"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO movie_bookings
        (username, movie_name, theatre, show_date, show_time, seat_no, amount, payment_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """,
    (
        session["username"],
        session["movie_name"],
        session["theatre"],
        session["show_date"],
        session["show_time"],
        ",".join(session["seats"]),
        total,
        "Paid"
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/movie_ticket")


@app.route("/movie_ticket")
def movie_ticket():

    movie = session.get("movie_name")
    theatre = session.get("theatre")
    show_date = session.get("show_date")
    show_time = session.get("show_time")
    seats = ",".join(session.get("seats", []))

    booking_id = str(uuid.uuid4())[:8].upper()

    qr_data = f"""
Booking ID : {booking_id}
Movie : {movie}
Theatre : {theatre}
Date : {show_date}
Time : {show_time}
Seats : {seats}
"""

    qr = qrcode.make(qr_data)

    filename = booking_id + ".png"

    path = os.path.join("static", "tickets", filename)

    qr.save(path)

    session["qr_image"] = filename

    return render_template(
        "movie_ticket.html",
        movie=movie,
        theatre=theatre,
        show_date=show_date,
        show_time=show_time,
        seats=seats,
        booking_id=booking_id,
        qr_image=filename
    )


@app.route("/movie_history")
def movie_history():

    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM movie_bookings
        WHERE username=%s
        ORDER BY id DESC
    """, (session["username"],))

    bookings = cursor.fetchall()

    conn.close()

    return render_template(
        "movie_history.html",
        bookings=bookings
    )


# ==========================
# Smart Parking
# ==========================

@app.route('/parking')
def parking():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM parking_slots")
    slots = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('parking.html', slots=slots)


@app.route('/book_parking', methods=['POST'])
def book_parking():
    if 'user' not in session:
        return redirect('/login')

    slot = request.form['slot']
    vehicle = request.form['vehicle']

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE parking_slots SET status='Occupied' WHERE slot_number=%s",
        (slot,)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return render_template('parking_success.html', slot=slot, vehicle=vehicle)


# ==========================
# Payment (Razorpay / Food Court)
# ==========================

@app.route('/payment')
def payment():
    if 'user' not in session:
        return redirect('/login')

    cart = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart)
    amount_paise = int(round(total * 100))

    order = razorpay_client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": 1
    })
    return render_template('payment.html', total=total, order=order, razorpay_key_id=os.getenv("RAZORPAY_KEY_ID"))


@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'user' not in session:
        return redirect('/login')

    # Recalculate from session cart - do not trust client-provided amount
    cart = session.get('cart', [])
    amount = sum(item['price'] * item['quantity'] for item in cart)
    method = request.form.get('method', '')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payments (username, amount, payment_method) VALUES (%s, %s, %s)",
        (session['user'], amount, method)
    )
    conn.commit()
    payment_id = cursor.lastrowid
    cursor.close()
    conn.close()

    session['last_payment'] = {"payment_id": payment_id, "amount": amount, "method": method}
    return render_template('payment_success.html', amount=amount, method=method, payment_id=payment_id)


@app.route("/create_order", methods=["POST"])
def create_order():

    amount = int(request.form["total"]) * 100

    order = razorpay_client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })

    return render_template(
        "razorpay_payment.html",
        order=order,
        key=os.getenv("RAZORPAY_KEY_ID")
    )


@app.route("/payment_success", methods=["POST"])
def payment_success():

    payment_id = request.form["razorpay_payment_id"]
    order_id = request.form["razorpay_order_id"]
    signature = request.form["razorpay_signature"]

    try:

        razorpay_client.utility.verify_payment_signature({
            "razorpay_payment_id": payment_id,
            "razorpay_order_id": order_id,
            "razorpay_signature": signature
        })

        amount = request.form.get("amount", 0)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO movie_payments
        (username, payment_id, order_id, amount, status)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            session["username"],
            payment_id,
            order_id,
            amount,
            "Success"
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/movie_ticket")

    except:

        return "Payment Failed"


# ==========================
# Invoices / Receipts (PDF)
# ==========================

def _build_invoice_pdf(order_id, username, items, amount, payment_method):
    """Builds a PDF invoice in memory and returns a BytesIO buffer."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("MallHub - Payment Receipt", styles['Title']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Invoice / Order #: {order_id}", styles['Normal']))
    elements.append(Paragraph(f"Customer: {username}", styles['Normal']))
    elements.append(Paragraph(f"Payment Method: {payment_method}", styles['Normal']))
    elements.append(Spacer(1, 20))

    if items:
        table_data = [["Item", "Unit Price", "Qty", "Subtotal"]]
        for item in items:
            name = item.get("product_name") or item.get("food") or "Item"
            price = float(item.get("price", 0))
            qty = int(item.get("quantity", 1))
            table_data.append([name, f"Rs.{price:.2f}", str(qty), f"Rs.{price * qty:.2f}"])

        table = Table(table_data, colWidths=[7 * cm, 3.5 * cm, 2 * cm, 3.5 * cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

    elements.append(Paragraph(f"<b>Total Paid: Rs.{float(amount):.2f}</b>", styles['Heading2']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Thank you for shopping with MallHub!", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer


@app.route('/invoice/shopping/<int:order_id>')
def invoice_shopping(order_id):
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM shopping_orders WHERE id=%s AND username=%s",
        (order_id, session['user'])
    )
    order = cursor.fetchone()
    cursor.close()
    conn.close()

    if order is None:
        return "Order Not Found", 404

    last_order = session.get('last_order', {})
    items = last_order.get('items', []) if last_order.get('order_id') == order_id else []

    buffer = _build_invoice_pdf(
        order_id=order['id'],
        username=order['username'],
        items=items,
        amount=order['total_amount'],
        payment_method=order['payment_method']
    )
    return send_file(buffer, as_attachment=True, download_name=f"invoice_{order_id}.pdf", mimetype="application/pdf")


@app.route('/invoice/payment/<int:payment_id>')
def invoice_payment(payment_id):
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM payments WHERE id=%s AND username=%s",
        (payment_id, session['user'])
    )
    pay = cursor.fetchone()
    cursor.close()
    conn.close()

    if pay is None:
        return "Payment Not Found", 404

    buffer = _build_invoice_pdf(
        order_id=pay['id'],
        username=pay['username'],
        items=[],
        amount=pay['amount'],
        payment_method=pay['payment_method']
    )
    return send_file(buffer, as_attachment=True, download_name=f"invoice_{payment_id}.pdf", mimetype="application/pdf")


# ==========================
# Order History
# ==========================

@app.route('/order_history')
def order_history():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM orders WHERE username=%s ORDER BY id DESC",
        (session['user'],)
    )
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('order_history.html', orders=orders)


# ==========================
# Notifications
# ==========================

@app.route('/notifications')
def notifications():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC")
    notices = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('notifications.html', notices=notices)


# ==========================
# Store Locator
# ==========================

@app.route('/stores')
def stores():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM stores")
    stores_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('stores.html', stores=stores_list)


# ==========================
# AI Assistant
# ==========================

@app.route('/ai_assistant', methods=['GET', 'POST'])
def ai_assistant():
    if 'user' not in session:
        return redirect('/login')

    answer = ""

    if request.method == 'POST':
        question = request.form['question'].lower()

        if "movie" in question:
            answer = "Today's recommended movie is Mission Impossible."
        elif "food" in question:
            answer = "Try KFC or Pizza Hut in the Food Court."
        elif "parking" in question:
            answer = "Parking is available on Ground Floor."
        elif "shoe" in question:
            answer = "Nike Shoes available for Rs.2999."
        elif "tv" in question:
            answer = "Samsung TV available for Rs.45,999."
        elif "shirt" in question:
            answer = "Premium T-Shirts starting from Rs.799."
        elif "electronics" in question:
            answer = "Electronics section contains TVs, Laptops and Mobiles."
        elif "shopping" in question:
            answer = "Visit Nike, Adidas and Apple Store."
        elif "store" in question:
            answer = "Open Store Locator to find shop locations."
        elif "offer" in question:
            answer = "Weekend Sale - Up to 70% OFF."
        else:
            answer = "Sorry, I could not understand. Please try another question."

    return render_template('ai_assistant.html', answer=answer)


@app.route("/chatbot", methods=["POST"])
def chatbot():

    data = request.get_json()
    message = data.get("message", "").lower()

    if "movie" in message:
        reply = "🎬 You can book movies from the Cinema section."

    elif "food" in message:
        reply = "🍔 Visit the Food Court to order delicious food."

    elif "product" in message or "shopping" in message:
        reply = "🛍 Browse our Shopping section for the latest products."

    elif "coupon" in message:
        reply = "🎁 Check the Coupons page for the latest offers."

    elif "contact" in message:
        reply = "📞 Contact us at support@mallhub.com"

    elif "hello" in message or "hi" in message:
        reply = "👋 Welcome to MallHub! How can I help you today?"

    else:
        reply = "🤖 Sorry, I didn't understand. Please ask about movies, food, shopping, or coupons."

    return jsonify({"reply": reply})


# ==========================
# Sales Chart
# ==========================

@app.route('/sales_chart')
def sales_chart():
    if 'user' not in session:
        return redirect('/login')

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    sales = [12000, 18000, 15000, 25000, 30000, 42000]

    plt.figure(figsize=(8, 5))
    plt.plot(months, sales, marker="o")
    plt.title("MallHub Monthly Sales")
    plt.xlabel("Month")
    plt.ylabel("Revenue (Rs.)")
    plt.grid(True)

    os.makedirs("static", exist_ok=True)
    chart_path = os.path.join("static", "sales_chart.png")
    plt.savefig(chart_path)
    plt.close()

    return render_template('sales_chart.html', chart="sales_chart.png")


# ==========================
# Admin Dashboard
# ==========================

@app.route('/admin')
def admin():
    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM users")
    users = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM products")
    products = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM orders")
    orders = cursor.fetchone()['total']

    cursor.execute("SELECT SUM(total) AS revenue FROM orders")
    result = cursor.fetchone()
    revenue = result['revenue'] if result['revenue'] else 0

    cursor.close()
    conn.close()

    return render_template('admin.html', users=users, products=products, orders=orders, revenue=revenue)



@app.route("/admin_movies")
def admin_movies():

    if "username" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM movies")
    movies = cursor.fetchall()

    conn.close()

    return render_template("admin_movies.html", movies=movies)


@app.route("/add_movie", methods=["POST"])
def add_movie():

    if "username" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO movies
    (movie_name, language, genre, duration, rating, poster)
    VALUES (%s, %s, %s, %s, %s, %s)
    """,
    (
        request.form["movie_name"],
        request.form["language"],
        request.form["genre"],
        request.form["duration"],
        request.form["rating"],
        request.form["poster"]
    ))

    conn.commit()
    conn.close()

    return redirect("/admin_movies")


@app.route("/delete_movie/<int:id>")
def delete_movie(id):

    if "username" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM movies WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return redirect("/admin_movies")


@app.route("/edit_movie/<int:id>", methods=["GET", "POST"])
def edit_movie(id):

    if "username" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        cursor.execute("""
        UPDATE movies
        SET
        movie_name=%s,
        language=%s,
        genre=%s,
        duration=%s,
        rating=%s,
        poster=%s
        WHERE id=%s
        """,
        (
            request.form["movie_name"],
            request.form["language"],
            request.form["genre"],
            request.form["duration"],
            request.form["rating"],
            request.form["poster"],
            id
        ))

        conn.commit()
        conn.close()

        return redirect("/admin_movies")

    cursor.execute("SELECT * FROM movies WHERE id=%s", (id,))
    movie = cursor.fetchone()
    conn.close()

    return render_template("edit_movie.html", movie=movie)


@app.route("/admin_dashboard")
def admin_dashboard():

    if "username" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) total FROM users")
    users = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) total FROM products")
    products = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) total FROM movie_bookings")
    bookings = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT IFNULL(SUM(amount),0) revenue
        FROM movie_bookings
        WHERE payment_status='Paid'
    """)
    revenue = cursor.fetchone()["revenue"]

    cursor.execute("SELECT COUNT(*) total FROM reviews")
    reviews = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) total
        FROM food_orders
    """)
    food_orders = cursor.fetchone()["total"]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        users=users,
        products=products,
        bookings=bookings,
        revenue=revenue,
        reviews=reviews,
        food_orders=food_orders
    )



@app.route("/movie_review", methods=["POST"])
def movie_review():

    if "username" not in session:
        return redirect("/login")

    movie = request.form["movie_name"]
    rating = request.form["rating"]
    review = request.form["review"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO movie_reviews
        (username, movie_name, rating, review)
        VALUES (%s, %s, %s, %s)
    """, (
        session["username"],
        movie,
        rating,
        review
    ))

    conn.commit()
    conn.close()

    return redirect("/movies")


@app.route("/admin_users")
def admin_users():

    if session.get("role") != "admin":
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_users.html",
        users=users
    )


@app.route("/make_admin/<int:id>")
def make_admin(id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET role='admin' WHERE id=%s",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin_users")


@app.route("/delete_user/<int:id>")
def delete_user(id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM users WHERE id=%s",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/admin_users")


# ==========================
# Send Ticket via Email
# ==========================

@app.route("/send_ticket")
def send_ticket():

    if "username" not in session:
        return redirect("/login")

    user_email = session.get("email")
    if not user_email:
        return "No email found in session. Please log in again.", 400

    required_keys = ["movie_name", "theatre", "show_date", "show_time", "seats"]
    for key in required_keys:
        if key not in session:
            return f"Missing booking info ({key}). Please complete booking first.", 400

    seats_display = ", ".join(session["seats"])

    msg = Message(
        subject="🎬 MallHub Movie Ticket",
        sender=app.config["MAIL_USERNAME"],
        recipients=[user_email]
    )

    msg.body = f"""Hello {session['username']},

Your movie booking is confirmed! 🎉

──────────────────────────────
🎬  Movie   : {session['movie_name']}
🏛️  Theatre  : {session['theatre']}
📅  Date    : {session['show_date']}
⏰  Time    : {session['show_time']}
💺  Seats   : {seats_display}
──────────────────────────────

Please arrive 15 minutes before the show.
Thank you for choosing MallHub!

— MallHub Team
"""

    qr_image = session.get("qr_image")
    if qr_image:
        try:
            with app.open_resource("static/tickets/" + qr_image) as fp:
                msg.attach(
                    qr_image,
                    "image/png",
                    fp.read()
                )
        except FileNotFoundError:
            print(f"QR file not found: {qr_image}, sending email without attachment.")

    try:
        mail.send(msg)
    except Exception as e:
        print("Mail Error:", e)
        return f"Failed to send email: {e}", 500

    return redirect("/movie_ticket")


# ==========================
# Run
# ==========================

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)