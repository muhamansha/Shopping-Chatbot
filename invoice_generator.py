import tkinter as tk
from tkinter import ttk, messagebox
from docxtpl import DocxTemplate
from num2words import num2words
import datetime
import json
import os
import sys


VAT_RATE = 0.05                     
DEFAULT_ADMIN_PASSWORD = "123admin"
CURRENCY_MAIN = "Dirhams"
CURRENCY_SUB = "Fils"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INVOICE_FOLDER = os.path.join(BASE_DIR, "Invoices")


def file_path(name):
    return os.path.join(BASE_DIR, name)


def read_json(name, default):
    try:
        with open(file_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(name, data):
    with open(file_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_users():
    users = read_json("users_data.json", {})
    if "Admin" not in users:
        users["Admin"] = DEFAULT_ADMIN_PASSWORD
        write_json("users_data.json", users)
    return users


def peek_invoice_number():
    """Returns (date_string, count) for the NEXT invoice, without saving."""
    today = datetime.datetime.now().strftime("%Y%m%d")
    data = read_json("invoice_counter.json", {"date": "", "count": 0})
    if data.get("date") == today:
        count = data.get("count", 0) + 1
    else:
        count = 1
    return today, count


def format_invoice_number(today, count):
    return f"{today}-{count:03d}"


def amount_in_words(amount):
    """105.50 -> 'One Hundred And Five Dirhams And Fifty Fils Only'"""
    cents = round(amount * 100)
    main, sub = divmod(cents, 100)
    words = num2words(main).title() + " " + CURRENCY_MAIN
    if sub:
        words += " And " + num2words(sub).title() + " " + CURRENCY_SUB
    return words + " Only"




def main_app():

    invoice_list = []
    stock_items = read_json("stock_data.json", {})
    customers = read_json("customers_data.json", {})

    # ---------- dropdown helpers ---------- #

    def load_stock_dropdown():
        desc_combo['values'] = list(stock_items.keys())

    def load_customer_dropdown():
        first_name_combo['values'] = list(customers.keys())

    # ---------- stock ---------- #

    def add_to_stock():
        stock_window = tk.Toplevel(window)
        stock_window.title("Add Item to Stock")
        stock_window.config(bg="#e6f2ff")
        w, h = 350, 200
        x = (stock_window.winfo_screenwidth() // 2) - (w // 2)
        y = (stock_window.winfo_screenheight() // 2) - (h // 2)
        stock_window.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(stock_window, text="Item Name", bg="#e6f2ff").pack(pady=5)
        item_name_entry = tk.Entry(stock_window, width=30)
        item_name_entry.pack()

        tk.Label(stock_window, text="Price", bg="#e6f2ff").pack(pady=5)
        item_price_entry = tk.Entry(stock_window, width=30)
        item_price_entry.pack()

        def save_stock_item():
            name = item_name_entry.get().strip()
            price = item_price_entry.get().strip()

            if not name or not price:
                messagebox.showerror("Error", "Please fill all fields", parent=stock_window)
                return
            try:
                stock_items[name] = float(price)
            except ValueError:
                messagebox.showerror("Error", "Price must be a number", parent=stock_window)
                return

            write_json("stock_data.json", stock_items)
            load_stock_dropdown()
            messagebox.showinfo("Success", f"{name} added to stock!", parent=stock_window)
            stock_window.destroy()

        tk.Button(stock_window, text="Save Item", bg="green", fg="white",
                  width=15, command=save_stock_item).pack(pady=15)

    def on_item_select(event):
        selected = desc_combo.get()
        if selected in stock_items:
            price_spinbox.delete(0, tk.END)
            price_spinbox.insert(0, str(stock_items[selected]))

    

    def add_customer():
        cw = tk.Toplevel(window)
        cw.title("Add Customer")
        cw.config(bg="#e6f2ff")
        w, h = 350, 260
        x = (cw.winfo_screenwidth() // 2) - (w // 2)
        y = (cw.winfo_screenheight() // 2) - (h // 2)
        cw.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(cw, text="Customer Full Name", bg="#e6f2ff").pack(pady=5)
        name_entry = tk.Entry(cw, width=30)
        name_entry.pack()

        tk.Label(cw, text="Phone", bg="#e6f2ff").pack(pady=5)
        phone_e = tk.Entry(cw, width=30)
        phone_e.pack()

        tk.Label(cw, text="TRN Number", bg="#e6f2ff").pack(pady=5)
        trn_e = tk.Entry(cw, width=30)
        trn_e.pack()

        def save_customer():
            name = name_entry.get().strip()
            phone = phone_e.get().strip()
            trn = trn_e.get().strip()

            if not name:
                messagebox.showerror("Error", "Customer name is required", parent=cw)
                return

            customers[name] = {"phone": phone, "trn": trn}
            write_json("customers_data.json", customers)
            load_customer_dropdown()
            messagebox.showinfo("Success", f"{name} added to customers!", parent=cw)
            cw.destroy()

        tk.Button(cw, text="Save Customer", bg="green", fg="white",
                  width=15, command=save_customer).pack(pady=15)

    def on_customer_select(event):
        full_name = first_name_combo.get()
        if full_name in customers:
            parts = full_name.split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""

            first_name_combo.set(first)
            last_name_entry.delete(0, tk.END)
            last_name_entry.insert(0, last)

            phone_entry.delete(0, tk.END)
            phone_entry.insert(0, customers[full_name].get("phone", ""))

            trn_entry.delete(0, tk.END)
            trn_entry.insert(0, customers[full_name].get("trn", ""))

    

    def clear_item():
        qty_spinbox.delete(0, tk.END)
        qty_spinbox.insert(0, "1")
        desc_combo.set("")
        price_spinbox.delete(0, tk.END)
        price_spinbox.insert(0, "0.0")

    def refresh_tree():
        tree.delete(*tree.get_children())
        for i, item in enumerate(invoice_list, start=1):
            item[0] = i  
            tree.insert("", "end", values=(item[0], item[1], item[2],
                                           f"{item[3]:.2f}", f"{item[4]:.2f}"))

    def add_item():
        desc = desc_combo.get().strip()
        if not desc:
            messagebox.showerror("Error", "Please enter or select a description")
            return
        try:
            qty = int(qty_spinbox.get())
            price = float(price_spinbox.get())
        except ValueError:
            messagebox.showerror("Error", "Qty and Price must be numbers")
            return
        if qty <= 0 or price < 0:
            messagebox.showerror("Error", "Qty must be above 0 and Price cannot be negative")
            return

        invoice_list.append([len(invoice_list) + 1, desc, qty, price, qty * price])
        refresh_tree()
        clear_item()

    def delete_item():
        selected = tree.selection()
        if not selected:
            return
        indexes = sorted((tree.index(i) for i in selected), reverse=True)
        for index in indexes:
            invoice_list.pop(index)
        refresh_tree()

    

    def new_invoice():
        first_name_combo.set("")
        last_name_entry.delete(0, tk.END)
        phone_entry.delete(0, tk.END)
        trn_entry.delete(0, tk.END)

        today, count = peek_invoice_number()
        invoice_no_entry.delete(0, tk.END)
        invoice_no_entry.insert(0, format_invoice_number(today, count))

        date_entry.delete(0, tk.END)
        date_entry.insert(0, datetime.datetime.now().strftime("%d-%m-%Y"))

        invoice_list.clear()
        refresh_tree()
        clear_item()

    def generate_invoice():
        if len(invoice_list) == 0:
            messagebox.showerror("Error", "No items added")
            return

        template_path = file_path("invoice_format.docx")
        if not os.path.exists(template_path):
            messagebox.showerror("Error", "invoice_format.docx not found in the app folder")
            return

        doc = DocxTemplate(template_path)

        name = (first_name_combo.get() + " " + last_name_entry.get()).strip()
        invoice_no = invoice_no_entry.get().strip()

        subtotal = round(sum(item[4] for item in invoice_list), 2)
        vat = round(subtotal * VAT_RATE, 2)
        net_total = round(subtotal + vat, 2)

       
        items_for_doc = [
            [item[0], item[1], item[2], f"{item[3]:.2f}", f"{item[4]:.2f}"]
            for item in invoice_list
        ]

        doc.render({
            "invoice_number": invoice_no,
            "date": date_entry.get(),
            "customer_name": name,
            "customer_trn": trn_entry.get(),
            "phone": phone_entry.get(),
            "invoice_list": items_for_doc,
            "total_amount": f"{subtotal:.2f}",
            "vat_amount": f"{vat:.2f}",
            "total_words": amount_in_words(net_total),
            "net_total": f"{net_total:.2f}"
        })

        try:
            os.makedirs(INVOICE_FOLDER, exist_ok=True)
            file_name = os.path.join(INVOICE_FOLDER, f"Invoice_{invoice_no}.docx")
            doc.save(file_name)
        except PermissionError:
            messagebox.showerror("Error", "Cannot save. Close the invoice if it is open in Word and try again.")
            return

       
        today, count = peek_invoice_number()
        write_json("invoice_counter.json", {"date": today, "count": count})

        messagebox.showinfo("Success", f"Invoice generated!\n\nSaved in:\n{file_name}")
        new_invoice()



    window = tk.Tk()
    window.title("PRO TAX INVOICE SYSTEM")
    try:
        window.state("zoomed")            
    except tk.TclError:
        try:
            window.attributes("-zoomed", True)   
        except tk.TclError:
            window.attributes("-fullscreen", True)  
    window.config(bg="#e6f2ff")

    frame = tk.Frame(window, bg="#e6f2ff")
    frame.pack(padx=10, pady=10)

    # top buttons
    tk.Button(frame, text="➕ Add Item to Stock", bg="#28a745", fg="white",
              font=("Arial", 10, "bold"),
              command=add_to_stock).grid(row=0, column=0, columnspan=2, pady=5, sticky="we")

    tk.Button(frame, text="➕ Add Customer", bg="#17a2b8", fg="white",
              font=("Arial", 10, "bold"),
              command=add_customer).grid(row=0, column=2, columnspan=2, pady=5, sticky="we")

    
    tk.Label(frame, text="First Name (Type or Select)", bg="#e6f2ff").grid(row=1, column=0)
    tk.Label(frame, text="Last Name", bg="#e6f2ff").grid(row=1, column=1)
    tk.Label(frame, text="Phone", bg="#e6f2ff").grid(row=1, column=2)
    tk.Label(frame, text="TRN", bg="#e6f2ff").grid(row=1, column=3)

    first_name_combo = ttk.Combobox(frame)
    first_name_combo.bind("<<ComboboxSelected>>", on_customer_select)
    last_name_entry = tk.Entry(frame)
    phone_entry = tk.Entry(frame)
    trn_entry = tk.Entry(frame)

    first_name_combo.grid(row=2, column=0)
    last_name_entry.grid(row=2, column=1)
    phone_entry.grid(row=2, column=2)
    trn_entry.grid(row=2, column=3)

    
    tk.Label(frame, text="Invoice No", bg="#e6f2ff").grid(row=3, column=0)
    tk.Label(frame, text="Date", bg="#e6f2ff").grid(row=3, column=1)

    invoice_no_entry = tk.Entry(frame)
    today, count = peek_invoice_number()
    invoice_no_entry.insert(0, format_invoice_number(today, count))
    invoice_no_entry.grid(row=4, column=0)

    date_entry = tk.Entry(frame)
    date_entry.insert(0, datetime.datetime.now().strftime("%d-%m-%Y"))
    date_entry.grid(row=4, column=1)

    
    tk.Label(frame, text="Qty", bg="#e6f2ff").grid(row=5, column=0)
    tk.Label(frame, text="Description (Type or Select)", bg="#e6f2ff").grid(row=5, column=1)
    tk.Label(frame, text="Price", bg="#e6f2ff").grid(row=5, column=2)

    qty_spinbox = tk.Spinbox(frame, from_=1, to=100000, width=5)
    desc_combo = ttk.Combobox(frame, width=37)
    desc_combo.bind("<<ComboboxSelected>>", on_item_select)
    price_spinbox = tk.Spinbox(frame, from_=0.0, to=999999, increment=0.5)

    qty_spinbox.grid(row=6, column=0)
    desc_combo.grid(row=6, column=1)
    price_spinbox.grid(row=6, column=2)

    tk.Button(frame, text="Add Item", bg="black", fg="white",
              command=add_item, width=12).grid(row=6, column=3)

    
    columns = ("SL", "DESC", "QTY", "PRICE", "TOTAL")
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
    for col in columns:
        tree.heading(col, text=col)
    tree.grid(row=7, column=0, columnspan=4, pady=10)

    # bottom buttons
    tk.Button(frame, text="Delete Selected Item", bg="red", fg="white",
              command=delete_item).grid(row=8, column=0, columnspan=2, sticky="we")

    tk.Button(frame, text="Generate Invoice", bg="#1f4de3", fg="white",
              font=("Arial", 11, "bold"),
              command=generate_invoice).grid(row=8, column=2, columnspan=2, sticky="we")

    tk.Button(frame, text="New Invoice", bg="gray", fg="white",
              command=new_invoice).grid(row=9, column=0, columnspan=4, sticky="we")


    load_stock_dropdown()
    load_customer_dropdown()

    window.mainloop()




users_db = load_users()


def center_window(win, w, h):
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def add_new_user():
    win = tk.Toplevel(login_window)
    win.title("Add New User")
    win.config(bg="#e6f2ff")
    center_window(win, 400, 320)

    tk.Label(win, text="ADD NEW USER", font=("Arial", 14, "bold"),
             bg="#e6f2ff").pack(pady=15)

    tk.Label(win, text="Admin Password (for verification)", bg="#e6f2ff").pack()
    admin_pass_entry = tk.Entry(win, show="*", width=25)
    admin_pass_entry.pack(pady=5)

    tk.Label(win, text="New Username", bg="#e6f2ff").pack()
    new_username_entry = tk.Entry(win, width=25)
    new_username_entry.pack(pady=5)

    tk.Label(win, text="New Password", bg="#e6f2ff").pack()
    new_password_entry = tk.Entry(win, show="*", width=25)
    new_password_entry.pack(pady=5)

    def save_new_user():
        admin_pass = admin_pass_entry.get()
        new_user = new_username_entry.get().strip()
        new_pass = new_password_entry.get().strip()

   
        if admin_pass != users_db.get("Admin"):
            messagebox.showerror("Error", "Invalid Admin Password!", parent=win)
            return
        if not new_user or not new_pass:
            messagebox.showerror("Error", "Please fill all fields", parent=win)
            return
        if new_user in users_db:
            messagebox.showerror("Error", "Username already exists!", parent=win)
            return

        users_db[new_user] = new_pass
        write_json("users_data.json", users_db)
        messagebox.showinfo("Success", f"User '{new_user}' added!", parent=win)
        win.destroy()

    tk.Button(win, text="Add User", command=save_new_user,
              bg="green", fg="white", width=15).pack(pady=15)


def check_login():
    username = username_entry.get()
    password = password_entry.get()

    if username in users_db and users_db[username] == password:
        login_window.destroy()
        main_app()
    else:
        messagebox.showerror("Login Failed", "Invalid Username or Password")


login_window = tk.Tk()
login_window.title("Login - Pro Invoice App")
login_window.config(bg="#e6f2ff")
center_window(login_window, 400, 300)

tk.Label(login_window, text="LOGIN", font=("Arial", 16, "bold"),
         bg="#e6f2ff").pack(pady=15)

tk.Label(login_window, text="Username", bg="#e6f2ff").pack()
username_entry = tk.Entry(login_window)
username_entry.pack()

tk.Label(login_window, text="Password", bg="#e6f2ff").pack()
password_entry = tk.Entry(login_window, show="*")
password_entry.pack()
password_entry.bind("<Return>", lambda e: check_login())  

tk.Button(login_window, text="Login", command=check_login,
          bg="black", fg="white", width=15).pack(pady=10)

tk.Button(login_window, text="➕ Add New User", command=add_new_user,
          bg="#17a2b8", fg="white", width=15).pack()

login_window.mainloop()
