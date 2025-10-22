from dotenv import load_dotenv
load_dotenv()
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mysql.connector
from datetime import datetime
import os

# Database connection setup


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "smartordersync"),
        autocommit=False
    )


# Object Oriented Programming Classes
class Customer:
    def __init__(self, customer_id, name, email, region):
        self.customer_id = customer_id
        self.name = name
        self.email = email
        self.region = region

class Product:
    def __init__(self, product_id, name, category, price, stock):
        self.product_id = product_id
        self.name = name
        self.category = category
        self.price = float(price)
        self.stock = int(stock)

    def update_stock(self, connection, quantity):
        new_stock = self.stock - quantity
        if new_stock < 0:
            raise ValueError("Insufficient stock for product ID {}".format(self.product_id))
        cursor = connection.cursor()
        cursor.execute("UPDATE Products SET stock = %s WHERE product_id = %s", (new_stock, self.product_id))
        connection.commit()
        cursor.close()
        self.stock = new_stock

class Order:
    def __init__(self, order_id, customer: Customer, product: Product, quantity):
        self.order_id = order_id
        self.customer = customer
        self.product = product
        self.quantity = int(quantity)
        self.total_price = round(self.product.price * self.quantity, 2)
        self.order_date = datetime.now()

    def process_order(self, connection):
        try:
            # Insert order into database
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO Orders (customer_id, product_id, quantity, total_price, order_date, status) VALUES (%s, %s, %s, %s, %s, %s)",
                (self.customer.customer_id, self.product.product_id, self.quantity, self.total_price, self.order_date, "CONFIRMED")
            )
            connection.commit()
            self.order_id = cursor.lastrowid

            # Update product stock
            self.product.update_stock(connection, self.quantity)

            # Create invoice
            cursor.execute(
                "INSERT INTO Invoices (order_id, amount, payment_status, invoice_date) VALUES (%s, %s, %s, %s)",
                (self.order_id, self.total_price, "PENDING", self.order_date)
            )
            connection.commit()
            cursor.close()
            self.status = "COMPLETED"
        except Exception as e:
            connection.rollback()
            self.status = "FAILED"
            raise e
        
# Flask application setup
app = Flask(__name__, template_folder='templates')
CORS(app)

@app.route('/')
def index():
    return render_template('order_form.html')

@app.route('/api/products')
def api_products():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Products")
    data = cursor.fetchall()
    cursor.close(); connection.close()
    return jsonify(data)

@app.route('/api/place_order', methods=['POST'])
def api_place_order():
    payload = request.get_json() or request.form
    try:
        customer_id = int(payload.get('customer_id'))
        product_id = int(payload.get('product_id'))
        quantity = int(payload.get('quantity'))
    except Exception:
        return jsonify({"error": "Invalid Payload"}), 400
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Fetch customer details
    cursor.execute("SELECT * FROM Customers WHERE customer_id = %s", (customer_id,))
    customer_data = cursor.fetchone()
    if not customer_data:
        cursor.close(); connection.close();
        return jsonify({"error": "Customer not found"}), 404
    customer = Customer(customer_data['customer_id'], customer_data['name'], customer_data['email'], customer_data['region'])

    # Fetch product details
    cursor.execute("SELECT * FROM Products WHERE product_id = %s", (product_id,))
    product_data = cursor.fetchone()
    if not product_data:
        cursor.close(); connection.close();
        return jsonify({"error": "Product not found"}), 404
    product = Product(product_data['product_id'], product_data['name'], product_data['category'], product_data['price'], product_data['stock']) 

    order = Order(None, customer, product, quantity)
    try: 
        order.process_order(connection)
    except ValueError as e:
        connection.close()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        connection.rollback()
        connection.close()
        return jsonify({"error": "Order processing failed"}), 500
    
    connection.close()
    return jsonify({
        "message": "Order placed successfully",
        "order_id": order.order_id,
        "customer_id": order.customer.customer_id,
        "product_id": order.product.product_id,
        "quantity": order.quantity,
        "total_price": order.total_price,
        "status": order.status
    }), 201

@app.route('/api/orders')
def api_orders():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT o.order_id, o.quantity, o.total_price, o.order_date, o.status,
               c.customer_id, c.name AS customer_name, c.email AS customer_email,
               p.product_id, p.name AS product_name, p.category AS product_category
        FROM Orders o
        JOIN Customers c ON o.customer_id = c.customer_id
        JOIN Products p ON o.product_id = p.product_id
        ORDER BY o.order_date DESC
    """)
    data = cursor.fetchall()
    cursor.close(); connection.close()
    return jsonify(data)

if __name__=='__main__':
    app.run(debug=True, port=5000)