import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
import sqlite3
import bcrypt
import re

conn = sqlite3.connect("finance_app.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date TEXT,
    details TEXT,
    amount REAL,
    type TEXT,
    category TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS user_budgets (
    user_id INTEGER,
    category TEXT,
    amount_budgeted REAL,
    PRIMARY KEY (user_id, category)
)
""")
conn.commit()

def hash_pw(pw):
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_pw(pw, hashed):
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(pw.encode('utf-8'), hashed)

def strong_pw(pw):
    return bool(re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$", pw))

def register_user(username, password):
    if not username or not password:
        return "empty"'
        
    clean_username = username.strip().lower()
    
    try:
        if not strong_pw(password):
            return "weak"
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (clean_username, hash_pw(password)))
        conn.commit()
        return "ok"
    except sqlite3.IntegrityError:
        return "duplicate"

def login_user(username, password):
    if not username or not password:
        return None
        
    clean_username = username.strip().lower()
    c.execute("SELECT id, password FROM users WHERE username=?", (clean_username,))
    user = c.fetchone()
    
    if user and check_pw(password, user[1]):
        return user[0]
    return None

if "user_id" not in st.session_state:
    st.session_state.user_id = None

category_file = "categories.json"

if "categories" not in st.session_state:
    st.session_state.categories = {"Uncategorized": []}

def save_categories():
    """Strictly saves categories mapped only to the current logged-in user_id."""
    all_cats = {}
    if os.path.exists(category_file):
        try:
            with open(category_file, "r") as f:
                all_cats = json.load(f)
        except Exception:
            all_cats = {}
            
    if st.session_state.user_id is not None:
        all_cats[str(st.session_state.user_id)] = st.session_state.categories
    
    with open(category_file, "w") as f:
        json.dump(all_cats, f, indent=4)

def add_keyword_to_category(category, keyword):
    """Adds a keyword to JSON for future auto-categorization."""
    keyword = str(keyword).strip().lower()
    if keyword and keyword not in [k.lower() for k in st.session_state.categories.get(category, [])]:
        st.session_state.categories[category].append(keyword)
        save_categories()

def fetch_transaction_data(user_id, cursor):
    """Fetches all transactions for the user and converts them to a DataFrame."""
    cursor.execute(
        "SELECT date, amount, type, category FROM transactions WHERE user_id = ?", 
        (user_id,)
    )
    rows = cursor.fetchall()
    
    df = pd.DataFrame(rows, columns=["Date", "Amount", "Type", "Category"])
    return df

def create_income_vs_expense_chart(df):
    """Processes the DataFrame and creates a grouped double bar graph."""
    if df.empty:
        return None
        
   
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    
   
    df["Month"] = df["Date"].dt.to_period("M").astype(str)
    
    
    summary_df = df.groupby(["Month", "Type"])["Amount"].sum().reset_index()
    

    fig = px.bar(
        summary_df,
        x="Month",
        y="Amount",
        color="Type",
        barmode="group", 
        title="Monthly Income vs. Expenses",
        labels={"Amount": "Total Amount", "Month": "Time Period", "Type": "Transaction Type"},
        color_discrete_map={"Income": "#2ecc71", "Expense": "#e74c3c"}
    )
    
    fig.update_layout(
        xaxis_tickangle=-45,
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=(dict(showgrid=True, gridcolor='lightgray'))
    )
    
    return fig


def create_expense_pie_chart(df):
    """Filters for expenses and creates a pie chart by category."""
    if df.empty:
        return None
        

    expense_df = df[df["Type"].str.strip().str.title() == "Expense"]
    
    if expense_df.empty:
        return None
        
    
    category_totals = expense_df.groupby("Category")["Amount"].sum().reset_index()
    
    
    fig = px.pie(
        category_totals,
        values="Amount",
        names="Category",
        title="Expense Breakdown by Category",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Pastel 
    )
    
   
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)")
    
    return fig

def categorize_transactions(df):
    """Auto-categorizes based on the active user's JSON dictionary."""
    df["Category"] = "Uncategorized"
    
    for category, keywords in st.session_state.categories.items():
        if category == "Uncategorized" or not keywords:
            continue
        
        lowered_keywords = [str(keyword).lower().strip() for keyword in keywords]
        
        for idx, row in df.iterrows():
            details = str(row.get("Details", "")).lower().strip()
            
           
            if str(row.get("Debit/Credit", "")).strip().title() == "Credit":
                df.at[idx, "Category"] = "Income"
                continue
                
            
            for kw in lowered_keywords:
                if kw in details:
                    df.at[idx, "Category"] = category
                    break
    return df

def load_transactions(file):
    try:
        df = pd.read_csv(file)
        df.columns = [col.strip() for col in df.columns]
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce") 
        df = categorize_transactions(df)
        df = df.sort_values(by="Date", ascending=True).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None

if st.session_state.user_id is None:
    st.title("Welcome to Finance App 📊")
    st.markdown("Please log in or register an account to access your isolated workspace.")
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.header("🔐 Login")
        with st.form("login_form", clear_on_submit=True):
            login_username = st.text_input("Username")
            login_password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", width="stretch"):
                if not login_username.strip() or not login_password:
                    st.error("Please enter both a username and password.")
                else:
                    uid = login_user(login_username, login_password)
                    if uid:
                        st.session_state.user_id = uid
                        st.success("Access granted! Loading dashboard...")
                        st.rerun()
                    else:
                        st.error("Access denied: Invalid username or password.")

    with col2:
        st.header("📝 Register")
        with st.form("register_form", clear_on_submit=True):
            reg_username = st.text_input("Choose a Username")
            reg_password = st.text_input("Choose a Password", type="password", help="8+ chars, 1 uppercase, 1 lowercase, 1 number")
            if st.form_submit_button("Create Account", width="stretch"):
                if not reg_username.strip() or not reg_password:
                    st.error("Please fill out both fields.")
                else:
                    result = register_user(reg_username, reg_password)
                    if result == "empty":
                        st.error("Fields cannot be empty or just spaces.")
                    elif result == "weak":
                        st.warning("Weak password: Must be 8+ characters and contain an uppercase, lowercase, and number.")
                    elif result == "duplicate":
                        st.error("Username already exists. Please choose another.")
                    else:
                        st.success("Account created successfully! You can now log in.")
    st.stop()

if st.session_state.user_id is not None:
    uid_key = str(st.session_state.user_id)
    all_user_categories = {}
    if os.path.exists(category_file):
        try:
            with open(category_file, "r") as f:
                all_user_categories = json.load(f)
        except:
            all_user_categories = {}
            
    if uid_key not in all_user_categories or not isinstance(all_user_categories[uid_key], dict):
        all_user_categories[uid_key] = {"Uncategorized": []}
        with open(category_file, "w") as f:
            json.dump(all_user_categories, f)
            
    if st.session_state.get("active_user_context_id") != uid_key:
        st.session_state.categories = all_user_categories[uid_key]
        st.session_state["active_user_context_id"] = uid_key
        st.rerun()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Menu", ["Budget Ledger", "CSV Import", "Account"])

    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    if page == "Budget Ledger":
        st.title("📊 Database Transaction Ledger")
        st.markdown("---")
        
        st.header("🗂️ Category Configuration")
        c1, c2, c3 = st.columns(3)
        
        with c1:
            new_cat_input = st.text_input("Create Category Name").strip()
            if st.button("Add New Category", width="stretch"):
                if new_cat_input and new_cat_input not in st.session_state.categories:
                    st.session_state.categories[new_cat_input] = []
                    save_categories()
                    c.execute("INSERT OR IGNORE INTO user_budgets (user_id, category, amount_budgeted) VALUES (?, ?, ?)", (st.session_state.user_id, new_cat_input, 0.0))
                    conn.commit()
                    st.success(f"'{new_cat_input}' added!")
                    st.rerun()
                        
        with c2:
            custom_cats = [k for k in st.session_state.categories.keys() if k != "Uncategorized"]
            cat_to_rename = st.selectbox("Rename Target", options=custom_cats)
            rename_target_val = st.text_input("New Name").strip()
            if st.button("Apply New Name", width="stretch") and cat_to_rename and rename_target_val:
                st.session_state.categories[rename_target_val] = st.session_state.categories.pop(cat_to_rename)
                save_categories()
                c.execute("UPDATE user_budgets SET category = ? WHERE user_id = ? AND category = ?", (rename_target_val, st.session_state.user_id, cat_to_rename))
                c.execute("UPDATE transactions SET category = ? WHERE user_id = ? AND category = ?", (rename_target_val, st.session_state.user_id, cat_to_rename))
                conn.commit()
                st.success("Updates reflected in database.")
                st.rerun()
                        
        with c3:
            cat_to_delete = st.selectbox("Delete Target", options=custom_cats)
            if st.button("Remove Category", width="stretch") and cat_to_delete:
                c.execute("UPDATE transactions SET category = 'Uncategorized' WHERE user_id = ? AND category = ?", (st.session_state.user_id, cat_to_delete))
                c.execute("DELETE FROM user_budgets WHERE user_id = ? AND category = ?", (st.session_state.user_id, cat_to_delete))
                conn.commit()
                st.session_state.categories.pop(cat_to_delete, None)
                save_categories()
                st.success("Category cleared.")
                st.rerun()

        st.markdown("---")
        st.header("🗎 Edit Database Records")
        st.caption("Double-click any cell to update database records.")
        
        c.execute("SELECT id, date, details, amount, type, category FROM transactions WHERE user_id = ? ORDER BY date DESC", (st.session_state.user_id,))
        raw_rows = c.fetchall()
        df_ledger_base = pd.DataFrame(raw_rows, columns=["id", "Date", "Details", "Amount", "Type", "Category"])
        df_ledger_base["Date"] = pd.to_datetime(df_ledger_base["Date"], errors='coerce')
        
        edited_ledger = st.data_editor(
            df_ledger_base,
            column_config={
                "id": None,
                "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", required=True),
                "Details": st.column_config.TextColumn("Details", required=True),
                "Amount": st.column_config.NumberColumn("Amount", min_value=0.0, format="%.2f CAD", required=True),
                "Type": st.column_config.SelectboxColumn("Type", options=["Income", "Expense"], required=True),
                "Category": st.column_config.SelectboxColumn("Category", options=list(st.session_state.categories.keys()), required=True)
            },
            num_rows="dynamic", width="stretch", hide_index=True, key="ledger_data_grid_manager"
        )
        
        if "ledger_data_grid_manager" in st.session_state:
            tx_changes = st.session_state.ledger_data_grid_manager
            state_mutated = False
            
            if tx_changes.get("deleted_rows"):
                for del_idx in tx_changes["deleted_rows"]:
                    target_del_id = int(df_ledger_base.iloc[del_idx]["id"])
                    c.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (target_del_id, st.session_state.user_id))
                state_mutated = True
                
            if tx_changes.get("edited_rows"):
                for edit_idx_str, updated_cols in tx_changes["edited_rows"].items():
                    edit_idx_val = int(edit_idx_str)
                    target_update_id = int(df_ledger_base.iloc[edit_idx_val]["id"])
                    for field_col, new_field_val in updated_cols.items():
                        if field_col == "Date":
                            new_field_val = pd.to_datetime(new_field_val).strftime('%Y-%m-%d')
                        c.execute(f"UPDATE transactions SET {field_col.lower()} = ? WHERE id = ? AND user_id = ?", (new_field_val, target_update_id, st.session_state.user_id))
                state_mutated = True
                
            if tx_changes.get("added_rows"):
                for row in tx_changes["added_rows"]:
                    dt_val = pd.to_datetime(row.get("Date", pd.Timestamp.now())).strftime('%Y-%m-%d')
                    c.execute("INSERT INTO transactions (user_id, date, details, amount, type, category) VALUES (?, ?, ?, ?, ?, ?)", 
                            (st.session_state.user_id, dt_val, row.get("Details", "New"), row.get("Amount", 0.0), row.get("Type", "Expense"), row.get("Category", "Uncategorized")))
                state_mutated = True

            if state_mutated:
                conn.commit()
                st.rerun()
        
        st.header("📊 Financial Dashboard")
        df_chart_data = fetch_transaction_data(st.session_state.user_id, c)
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            bar_fig = create_income_vs_expense_chart(df_chart_data)
            if bar_fig is not None:
                st.plotly_chart(bar_fig, width="stretch")
            else:
                st.info("Upload transactions to see your Cash Flow.")

        with chart_col2:

            pie_fig = create_expense_pie_chart(df_chart_data)
            if pie_fig is not None:
                st.plotly_chart(pie_fig, width="stretch")
            else:
                st.info("Add expense transactions to see your Category Breakdown.")
       
    elif page == "CSV Import":
        st.title("📂 Bulk CSV Transaction Import")
        
        
        st.subheader("Manage Categories")
        col_cat, col_btn = st.columns([3, 1])
        with col_cat:
            new_cat_input = st.text_input("Add a new category", placeholder="e.g., Entertainment")
        with col_btn:
            st.write("") 
            st.write("")
            if st.button("Add Category", width="stretch"):
                clean_cat = new_cat_input.strip()
                if clean_cat and clean_cat not in st.session_state.categories:
                    st.session_state.categories[clean_cat] = []
                    save_categories()
                    st.success(f"Category '{clean_cat}' added to your profile!")
                    st.rerun()
                elif clean_cat in st.session_state.categories:
                    st.warning("Category already exists.")
                    
        st.markdown("---")

        uploaded_file = st.file_uploader("Upload Bank CSV File", type=["csv"])
        
        if uploaded_file is not None:
            st.success("✅ CSV Accepted! Processing and pre-sorting by date...")
            
            try:
                df = pd.read_csv(uploaded_file)
                df.columns = [col.strip() for col in df.columns]
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce") 
                df = df.sort_values(by="Date", ascending=True).reset_index(drop=True)
                
                df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
                
                df["Category"] = "Uncategorized"
                
                for idx, row in df.iterrows():
                    details = str(row.get("Details", "")).upper().strip()
                    
                    assigned = False
                    for cat, keywords in st.session_state.categories.items():
                        if cat == "Uncategorized": continue
                        for kw in keywords:
                            if kw.upper() in details:
                                df.at[idx, "Category"] = cat
                                assigned = True
                                break
                        if assigned:
                            break
                
                st.subheader("Review & Edit Categories")
                st.write("Make any manual adjustments below. When ready, save to your database.")
                
                edited_df = st.data_editor(
                    df,
                    column_config={
                        "Category": st.column_config.SelectboxColumn("Category", options=list(st.session_state.categories.keys()))
                    },
                    width='stretch',
                    hide_index=True
                )
                
                
                if st.button("💾 Save Transactions to Database", type="primary"):
                    records_added = 0
                    
                    for _, row in edited_df.iterrows():
                        
                        tx_type = "Expense"
                        if "Debit/Credit" in row:
                            tx_type = "Expense" if str(row.get("Debit/Credit")).strip().title() == "Debit" else "Income"
                        elif "Amount" in row and float(row["Amount"]) > 0 and "Type" not in row:
                            
                            tx_type = "Expense" 
                        
                        tx_cat = row.get("Category", "Uncategorized")
                        date_str = row["Date"]
                        details = row.get("Details", "")
                        amount = float(row.get("Amount", 0.0))
                        
                       
                        c.execute("SELECT id FROM transactions WHERE user_id=? AND date=? AND details=? AND amount=? AND type=?", 
                                (st.session_state.user_id, date_str, details, amount, tx_type))
                        
                        if not c.fetchone():
                            c.execute("INSERT INTO transactions (user_id, date, details, amount, type, category) VALUES (?, ?, ?, ?, ?, ?)", 
                                    (st.session_state.user_id, date_str, details, amount, tx_type, tx_cat))
                            records_added += 1
                            
                           
                            add_keyword_to_category(tx_cat, details)
                    
                    conn.commit()
                    if records_added > 0:
                        st.success(f"🎉 Successfully saved {records_added} new transactions to your database! They are now accessible in the Ledger.")
                    else:
                        st.info("No new transactions were added (duplicates were skipped).")
                        
            except Exception as e:
                st.error(f"Error reading CSV format: {e}. Please ensure your CSV has 'Date', 'Details', and 'Amount' columns.")
   
    elif page == "Account":
        st.title("⚙️ Account Settings")
        c.execute("SELECT username FROM users WHERE id=?", (st.session_state.user_id,))
        username_result = c.fetchone()
        current_username = username_result[0] if username_result else 'Unknown'
        
        st.subheader("Data Overview")
        c.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE user_id=? AND type='Expense'", (st.session_state.user_id,))
        exp_stats = c.fetchone()
        st.write(f"**Username:** {current_username}")
        st.write(f"**Database User ID:** {st.session_state.user_id}")
        st.write(f"**Total Transaction Records:** {exp_stats[0]}")
        
        st.markdown("---")
        st.subheader("Update Information")
        with st.form("update_info_form"):
            new_username = st.text_input("New Username", value=current_username)
            new_password = st.text_input("New Password (Leave blank to keep current)", type="password")
            
            if st.form_submit_button("Update Profile"):
                try:
                    if new_username != current_username:
                        c.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, st.session_state.user_id))
                    
                    if new_password:
                        if not strong_pw(new_password):
                            st.error("Password must be 8+ chars with an uppercase, lowercase, and number.")
                        else:
                            c.execute("UPDATE users SET password = ? WHERE id = ?", (hash_pw(new_password), st.session_state.user_id))
                    
                    conn.commit()
                    st.success("Profile updated successfully!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Username already taken. Choose another.")

        st.markdown("---")
        st.subheader("🚨 Danger Zone")
        st.error("Deleting your account will permanently wipe all transactions, budgets, and JSON categories associated with your User ID. This cannot be undone.")
        
        delete_confirm = st.checkbox("I understand that my data will be permanently destroyed.")
        if st.button("Delete Account & All Data", type="primary", disabled=not delete_confirm):
            c.execute("DELETE FROM users WHERE id=?", (st.session_state.user_id,))
            c.execute("DELETE FROM transactions WHERE user_id=?", (st.session_state.user_id,))
            c.execute("DELETE FROM user_budgets WHERE user_id=?", (st.session_state.user_id,))
            conn.commit()
            
            if os.path.exists(category_file):
                with open(category_file, "r") as f:
                    all_user_cats = json.load(f)
                if str(st.session_state.user_id) in all_user_cats:
                    del all_user_cats[str(st.session_state.user_id)]
                    with open(category_file, "w") as f:
                        json.dump(all_user_cats, f, indent=4)
            
    
            st.session_state.clear()
            st.success("Account and all associated data have been permanently deleted.")
            st.rerun()
