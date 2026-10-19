import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import hashlib
import hmac
import json
import math
import os
import re
import sys

# ================= SETTINGS ================= #

MIN_PASSWORD_LENGTH = 6
DEFAULT_UNIT = "1 piece"

# Same folder logic as the invoice app, so both apps share the same data files
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STOCK_FILE = "stock_data.json"          # {item: {"price": 6.0, "unit": "1 kg"}}  (shared with invoice app)
CUSTOMERS_FILE = "customers_data.json"  # {name: {phone, trn}}         (shared with invoice app)
APP_USERS_FILE = "login_users.json"     # {phone: name}                (invoice app logins)
ADMINS_FILE = "admin_users.json"        # {username: {salt, hash}}     (this app only)

# ================= DARK THEME ================= #

BG = "#0f1115"          # window background
SURFACE = "#171a21"     # cards / tables
SURFACE2 = "#1f232c"    # inputs / headers
BORDER = "#2b303b"
TEXT = "#e7e9ee"
MUTED = "#8a93a6"
ACCENT = "#6c8cff"
ACCENT_DARK = "#2f4fd0"
GREEN = "#22a55b"
RED = "#e5484d"
CYAN = "#1b9fb8"
ORANGE = "#e8832a"
PURPLE = "#7c5cd6"
GRAY = "#4a5163"

FONT = "Segoe UI"


def lighten(color, amount=0.15):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (int(c + (255 - c) * amount) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def apply_theme(root):
    root.config(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))
    style.configure("TFrame", background=BG)

    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    rowheight=30, borderwidth=0, font=(FONT, 10))
    style.map("Treeview", background=[("selected", ACCENT_DARK)],
              foreground=[("selected", "white")])
    style.configure("Treeview.Heading", background=SURFACE2, foreground=MUTED, relief="flat",
                    borderwidth=0, padding=(8, 8), font=(FONT, 9, "bold"))
    style.map("Treeview.Heading", background=[("active", BORDER)], foreground=[("active", TEXT)])

    style.configure("Vertical.TScrollbar", background=SURFACE2, troughcolor=BG, bordercolor=BG,
                    arrowcolor=MUTED, lightcolor=SURFACE2, darkcolor=SURFACE2, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", BORDER)])

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(18, 10),
                    borderwidth=0, font=(FONT, 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", SURFACE)],
              foreground=[("selected", ACCENT)])


def make_button(parent, text, color, command, width=None, size=10):
    b = tk.Button(parent, text=text, command=command, bg=color, fg="white",
                  activebackground=lighten(color, 0.2), activeforeground="white",
                  relief="flat", bd=0, padx=14, pady=7, cursor="hand2",
                  font=(FONT, size, "bold"), width=width or 0)
    b.bind("<Enter>", lambda e: b.config(bg=lighten(color, 0.12)))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


def make_entry(parent, width=30, show="", textvariable=None, font_size=10):
    return tk.Entry(parent, width=width, show=show, textvariable=textvariable, bg=SURFACE2, fg=TEXT,
                    insertbackground=TEXT, relief="flat", bd=0, font=(FONT, font_size),
                    highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
                    disabledbackground=SURFACE2)


# ================= DATA SAVE / LOAD ================= #

def file_path(name):
    return os.path.join(BASE_DIR, name)


def read_json(name, default):
    try:
        with open(file_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(name, data):
    # write to a temp file first so a crash can never leave a half-written file
    tmp = file_path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, file_path(name))


def find_key(dictionary, name):
    """Case-insensitive lookup. Returns the real key or None."""
    for k in dictionary:
        if k.lower() == name.lower():
            return k
    return None


def parse_price(text):
    try:
        value = float(str(text).replace(",", ""))
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def normalize_phone(phone):
    return re.sub(r"\D", "", phone)


# ================= STOCK ENTRIES =================
# New format : {"Apples": {"price": 6.0, "unit": "1 kg"}}
# Old format : {"Laptop": 2500.0}   (still understood, treated as "1 piece")

def stock_entry(value):
    """Returns (price, unit) for either stock format."""
    if isinstance(value, dict):
        price = parse_price(value.get("price", 0))
        unit = str(value.get("unit") or DEFAULT_UNIT).strip()
    else:
        price = parse_price(value)
        unit = DEFAULT_UNIT
    return (price if price is not None else 0.0), unit


def make_entry_value(price, unit):
    return {"price": round(price, 2), "unit": unit or DEFAULT_UNIT}


def is_per_kg(unit):
    return re.sub(r"\s+", "", str(unit).lower()) in ("1kg", "kg", "perkg", "/kg")


# ================= PASSWORDS (hashed, never stored as plain text) ================= #

def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt), 200_000).hex()
    return {"salt": salt, "hash": digest}


def verify_password(password, record):
    try:
        test = hash_password(password, record["salt"])["hash"]
        return hmac.compare_digest(test, record["hash"])
    except (KeyError, ValueError, TypeError):
        return False


# ================= REUSABLE FORM DIALOG ================= #

def center_window(win, w, h):
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def form_dialog(parent, title, fields, values=None, validate=None, note=None):
    """
    fields   : list of (label, is_secret)
    values   : optional starting values
    validate : function(list_of_values) -> error text or None
    note     : optional grey helper text shown under the title
    Returns the list of entered values, or None if cancelled.
    """
    result = {"v": None}
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.config(bg=SURFACE)
    dlg.transient(parent)
    dlg.resizable(False, False)

    tk.Label(dlg, text=title, bg=SURFACE, fg=TEXT, font=(FONT, 13, "bold")).pack(
        padx=26, pady=(20, 0), anchor="w")
    if note:
        tk.Label(dlg, text=note, bg=SURFACE, fg=MUTED, font=(FONT, 9), wraplength=320,
                 justify="left").pack(padx=26, pady=(4, 0), anchor="w")

    entries = []
    for i, (label, secret) in enumerate(fields):
        tk.Label(dlg, text=label, bg=SURFACE, fg=MUTED, font=(FONT, 9, "bold")).pack(
            padx=26, pady=(14, 3), anchor="w")
        e = make_entry(dlg, width=36, show="*" if secret else "")
        if values:
            e.insert(0, values[i])
        e.pack(padx=26, ipady=6, fill="x")
        entries.append(e)

    err = tk.Label(dlg, text="", fg="#ff7b80", bg=SURFACE, wraplength=320, justify="left",
                   font=(FONT, 9))
    err.pack(padx=26, pady=(10, 0), anchor="w")

    def ok(event=None):
        vals = [e.get().strip() for e in entries]
        if validate:
            msg = validate(vals)
            if msg:
                err.config(text=msg)
                return
        result["v"] = vals
        dlg.destroy()

    btns = tk.Frame(dlg, bg=SURFACE)
    btns.pack(pady=(10, 20), padx=26, fill="x")
    make_button(btns, "Save", GREEN, ok, width=10).pack(side="right")
    make_button(btns, "Cancel", GRAY, dlg.destroy, width=10).pack(side="right", padx=(0, 8))

    dlg.bind("<Return>", ok)
    dlg.bind("<Escape>", lambda e: dlg.destroy())
    dlg.update_idletasks()
    center_window(dlg, max(dlg.winfo_reqwidth(), 400), dlg.winfo_reqheight())
    dlg.grab_set()
    entries[0].focus()
    parent.wait_window(dlg)
    return result["v"]


# ================= REUSABLE TABLE TAB ================= #

class TableTab(ttk.Frame):
    """A searchable, sortable table with Add / Edit / Delete buttons."""

    def __init__(self, parent, columns, widths, get_rows, on_add, on_edit, on_delete,
                 extra_buttons=(), noun="items"):
        super().__init__(parent)
        self.columns = columns
        self.get_rows = get_rows
        self.on_add, self.on_edit, self.on_delete = on_add, on_edit, on_delete
        self.noun = noun
        self.keys = {}
        self.sort_col = None
        self.sort_rev = False

        # ----- toolbar ----- #
        top = tk.Frame(self, bg=SURFACE)
        top.pack(fill="x", padx=12, pady=(12, 8))

        search_box = tk.Frame(top, bg=SURFACE2, highlightthickness=1, highlightbackground=BORDER,
                              highlightcolor=ACCENT)
        search_box.pack(side="left")
        tk.Label(search_box, text="🔍", bg=SURFACE2, fg=MUTED).pack(side="left", padx=(8, 0))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.refresh())
        e = tk.Entry(search_box, textvariable=self.search, width=24, bg=SURFACE2, fg=TEXT,
                     insertbackground=TEXT, relief="flat", bd=0, font=(FONT, 10))
        e.pack(side="left", padx=6, ipady=7)

        def btn(text, color, cmd):
            make_button(top, text, color, cmd, size=9).pack(side="left", padx=(8, 0))

        btn("➕  Add", GREEN, self.add)
        btn("✏️  Edit", CYAN, self.edit_selected)
        btn("🗑  Delete", RED, self.delete_selected)
        for text, color, fn in extra_buttons:
            btn(text, color, lambda f=fn: f(self))

        self.count_label = tk.Label(top, text="", fg=MUTED, bg=SURFACE, font=(FONT, 9))
        self.count_label.pack(side="right")

        # ----- table ----- #
        body = tk.Frame(self, bg=SURFACE)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="extended")
        scroll = ttk.Scrollbar(body, command=self.tree.yview)
        self.tree.config(yscrollcommand=scroll.set)
        for i, col in enumerate(columns):
            self.tree.heading(col, text=col, anchor="w", command=lambda i=i: self.sort_by(i))
            self.tree.column(col, width=widths[i], anchor="w")
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.refresh()

    @staticmethod
    def _sort_key(value):
        try:
            return (0, float(str(value).replace(",", "")), "")
        except ValueError:
            return (1, 0.0, str(value).lower())

    def sort_by(self, index):
        self.sort_rev = (not self.sort_rev) if self.sort_col == index else False
        self.sort_col = index
        self.refresh()

    def refresh(self):
        q = self.search.get().strip().lower()
        rows = [(k, v) for k, v in self.get_rows()
                if not q or any(q in str(x).lower() for x in v)]
        if self.sort_col is not None:
            rows.sort(key=lambda kv: self._sort_key(kv[1][self.sort_col]), reverse=self.sort_rev)
        self.tree.delete(*self.tree.get_children())
        self.keys = {}
        for i, (key, values) in enumerate(rows):
            self.tree.insert("", "end", iid=str(i), values=values)
            self.keys[str(i)] = key
        self.count_label.config(text=f"{len(rows)} {self.noun}")

    def selected_keys(self):
        return [self.keys[i] for i in self.tree.selection() if i in self.keys]

    def add(self):
        self.on_add()
        self.refresh()

    def edit_selected(self):
        keys = self.selected_keys()
        if len(keys) != 1:
            messagebox.showinfo("Edit", "Please select exactly one row to edit.")
            return
        self.on_edit(keys[0])
        self.refresh()

    def delete_selected(self):
        keys = self.selected_keys()
        if not keys:
            messagebox.showinfo("Delete", "Please select at least one row to delete.")
            return
        if not messagebox.askyesno("Confirm delete",
                                   f"Delete {len(keys)} selected {self.noun}?\nThis cannot be undone."):
            return
        self.on_delete(keys)
        self.refresh()


# ================= MAIN ADMIN WINDOW ================= #

def admin_window(current_user):
    """Shows the control panel. Returns True if the user clicked Logout."""
    win = tk.Tk()
    win.title("STOCK & APP MANAGER")
    apply_theme(win)
    center_window(win, 1040, 660)
    win.minsize(860, 500)
    state = {"logout": False}

    # ----- header ----- #
    header = tk.Frame(win, bg=BG)
    header.pack(fill="x", padx=16, pady=(14, 6))
    tk.Label(header, text="STOCK & APP MANAGER", font=(FONT, 16, "bold"), bg=BG, fg=TEXT).pack(side="left")

    def logout():
        state["logout"] = True
        win.destroy()

    make_button(header, "Logout", GRAY, logout, width=8, size=9).pack(side="right")
    chip = tk.Label(header, text=f"👤  {current_user}", bg=SURFACE2, fg=TEXT, font=(FONT, 9, "bold"),
                    padx=12, pady=6)
    chip.pack(side="right", padx=12)

    notebook = ttk.Notebook(win)
    notebook.pack(fill="both", expand=True, padx=14, pady=(6, 6))

    # =============== STOCK & PRICES =============== #

    def stock_rows():
        rows = []
        for name, value in read_json(STOCK_FILE, {}).items():
            price, unit = stock_entry(value)
            rows.append((name, (name, unit, f"{price:.2f}")))
        return rows

    def stock_add():
        stock = read_json(STOCK_FILE, {})

        def validate(v):
            if not v[0]:
                return "Item name is required."
            if parse_price(v[2]) is None:
                return "Price must be a number (0 or more)."
            if find_key(stock, v[0]):
                return "This item already exists. Select it and use Edit to change the price."

        vals = form_dialog(win, "Add Item",
                           [("Item Name", False), ("Unit (e.g. 1 kg, 1 piece, 500 g, 1 litre)", False),
                            ("Price per unit (AED)", False)],
                           values=["", DEFAULT_UNIT, ""], validate=validate)
        if vals:
            stock[vals[0]] = make_entry_value(parse_price(vals[2]), vals[1])
            write_json(STOCK_FILE, stock)

    def stock_add_per_kg(tab):
        """Quick form for items that are sold by weight (price per 1 kg)."""
        stock = read_json(STOCK_FILE, {})

        def validate(v):
            if not v[0]:
                return "Item name is required."
            if parse_price(v[1]) is None:
                return "Price per kg must be a number (0 or more)."
            if find_key(stock, v[0]):
                return "This item already exists. Select it and use Edit to change the price."

        vals = form_dialog(win, "Add Item (per kg)",
                           [("Item Name", False), ("Price per 1 kg (AED)", False)],
                           validate=validate,
                           note="Customers can then order this item by weight, e.g. \"500 g apples\".")
        if vals:
            stock[vals[0]] = make_entry_value(parse_price(vals[1]), "1 kg")
            write_json(STOCK_FILE, stock)
            tab.refresh()

    def stock_edit(old_name):
        stock = read_json(STOCK_FILE, {})
        if old_name not in stock:
            return
        price, unit = stock_entry(stock[old_name])

        def validate(v):
            if not v[0]:
                return "Item name is required."
            if parse_price(v[2]) is None:
                return "Price must be a number (0 or more)."
            if v[0].lower() != old_name.lower() and find_key(stock, v[0]):
                return "Another item already has that name."

        vals = form_dialog(win, "Edit Item",
                           [("Item Name", False), ("Unit (e.g. 1 kg, 1 piece, 500 g, 1 litre)", False),
                            ("Price per unit (AED)", False)],
                           values=[old_name, unit, f"{price:.2f}"], validate=validate)
        if vals:
            stock.pop(old_name)
            stock[vals[0]] = make_entry_value(parse_price(vals[2]), vals[1])
            write_json(STOCK_FILE, stock)

    def stock_delete(names):
        stock = read_json(STOCK_FILE, {})
        for n in names:
            stock.pop(n, None)
        write_json(STOCK_FILE, stock)

    def stock_adjust(tab):
        stock = read_json(STOCK_FILE, {})
        if not stock:
            messagebox.showinfo("Adjust Prices", "Stock is empty.")
            return
        names = [n for n in tab.selected_keys() if n in stock] or list(stock)

        def validate(v):
            try:
                pct = float(v[0])
            except ValueError:
                return "Enter a number, e.g. 10 or -5."
            if not math.isfinite(pct) or pct <= -100:
                return "The change must be above -100%."

        vals = form_dialog(win, "Adjust Prices", [("Percent change", False)], validate=validate,
                           note=f"e.g. 10 for +10%, -5 for -5%.\nApplies to {len(names)} "
                                f"{'selected' if tab.selected_keys() else 'ALL'} item(s).")
        if not vals:
            return
        pct = float(vals[0])
        for n in names:
            price, unit = stock_entry(stock[n])
            stock[n] = make_entry_value(price * (1 + pct / 100), unit)
        write_json(STOCK_FILE, stock)
        tab.refresh()

    def stock_import(tab):
        path = filedialog.askopenfilename(parent=win, title="Import stock from CSV",
                                          filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        stock = read_json(STOCK_FILE, {})
        added = updated = skipped = 0
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                for row in csv.reader(f):
                    row = [c.strip() for c in row]
                    if len(row) >= 3:                       # Item, Unit, Price
                        name, unit, price = row[0], row[1], parse_price(row[2])
                    elif len(row) == 2:                     # Item, Price
                        name, unit, price = row[0], None, parse_price(row[1])
                    else:
                        skipped += 1
                        continue
                    if not name or price is None:           # also skips a header row
                        skipped += 1
                        continue
                    existing = find_key(stock, name)
                    # same name but a different unit (e.g. two bottle sizes) -> separate item
                    if existing and unit and stock_entry(stock[existing])[1].lower() != unit.lower():
                        name = f"{name} ({unit})"
                        existing = find_key(stock, name)
                    if existing:
                        old_unit = stock_entry(stock[existing])[1]
                        stock[existing] = make_entry_value(price, unit or old_unit)
                        updated += 1
                    else:
                        stock[name] = make_entry_value(price, unit)
                        added += 1
        except (OSError, csv.Error, UnicodeDecodeError) as e:
            messagebox.showerror("Import failed", f"Could not read the file:\n{e}")
            return
        write_json(STOCK_FILE, stock)
        tab.refresh()
        messagebox.showinfo("Import finished",
                            f"Added: {added}\nUpdated: {updated}\nSkipped: {skipped}\n\n"
                            "CSV format: Item, Unit, Price (AED)  - one item per row.\n"
                            "A 2-column file (Item, Price) also works.")

    def stock_export(tab):
        path = filedialog.asksaveasfilename(parent=win, title="Export stock to CSV",
                                            defaultextension=".csv", initialfile="stock_export.csv",
                                            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Item", "Unit", "Price (AED)"])
                for name, value in read_json(STOCK_FILE, {}).items():
                    price, unit = stock_entry(value)
                    w.writerow([name, unit, f"{price:.2f}"])
        except OSError as e:
            messagebox.showerror("Export failed", str(e))
            return
        messagebox.showinfo("Export finished", f"Stock saved to:\n{path}")

    stock_tab = TableTab(
        notebook, ("Item", "Unit", "Price (AED)"), (380, 160, 140), stock_rows,
        stock_add, stock_edit, stock_delete,
        extra_buttons=[("⚖  Add Per-Kg Item", PURPLE, stock_add_per_kg),
                       ("%  Adjust", ORANGE, stock_adjust),
                       ("⬇  Import", GRAY, stock_import),
                       ("⬆  Export", GRAY, stock_export)],
        noun="items")
    notebook.add(stock_tab, text="  📦 Stock & Prices  ")

    # =============== CUSTOMERS =============== #

    def customer_rows():
        return [(n, (n, d.get("phone", ""), d.get("trn", "")))
                for n, d in read_json(CUSTOMERS_FILE, {}).items()]

    customer_fields = [("Customer Full Name", False), ("Phone", False), ("TRN Number", False)]

    def customer_add():
        customers = read_json(CUSTOMERS_FILE, {})

        def validate(v):
            if not v[0]:
                return "Customer name is required."
            if find_key(customers, v[0]):
                return "A customer with this name already exists."

        vals = form_dialog(win, "Add Customer", customer_fields, validate=validate)
        if vals:
            customers[vals[0]] = {"phone": vals[1], "trn": vals[2]}
            write_json(CUSTOMERS_FILE, customers)

    def customer_edit(old_name):
        customers = read_json(CUSTOMERS_FILE, {})
        if old_name not in customers:
            return
        info = customers[old_name]

        def validate(v):
            if not v[0]:
                return "Customer name is required."
            if v[0].lower() != old_name.lower() and find_key(customers, v[0]):
                return "Another customer already has that name."

        vals = form_dialog(win, "Edit Customer", customer_fields,
                           values=[old_name, info.get("phone", ""), info.get("trn", "")], validate=validate)
        if vals:
            customers.pop(old_name)
            customers[vals[0]] = {"phone": vals[1], "trn": vals[2]}
            write_json(CUSTOMERS_FILE, customers)

    def customer_delete(names):
        customers = read_json(CUSTOMERS_FILE, {})
        for n in names:
            customers.pop(n, None)
        write_json(CUSTOMERS_FILE, customers)

    notebook.add(TableTab(notebook, ("Name", "Phone", "TRN"), (320, 180, 220), customer_rows,
                          customer_add, customer_edit, customer_delete, noun="customers"),
                 text="  👥 Customers  ")

    # =============== INVOICE APP USERS (name + phone logins) =============== #

    def app_user_rows():
        return [(phone, (name, phone)) for phone, name in read_json(APP_USERS_FILE, {}).items()]

    app_user_fields = [("Full Name", False), ("Phone Number", False)]

    def app_user_add():
        users = read_json(APP_USERS_FILE, {})

        def validate(v):
            key = normalize_phone(v[1])
            if not v[0]:
                return "Name is required."
            if not 7 <= len(key) <= 15:
                return "Enter a valid phone number (7-15 digits)."
            if key in users:
                return "This phone number is already registered."

        vals = form_dialog(win, "Add Invoice-App User", app_user_fields, validate=validate)
        if vals:
            users[normalize_phone(vals[1])] = " ".join(vals[0].split())
            write_json(APP_USERS_FILE, users)

    def app_user_edit(old_phone):
        users = read_json(APP_USERS_FILE, {})
        if old_phone not in users:
            return

        def validate(v):
            key = normalize_phone(v[1])
            if not v[0]:
                return "Name is required."
            if not 7 <= len(key) <= 15:
                return "Enter a valid phone number (7-15 digits)."
            if key != old_phone and key in users:
                return "This phone number is already registered."

        vals = form_dialog(win, "Edit Invoice-App User", app_user_fields,
                           values=[users[old_phone], old_phone], validate=validate)
        if vals:
            users.pop(old_phone)
            users[normalize_phone(vals[1])] = " ".join(vals[0].split())
            write_json(APP_USERS_FILE, users)

    def app_user_delete(phones):
        users = read_json(APP_USERS_FILE, {})
        for p in phones:
            users.pop(p, None)
        write_json(APP_USERS_FILE, users)

    notebook.add(TableTab(notebook, ("Name", "Phone"), (380, 220), app_user_rows,
                          app_user_add, app_user_edit, app_user_delete, noun="users"),
                 text="  🔑 Invoice App Users  ")

    # =============== ADMIN ACCOUNTS =============== #

    def admin_rows():
        return [(u, (u, "You" if u == current_user else ""))
                for u in read_json(ADMINS_FILE, {})]

    def password_error(pw, confirm):
        if len(pw) < MIN_PASSWORD_LENGTH:
            return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        if pw != confirm:
            return "Passwords do not match."

    def admin_add():
        admins = read_json(ADMINS_FILE, {})

        def validate(v):
            if not v[0]:
                return "Username is required."
            if find_key(admins, v[0]):
                return "This username already exists."
            return password_error(v[1], v[2])

        vals = form_dialog(win, "Add Admin",
                           [("Username", False), ("Password", True), ("Confirm Password", True)],
                           validate=validate)
        if vals:
            admins[vals[0]] = hash_password(vals[1])
            write_json(ADMINS_FILE, admins)

    def admin_change_password(username):
        admins = read_json(ADMINS_FILE, {})
        if username not in admins:
            return
        vals = form_dialog(win, f"Change Password - {username}",
                           [("New Password", True), ("Confirm New Password", True)],
                           validate=lambda v: password_error(v[0], v[1]))
        if vals:
            admins[username] = hash_password(vals[0])
            write_json(ADMINS_FILE, admins)

    def admin_delete(usernames):
        admins = read_json(ADMINS_FILE, {})
        if current_user in usernames:
            messagebox.showerror("Delete", "You cannot delete the account you are logged in with.")
            return
        if len(admins) - len(usernames) < 1:
            messagebox.showerror("Delete", "At least one admin account must remain.")
            return
        for u in usernames:
            admins.pop(u, None)
        write_json(ADMINS_FILE, admins)

    # Edit on this tab = change password
    notebook.add(TableTab(notebook, ("Admin Username", "Note"), (380, 220), admin_rows,
                          admin_add, admin_change_password, admin_delete, noun="admins"),
                 text="  🛡 Admins  ")
    tk.Label(win, text="Tip: on the Admins tab, 'Edit' changes the selected admin's password.   "
                       "On the Stock tab, items with unit \"1 kg\" can be ordered by weight in the invoice app.",
             bg=BG, fg=MUTED, font=(FONT, 9)).pack(pady=(0, 10))

    win.mainloop()
    return state["logout"]


# ================= LOGIN / FIRST-TIME SETUP ================= #

def login_screen():
    """Returns the logged-in admin username, or None if the window was closed."""
    admins = read_json(ADMINS_FILE, {})
    first_run = not admins
    result = {"user": None}

    root = tk.Tk()
    root.title("Stock Manager - " + ("First-time Setup" if first_run else "Login"))
    apply_theme(root)
    center_window(root, 420, 470 if first_run else 400)

    card = tk.Frame(root, bg=SURFACE)
    card.pack(fill="both", expand=True, padx=24, pady=24)

    tk.Label(card, text="📦", bg=SURFACE, font=(FONT, 30)).pack(pady=(22, 0))
    tk.Label(card, text="Create Admin Account" if first_run else "Admin Login",
             font=(FONT, 16, "bold"), bg=SURFACE, fg=TEXT).pack(pady=(4, 0))
    tk.Label(card, text="No admin exists yet. Create the first one." if first_run
             else "Sign in to manage stock and users",
             bg=SURFACE, fg=MUTED, font=(FONT, 9)).pack(pady=(2, 8))

    def labeled_entry(text, secret=False):
        tk.Label(card, text=text, bg=SURFACE, fg=MUTED, font=(FONT, 9, "bold")).pack(
            padx=30, pady=(10, 3), anchor="w")
        e = make_entry(card, width=30, show="*" if secret else "")
        e.pack(padx=30, ipady=6, fill="x")
        return e

    user_e = labeled_entry("Username")
    pass_e = labeled_entry("Password", secret=True)
    confirm_e = labeled_entry("Confirm Password", secret=True) if first_run else None

    def submit(event=None):
        username, password = user_e.get().strip(), pass_e.get()
        if first_run:
            if not username:
                messagebox.showerror("Setup", "Username is required.", parent=root)
                return
            if len(password) < MIN_PASSWORD_LENGTH:
                messagebox.showerror("Setup", f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", parent=root)
                return
            if password != confirm_e.get():
                messagebox.showerror("Setup", "Passwords do not match.", parent=root)
                return
            write_json(ADMINS_FILE, {username: hash_password(password)})
            result["user"] = username
            root.destroy()
            return

        current = read_json(ADMINS_FILE, {})
        key = find_key(current, username)
        if key and verify_password(password, current[key]):
            result["user"] = key
            root.destroy()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password.", parent=root)
            pass_e.delete(0, tk.END)

    make_button(card, "Create Account" if first_run else "Login", ACCENT_DARK, submit).pack(
        pady=22, padx=30, fill="x")

    for e in (user_e, pass_e, confirm_e):
        if e is not None:
            e.bind("<Return>", submit)
    user_e.focus()
    root.mainloop()
    return result["user"]


def main():
    while True:
        user = login_screen()
        if not user:
            break
        if not admin_window(user):    # closed with X (not Logout) -> quit
            break


if __name__ == "__main__":
    main()
