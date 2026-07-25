import io
import os

from flask import Flask, render_template, request, redirect, session, send_file
import mysql.connector
import razorpay

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm

app = Flask(__name__)

app.secret_key = "mallhub_secret_key"

# Razorpay credentials — prefer environment variables over hardcoding real
# keys here, since this file (like the DB password above) isn't a safe
# place to keep secrets if it's ever committed or shared.
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "YOUR_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "YOUR_SECRET_KEY")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


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

        print("✅ MySQL Connected")

        return conn


    except mysql.connector.Error as e:

        print("❌ Database Error:", e)

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

    if 'user' in session:

        return render_template(
            'dashboard.html',
            username=session['user']
        )

    return redirect('/login')



# ==========================
# Shopping
# ==========================

@app.route('/shopping')
def shopping():

    if 'user' not in session:
        return redirect('/login')

    search = request.args.get("search", "")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        cursor.execute("""
            SELECT *
            FROM products
            WHERE product_name LIKE %s
               OR category LIKE %s
        """, (f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("SELECT * FROM products")

    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "shopping.html",
        products=products,
        search=search
    )



# ==========================
# Product Details
# ==========================

@app.route('/product/<int:id>')
def product_details(id):

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM products WHERE id=%s",
        (id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if product is None:
        return "Product Not Found"

    return render_template(
        "product_details.html",
        product=product
    )



# ==========================
# Movies
# ==========================

@app.route('/movies')
def movies():

    if 'user' in session:

        return render_template('movies.html')

    return redirect('/login')



@app.route('/book_movie', methods=['POST'])
def book_movie():

    if 'user' not in session:
        return redirect('/login')

    movie = request.form['movie']
    time = request.form['time']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO movie_bookings
        (username, movie_name, show_time)
        VALUES (%s, %s, %s)
    """, (
        session['user'],
        movie,
        time
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return render_template(
        'booking_success.html',
        movie=movie,
        time=time
    )



# ==========================
# Smart Parking
# ==========================

@app.route('/parking')
def parking():

    if 'user' in session:


        conn = get_db_connection()


        cursor = conn.cursor(dictionary=True)


        cursor.execute(
            "SELECT * FROM parking_slots"
        )


        slots = cursor.fetchall()


        cursor.close()

        conn.close()


        return render_template(
            'parking.html',
            slots=slots
        )


    return redirect('/login')



@app.route('/book_parking', methods=['POST'])
def book_parking():

    if 'user' in session:


        slot = request.form['slot']

        vehicle = request.form['vehicle']


        conn = get_db_connection()


        cursor = conn.cursor()


        cursor.execute(

            """
            UPDATE parking_slots
            SET status='Occupied'
            WHERE slot_number=%s
            """,

            (slot,)

        )


        conn.commit()


        cursor.close()

        conn.close()


        return render_template(
            'parking_success.html',
            slot=slot,
            vehicle=vehicle
        )


    return redirect('/login')



# ==========================
# Food Court
# ==========================

@app.route('/foodcourt')
def foodcourt():

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM food_items")
    foods = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'foodcourt.html',
        foods=foods
    )

# ==========================
# Add Food To Cart
# ==========================

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
        cart.append({
            "food": food,
            "price": price,
            "quantity": 1
        })

    session['cart'] = cart
    session.modified = True

    return redirect('/foodcourt')

# ==========================
# Add Product To Cart
# ==========================

@app.route('/add_product_cart', methods=['POST'])
def add_product_cart():

    if 'user' not in session:
        return redirect('/login')

    product_name = request.form['product_name']
    price = float(request.form['price'])

    if 'shopping_cart' not in session:
        session['shopping_cart'] = []

    cart = session['shopping_cart']

    # Check if product already exists
    found = False

    for item in cart:
        if item.get('product_name') == product_name:
            item['quantity'] += 1
            found = True
            break

    if not found:
        cart.append({
            "product_name": product_name,
            "price": price,
            "quantity": 1
        })

    session['shopping_cart'] = cart
    session.modified = True

    return redirect('/shopping_checkout')



# ==========================
# Shopping Checkout Page
# ==========================

@app.route('/shopping_checkout')
def shopping_checkout():

    if 'user' not in session:
        return redirect('/login')

    items = session.get('shopping_cart', [])

    total = sum(item['price'] * item['quantity'] for item in items)

    return render_template(
        'shopping_checkout.html',
        items=items,
        total=total
    )



# ==========================
# Apply Coupon
# ==========================

@app.route('/apply_coupon', methods=['POST'])
def apply_coupon():

    if 'user' not in session:
        return redirect('/login')

    code = request.form['coupon']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM coupons WHERE coupon_code=%s",
        (code,)
    )

    coupon = cursor.fetchone()

    cursor.close()
    conn.close()

    if coupon:

        return f"Coupon Applied! Discount: {coupon['discount']}%"

    else:

        return "Invalid Coupon"



# ==========================
# Shopping Payment
# ==========================

@app.route('/shopping_payment', methods=['POST'])
def shopping_payment():

    if 'user' not in session:
        return redirect('/login')

    cart = session.get('shopping_cart', [])

    if not cart:
        return redirect('/shopping')

    # Recalculate the total from the session cart instead of trusting the form
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
            """
            INSERT INTO shopping_orders
            (username, total_amount, payment_method)
            VALUES (%s, %s, %s)
            """,
            (
                session['user'],
                amount,
                payment
            )
        )

        conn.commit()

        order_id = cursor.lastrowid

    except mysql.connector.Error as e:
        conn.rollback()
        print("❌ Payment Error:", e)
        return "Payment Failed", 500

    finally:
        cursor.close()
        conn.close()

    # Keep a copy of the purchased items so the invoice can list them
    # even after the cart is cleared from the session.
    session['last_order'] = {
        "order_id": order_id,
        "items": cart,
        "amount": amount,
        "payment_method": payment
    }

    session.pop('shopping_cart', None)

    return render_template(
        "payment_success.html",
        amount=amount,
        method=payment,
        order_id=order_id
    )



# ==========================
# Cart
# ==========================

@app.route('/cart')
def cart():

    if 'user' not in session:
        return redirect('/login')

    items = session.get('cart', [])

    total = 0

    for item in items:
        item['total'] = item['price'] * item['quantity']
        total += item['total']

    return render_template(
        "cart.html",
        items=items,
        total=total
    )



# ==========================
# Remove Cart Item
# ==========================

@app.route('/remove_cart/<int:index>')
def remove_cart(index):

    if 'user' in session:


        cart=session.get('cart',[])


        cart.pop(index)


        session['cart']=cart


        session.modified=True


        return redirect('/cart')


    return redirect('/login')



# ==========================
# Place Order
# ==========================

@app.route('/place_order')
def place_order():

    if 'user' in session:


        cart=session.get('cart',[])


        conn=get_db_connection()


        cursor=conn.cursor()



        for item in cart:


            cursor.execute(

            """
            INSERT INTO orders
            (username,food_name,price,quantity,total)

            VALUES(%s,%s,%s,%s,%s)
            """,

            (

            session['user'],

            item['food'],

            item['price'],

            item['quantity'],

            item['total']

            )

            )



        conn.commit()


        cursor.close()

        conn.close()



        session.pop('cart',None)


        return render_template(
            'order_success.html'
        )


    return redirect('/login')



# ==========================
# Payment Page
# ==========================

@app.route('/payment')
def payment():

    if 'user' in session:

        cart = session.get('cart',[])

        total = 0


        for item in cart:

            total += item['price'] * item['quantity']

        # Razorpay wants the amount in paise (smallest currency unit),
        # and the order amount must be created server-side from the
        # cart total rather than trusted from the client.
        amount_paise = int(round(total * 100))

        order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1
        })

        return render_template(
            'payment.html',
            total=total,
            order=order,
            razorpay_key_id=RAZORPAY_KEY_ID
        )


    return redirect('/login')



# ==========================
# Process Payment
# ==========================

@app.route('/process_payment', methods=['POST'])
def process_payment():

    if 'user' in session:

        amount = request.form['amount']
        method = request.form['method']

        conn = get_db_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO payments
        (username, amount, payment_method)
        VALUES (%s, %s, %s)
        """

        cursor.execute(
            sql,
            (
                session['user'],
                amount,
                method
            )
        )

        conn.commit()

        payment_id = cursor.lastrowid

        cursor.close()
        conn.close()

        session['last_payment'] = {
            "payment_id": payment_id,
            "amount": amount,
            "method": method
        }

        return render_template(
            'payment_success.html',
            amount=amount,
            method=method,
            payment_id=payment_id
        )

    return redirect('/login')



# ==========================
# Invoice / Receipt (PDF)
# ==========================

def _build_invoice_pdf(order_id, username, items, amount, payment_method):
    """Builds a simple PDF invoice in memory and returns a BytesIO buffer."""

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm
    )

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
            subtotal = price * qty

            table_data.append([
                name,
                f"₹{price:.2f}",
                str(qty),
                f"₹{subtotal:.2f}"
            ])

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

    elements.append(Paragraph(f"<b>Total Paid: ₹{float(amount):.2f}</b>", styles['Heading2']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Thank you for shopping with MallHub!", styles['Normal']))

    doc.build(elements)

    buffer.seek(0)

    return buffer


@app.route('/invoice/shopping/<int:order_id>')
def invoice_shopping(order_id):
    """Downloadable PDF invoice for a shopping order."""

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()

    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT * FROM shopping_orders
        WHERE id=%s AND username=%s
        """,
        (order_id, session['user'])
    )

    order = cursor.fetchone()

    cursor.close()
    conn.close()

    if order is None:
        return "Order Not Found", 404

    # Item-level detail is best-effort: it's only available if this is the
    # most recently placed order still cached in the session.
    last_order = session.get('last_order', {})

    items = last_order.get('items', []) if last_order.get('order_id') == order_id else []

    buffer = _build_invoice_pdf(
        order_id=order['id'],
        username=order['username'],
        items=items,
        amount=order['total_amount'],
        payment_method=order['payment_method']
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{order_id}.pdf",
        mimetype="application/pdf"
    )


@app.route('/invoice')
def invoice():

    if 'user' not in session:
        return redirect('/login')

    pdf_file = "MallHub_Invoice.pdf"

    doc = SimpleDocTemplate(pdf_file)
    styles = getSampleStyleSheet()

    story = []

    story.append(Paragraph("<b>MallHub Invoice</b>", styles["Title"]))
    story.append(Paragraph("Thank you for shopping with MallHub!", styles["Normal"]))
    story.append(Paragraph("<br/>", styles["Normal"]))
    story.append(Paragraph("Customer: " + session.get("user", "Guest"), styles["Normal"]))

    doc.build(story)

    return send_file(pdf_file, as_attachment=True)


@app.route('/invoice/payment/<int:payment_id>')
def invoice_payment(payment_id):
    """Downloadable PDF invoice for a foodcourt/general payment."""

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()

    if conn is None:
        return "Database Connection Failed", 500

    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT * FROM payments
        WHERE id=%s AND username=%s
        """,
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

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{payment_id}.pdf",
        mimetype="application/pdf"
    )



# ==========================
# Register
# ==========================

@app.route('/register',methods=['GET','POST'])
def register():


    if request.method=='POST':


        fullname=request.form['fullname']

        email=request.form['email']

        phone=request.form['phone']

        password=request.form['password']


        conn=get_db_connection()


        cursor=conn.cursor()


        cursor.execute(

        """
        INSERT INTO users
        (fullname,email,phone,password)

        VALUES(%s,%s,%s,%s)
        """,

        (fullname,email,phone,password)

        )


        conn.commit()


        cursor.close()

        conn.close()


        return redirect('/login')



    return render_template('register.html')





# ==========================
# Login
# ==========================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()

        if conn is None:
            return "Database Connection Failed"

        cursor = conn.cursor(dictionary=True, buffered=True)

        cursor.execute(
            """
            SELECT * FROM users
            WHERE email=%s AND password=%s
            """,
            (email, password)
        )

        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            session['user'] = user['fullname']
            return redirect('/dashboard')

        return "Invalid Login"

    return render_template("login.html")


# ==========================
# User Profile
# ==========================

@app.route('/profile')
def profile():

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE fullname=%s",
        (session['user'],)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "profile.html",
        user=user
    )


# ==========================
# Notifications
# ==========================

@app.route('/notifications')
def notifications():

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM notifications
        ORDER BY created_at DESC
    """)

    notices = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "notifications.html",
        notices=notices
    )


# ==========================
# Order History
# ==========================

@app.route('/order_history')
def order_history():

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM orders
        WHERE username = %s
        ORDER BY id DESC
    """, (session['user'],))

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "order_history.html",
        orders=orders
    )


# ==========================
# Store Locator
# ==========================

@app.route('/stores')
def stores():

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM stores")

    stores = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "stores.html",
        stores=stores
    )


# ==========================
# AI Assistant
# ==========================

@app.route('/assistant')
def assistant():

    if 'user' not in session:
        return redirect('/login')

    return render_template("assistant.html")


@app.route('/ask_ai', methods=['POST'])
def ask_ai():

    question = request.form['question'].lower()

    answer = "Sorry, I don't understand."

    if "movie" in question:
        answer = "🎬 Today's recommended movie is Mission Impossible."

    elif "food" in question:
        answer = "🍔 Try KFC or Pizza Hut in the Food Court."

    elif "parking" in question:
        answer = "🚗 Parking is available on Ground Floor."

    elif "shopping" in question:
        answer = "🛍 Visit Nike, Adidas and Apple Store."

    elif "store" in question:
        answer = "🏬 Open Store Locator to find shop locations."

    elif "offer" in question:
        answer = "🎉 Weekend Sale - Up to 70% OFF."

    return render_template(
        "assistant.html",
        answer=answer
    )


@app.route('/ai_assistant', methods=['GET', 'POST'])
def ai_assistant():

    if 'user' not in session:
        return redirect('/login')

    answer = ""

    if request.method == "POST":

        question = request.form['question'].lower()

        if "shoe" in question:
            answer = "👟 Nike Shoes available for ₹2999."

        elif "tv" in question:
            answer = "📺 Samsung TV available for ₹45,999."

        elif "shirt" in question:
            answer = "👕 Premium T-Shirts starting from ₹799."

        elif "electronics" in question:
            answer = "💻 Electronics section contains TVs, Laptops and Mobiles."

        else:
            answer = "😊 Sorry, I couldn't understand. Please try another question."

    return render_template(
        "ai_assistant.html",
        answer=answer
    )



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
    plt.ylabel("Revenue (₹)")
    plt.grid(True)

    os.makedirs("static", exist_ok=True)

    chart_path = os.path.join("static", "sales_chart.png")
    plt.savefig(chart_path)
    plt.close()

    return render_template(
        "sales_chart.html",
        chart="sales_chart.png"
    )



# ==========================
# Admin Dashboard
# ==========================

@app.route('/admin')
def admin():

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total Users
    cursor.execute("SELECT COUNT(*) AS total FROM users")
    users = cursor.fetchone()['total']

    # Total Products
    cursor.execute("SELECT COUNT(*) AS total FROM products")
    products = cursor.fetchone()['total']

    # Total Orders
    cursor.execute("SELECT COUNT(*) AS total FROM orders")
    orders = cursor.fetchone()['total']

    # Total Revenue
    cursor.execute("SELECT SUM(total) AS revenue FROM orders")
    result = cursor.fetchone()

    revenue = result['revenue'] if result['revenue'] else 0

    cursor.close()
    conn.close()

    return render_template(
        "admin.html",
        users=users,
        products=products,
        orders=orders,
        revenue=revenue
    )


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
    image = request.form['image']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO wishlist
        (username, product_id, product_name, price, image)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        session['user'],
        product_id,
        product_name,
        price,
        image
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect('/shopping')


# ==========================
# Product Review
# ==========================

@app.route('/review/<int:product_id>')
def review(product_id):

    if 'user' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM products WHERE id=%s",
        (product_id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if product is None:
        return "Product Not Found"

    return render_template(
        "review.html",
        product=product
    )


@app.route('/submit_review', methods=['POST'])
def submit_review():

    if 'user' not in session:
        return redirect('/login')

    product_id = request.form['product_id']
    product_name = request.form['product_name']
    rating = request.form['rating']
    review = request.form['review']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reviews
        (username, product_id, product_name, rating, review)
        VALUES (%s,%s,%s,%s,%s)
    """, (
        session['user'],
        product_id,
        product_name,
        rating,
        review
    ))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect('/shopping')



# ==========================
# Logout
# ==========================

@app.route('/logout')
def logout():

    session.pop('user', None)

    return redirect('/login')



# ==========================
# Run
# ==========================

if __name__=="__main__":

    app.run(debug=True)

