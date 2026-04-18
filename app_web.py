import streamlit as st
import pandas as pd
import sqlite3
import datetime
from sklearn.linear_model import LinearRegression
from fpdf import FPDF

# --- 1. SESSION STATE & CONFIG ---
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'last_receipt' not in st.session_state:
    st.session_state.last_receipt = None

st.set_page_config(page_title="ChefIntel Enterprise", page_icon="💎", layout="wide")

# --- 2. DATABASE ARCHITECTURE (Self-Healing) ---
def init_db():
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS menu (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, price REAL, cost_price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS ingredients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, unit TEXT, current_stock REAL, min_required REAL, cost_per_unit REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS recipes (menu_item_id INTEGER, ingredient_id INTEGER, amount REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT, subtotal REAL, tax REAL, tip REAL, discount REAL, grand_total REAL, date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, menu_item_id INTEGER, qty INTEGER, item_price REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT, amount REAL, category TEXT, date TEXT)')

    cursor.execute("SELECT COUNT(*) FROM menu")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO menu (name, category, price, cost_price) VALUES ('Wagyu Burger', 'Mains', 15.00, 5.50), ('Truffle Pizza', 'Mains', 18.50, 6.20), ('Iced Latte', 'Drinks', 5.50, 1.20)")
        cursor.execute("INSERT INTO ingredients (name, unit, current_stock, min_required, cost_per_unit) VALUES ('Wagyu Beef', 'kg', 25.0, 5.0, 45.0), ('Brioche Bun', 'unit', 60, 15, 0.8), ('Pizza Dough', 'unit', 40, 10, 1.2)")
        cursor.execute("INSERT INTO recipes VALUES (1, 1, 0.2), (1, 2, 1.0), (2, 3, 1.0)")
    conn.commit()
    conn.close()

init_db()# --- 3. ADVANCED ML FORECASTING ENGINE ---
def forecast_inventory(conn):
    try:
        # 1. Fetch daily sales data
        query = "SELECT date(date) as day, SUM(grand_total) as daily_sales FROM orders GROUP BY day ORDER BY day"
        df = pd.read_sql_query(query, conn)
        
        # Not enough data fallback
        if len(df) < 3:
            empty_df = pd.DataFrame(columns=['day', 'daily_sales', 'type'])
            return empty_df, empty_df, empty_df

        # 2. Train the Machine Learning Model (Linear Regression)
        df['day_index'] = range(len(df))
        X = df[['day_index']]
        y = df['daily_sales']
        model = LinearRegression().fit(X, y)
        
        # 3. Predict the next 7 days
        future_steps = [[len(df) + i] for i in range(7)]
        predictions = model.predict(future_steps)
        
        last_date = pd.to_datetime(df['day'].iloc[-1])
        future_dates = [(last_date + datetime.timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(7)]
        
        # 4. Format DataFrames for Plotly
        recent_df = df[['day', 'daily_sales']].copy()
        recent_df['type'] = 'Actual Sales'
        
        future_df = pd.DataFrame({'day': future_dates, 'daily_sales': predictions, 'type': 'Predicted Sales'})
        
        # Prevent negative predictions
        future_df['daily_sales'] = future_df['daily_sales'].apply(lambda x: max(0, x)) 
        
        full_df = pd.concat([recent_df, future_df])
        
        return recent_df, future_df, full_df
    
    except Exception as e:
        # Failsafe if tables are missing or empty
        empty_df = pd.DataFrame(columns=['day', 'daily_sales', 'type'])
        return empty_df, empty_df, empty_df

# --- 3. PDF RECEIPT GENERATOR ---
def generate_receipt(order_id, customer, cart, subtotal, tax, tip, discount, grand_total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="ChefIntel Pro Restaurant", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Order #{order_id} | Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.cell(200, 10, txt=f"Customer: {customer}", ln=True, align='C')
    pdf.cell(200, 10, txt="-"*50, ln=True, align='C')
    
    for item in cart:
        pdf.cell(200, 8, txt=f"{item['qty']}x {item['name']} ..... ${item['total']:.2f}", ln=True, align='C')
    
    pdf.cell(200, 10, txt="-"*50, ln=True, align='C')
    pdf.cell(200, 8, txt=f"Subtotal: ${subtotal:.2f}", ln=True, align='C')
    pdf.cell(200, 8, txt=f"Tax: ${tax:.2f} | Tip: ${tip:.2f} | Discount: -${discount:.2f}", ln=True, align='C')
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"GRAND TOTAL: ${grand_total:.2f}", ln=True, align='C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 10, txt="Thank you for dining with us!", ln=True, align='C')
    
    return pdf.output(dest='S').encode('latin-1')

# --- 4. SIDEBAR: ADVANCED POS ---
st.sidebar.title("💳 Digital POS")
customer = st.sidebar.text_input("Customer Name", "Walk-in Guest")

conn = sqlite3.connect('restaurant.db')
menu_df = pd.read_sql_query("SELECT * FROM menu", conn)

with st.sidebar.expander("🍔 Add Menu Items", expanded=True):
    if not menu_df.empty:
        cat = st.selectbox("Category", menu_df['category'].unique())
        filtered_menu = menu_df[menu_df['category'] == cat]
        item_name = st.selectbox("Select Item", filtered_menu['name'])
        qty = st.number_input("Qty", min_value=1, value=1)
        
        # Touch-friendly button
        if st.button("➕ Add to Order", use_container_width=True):
            info = menu_df[menu_df['name'] == item_name].iloc[0]
            st.session_state.cart.append({
                'id': int(info['id']), 'name': item_name, 'qty': qty, 
                'price': info['price'], 'total': info['price'] * qty
            })
            st.toast(f"Added {item_name}!")

if st.session_state.cart:
    st.sidebar.markdown("---")
    subtotal = sum(item['total'] for item in st.session_state.cart)
    
    tax_rate = st.sidebar.slider("Tax Rate (%)", 0, 20, 10)
    col_d, col_t = st.sidebar.columns(2)
    discount_val = col_d.number_input("Discount ($)", min_value=0.0, step=1.0)
    tip_val = col_t.number_input("Tip ($)", min_value=0.0, step=1.0)
    
    tax_total = (subtotal * tax_rate / 100)
    grand_total = max(0, (subtotal + tax_total + tip_val) - discount_val)
    
    st.sidebar.write(f"**Subtotal:** `${subtotal:.2f}`")
    st.sidebar.write(f"**Grand Total:** `${grand_total:.2f}`")

    if st.sidebar.button("🚀 Finalize Transaction", type="primary", use_container_width=True):
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save Order
        cursor.execute("INSERT INTO orders (customer_name, subtotal, tax, tip, discount, grand_total, date) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                       (customer, subtotal, tax_total, tip_val, discount_val, grand_total, now))
        order_id = cursor.lastrowid
        
        # Deduct Stock & Save Items
        for item in st.session_state.cart:
            cursor.execute("INSERT INTO order_items (order_id, menu_item_id, qty, item_price) VALUES (?, ?, ?, ?)", 
                           (order_id, item['id'], item['qty'], item['price']))
            cursor.execute('''UPDATE ingredients SET current_stock = current_stock - (SELECT amount * ? FROM recipes WHERE ingredient_id = ingredients.id AND menu_item_id = ?) WHERE id IN (SELECT ingredient_id FROM recipes WHERE menu_item_id = ?)''', (item['qty'], item['id'], item['id']))
        
        conn.commit()
        
        # Generate PDF
        pdf_bytes = generate_receipt(order_id, customer, st.session_state.cart, subtotal, tax_total, tip_val, discount_val, grand_total)
        st.session_state.last_receipt = pdf_bytes
        st.session_state.cart = []
        st.toast("✅ Payment Successful!")
        st.rerun()

    if st.sidebar.button("🗑️ Clear Order", use_container_width=True):
        st.session_state.cart = []
        st.rerun()

# Show PDF Download Button if available
if st.session_state.last_receipt:
    st.sidebar.download_button(label="📥 Download Last Receipt (PDF)", data=st.session_state.last_receipt, file_name="receipt.pdf", mime="application/pdf", use_container_width=True)

# --- 5. MAIN DASHBOARD ---
t1, t2, t3, t4, t5 = st.tabs(["📈 Financials", "🥗 Stock Room", "📋 Menu Studio", "💸 Expenses", "⚙️ Admin"])

with t1:
    st.header("Executive Financial Summary")
    orders_df = pd.read_sql_query("SELECT * FROM orders", conn)
    
    if not orders_df.empty:
        total_rev = orders_df['grand_total'].sum()
        cogs = conn.execute("SELECT SUM(oi.qty * m.cost_price) FROM order_items oi JOIN menu m ON oi.menu_item_id = m.id").fetchone()[0] or 0
        op_exp = conn.execute("SELECT SUM(amount) FROM expenses").fetchone()[0] or 0
        net_profit = total_rev - cogs - op_exp - orders_df['tax'].sum()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Gross Revenue", f"${total_rev:.2f}")
        m2.metric("Cost of Goods", f"${cogs:.2f}")
        m3.metric("Net Profit", f"${net_profit:.2f}")
        m4.metric("Tips Collected", f"${orders_df['tip'].sum():.2f}")

        orders_df['date'] = pd.to_datetime(orders_df['date'])
        daily_sales = orders_df.set_index('date').resample('D')['grand_total'].sum()
        st.line_chart(daily_sales)
    else:
        st.info("No sales data available yet.")

with t2:
    st.header("Inventory Management")
    stock_data = pd.read_sql_query("SELECT id, name, current_stock, unit, min_required FROM ingredients", conn)
    st.data_editor(stock_data, use_container_width=True, hide_index=True)

with t3:
    st.header("Menu & Recipe Engineering")
    col_menu, col_recipe = st.columns([1, 1])
    
    with col_menu:
        st.subheader("Create New Dish")
        with st.form("new_item"):
            n_name = st.text_input("Item Name")
            n_cat = st.selectbox("Category", ["Mains", "Starters", "Drinks", "Desserts"])
            n_price = st.number_input("Selling Price ($)", min_value=0.0)
            n_cost = st.number_input("Estimated Cost ($)", min_value=0.0)
            if st.form_submit_button("Save to Menu"):
                conn.execute("INSERT INTO menu (name, category, price, cost_price) VALUES (?,?,?,?)", (n_name, n_cat, n_price, n_cost))
                conn.commit()
                st.success(f"{n_name} added!")
                st.rerun()
                
    with col_recipe:
        st.subheader("Link Ingredient to Dish")
        m_list = pd.read_sql_query("SELECT id, name FROM menu", conn)
        i_list = pd.read_sql_query("SELECT id, name FROM ingredients", conn)
        if not m_list.empty and not i_list.empty:
            sel_m = st.selectbox("Select Dish", m_list['name'])
            sel_i = st.selectbox("Select Ingredient", i_list['name'])
            amt = st.number_input("Amount used per portion", min_value=0.01)
            if st.button("Link Recipe"):
                mid = m_list[m_list['name'] == sel_m]['id'].values[0]
                iid = i_list[i_list['name'] == sel_i]['id'].values[0]
                conn.execute("INSERT INTO recipes VALUES (?,?,?)", (int(mid), int(iid), amt))
                conn.commit()
                st.success("Recipe Linked successfully!")

with t4:
    st.header("Operating Expenses")
    with st.form("exp"):
        desc = st.text_input("Expense Description (e.g. Electricity)")
        amt_e = st.number_input("Amount ($)", min_value=0.0)
        cat_e = st.selectbox("Category", ["Rent", "Utilities", "Marketing", "Payroll", "Other"])
        if st.form_submit_button("Log Expense"):
            conn.execute("INSERT INTO expenses (description, amount, category, date) VALUES (?,?,?,?)", 
                         (desc, amt_e, cat_e, datetime.datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            st.success("Expense logged!")
            st.rerun()
    st.dataframe(pd.read_sql_query("SELECT * FROM expenses", conn), use_container_width=True)

with t5:
    st.header("System Administration")
    st.warning("⚠️ These actions cannot be undone.")
    if st.button("🚨 Wipe All Sales & Expense Data", type="primary"):
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM order_items")
        conn.execute("DELETE FROM expenses")
        conn.commit()
        st.session_state.last_receipt = None
        st.success("Database history cleared for a new financial period.")
        st.rerun()

conn.close()