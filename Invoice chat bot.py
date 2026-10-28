import tkinter as tk
from tkinter import ttk
from docxtpl import DocxTemplate
from num2words import num2words
import datetime
import difflib
import importlib.util
import json
import math
import os
import queue
import re
import sys
import threading
import time
import traceback

# ================= SETTINGS ================= #

VAT_RATE = 0.05
CURRENCY_MAIN = "Dirhams"
CURRENCY_SUB = "Fils"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INVOICE_FOLDER = os.path.join(BASE_DIR, "Invoices")


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
    tmp = file_path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, file_path(name))


def parse_unit(unit):
    """('kg', kg_amount) for '1 kg', 'kg', 'per kg', '500 g'; ('pc', 1) for '1 piece', 'pc', ..."""
    s = str(unit).strip().lower()
    m = re.match(r"^(?:(\d+(?:\.\d+)?)\s*)?(?:per\s+)?(kilograms?|kilos?|kgs?|grams?|gms?|g)\b", s)
    if m:
        amount = float(m.group(1) or 1)
        kg = amount if m.group(2).startswith("k") else amount / 1000
        return "kg", (kg or 1.0)
    return "pc", 1.0


def read_stock():
    """
    Returns {name: {"price": float, "unit": "pc" | "kg"}} (price is always per piece or per 1 kg).
    Understands plain numbers, {"price", "unit"} with units like "kg", "1 kg", "500 g", "1 piece".
    """
    out = {}
    for name, v in read_json("stock_data.json", {}).items():
        if isinstance(v, dict):
            price = v.get("price", v.get("Price", v.get("rate", 0)))
            unit = v.get("unit", v.get("Unit", "pc"))
        elif isinstance(v, (list, tuple)) and v:
            price, unit = v[0], (v[1] if len(v) > 1 else "pc")
        else:
            price, unit = v, "pc"
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = 0.0
        kind, amount = parse_unit(unit)
        if kind == "kg":
            price = round(price / amount, 4)
        out[name] = {"price": price, "unit": kind}
    return out


def save_stock_item(name, price, unit):
    """Adds/updates ONE item without touching how the other items are stored."""
    raw = read_json("stock_data.json", {})
    verbose = any(isinstance(v, dict) and re.match(r"\s*\d", str(v.get("unit", ""))) for v in raw.values())
    label = ("1 kg" if verbose else "kg") if unit == "kg" else ("1 piece" if verbose else "pc")
    for k in list(raw):
        if k.lower() == name.lower():
            raw.pop(k)
    raw[name] = {"price": price, "unit": label}
    write_json("stock_data.json", raw)


def normalize_phone(phone):
    return re.sub(r"\D", "", phone)


def login_or_register(name, phone):
    """Name + phone login. Anyone can log in; new people are registered automatically."""
    name = " ".join(name.split())
    key = normalize_phone(phone)
    if not name:
        return False, "Please enter your name."
    if len(key) < 7 or len(key) > 15:
        return False, "Please enter a valid phone number (7-15 digits)."
    users = read_json("login_users.json", {})
    if key in users:
        if users[key].lower() != name.lower():
            return False, "This phone number is registered under a different name."
        return True, users[key]
    users[key] = name
    write_json("login_users.json", users)
    return True, name


# ================= INVOICE NUMBER ================= #

def peek_invoice_number():
    today = datetime.datetime.now().strftime("%Y%m%d")
    data = read_json("invoice_counter.json", {"date": "", "count": 0})
    count = data.get("count", 0) + 1 if data.get("date") == today else 1
    return today, count


def format_invoice_number(today, count):
    return f"{today}-{count:03d}"


def amount_in_words(amount):
    cents = round(amount * 100)
    main, sub = divmod(cents, 100)
    words = num2words(main).title() + " " + CURRENCY_MAIN
    if sub:
        words += " And " + num2words(sub).title() + " " + CURRENCY_SUB
    return words + " Only"


def fmt_qty(qty, unit):
    """500 g / 1.5 kg for weighed items, whole numbers for pieces."""
    if unit == "kg":
        grams = round(qty * 1000, 3)
        return f"{grams:g} g" if grams < 1000 else f"{qty:g} kg"
    return f"{int(qty)}"


def fmt_price(price, unit):
    return f"{price:.2f}" + ("/kg" if unit == "kg" else "")


def normalize_fractions(text):
    """'half a kilo' -> '0.5 kg', 'quarter kilo' -> '0.25 kg', 'three quarters of a kilo' -> '0.75 kg'."""
    kilo = r"(?:kilo|kilogram|kg)s?\b"
    t = re.sub(rf"\b(?:three|3)\s+quarters?\s+(?:of\s+a\s+)?{kilo}", "0.75 kg", text, flags=re.I)
    t = re.sub(rf"(?<!\ba )\b(?:half|1/2)\s+(?:a\s+|of\s+a\s+)?{kilo}", "0.5 kg", t, flags=re.I)
    t = re.sub(rf"\b(?:a\s+)?quarter\s+(?:of\s+a\s+)?{kilo}", "0.25 kg", t, flags=re.I)
    return t


# ================= DARK THEME ================= #

BG = "#0b1220"
SURFACE = "#131c2e"
SURFACE2 = "#1b2740"
BORDER = "#2a3a57"
TEXT = "#e6edf7"
MUTED = "#8a9bb8"
ACCENT, ACCENT_HOVER = "#4f8cff", "#6ea1ff"
GREEN, GREEN_HOVER = "#1fa65a", "#2dbf6c"
RED, RED_HOVER = "#e5484d", "#f06a6e"
AMBER, AMBER_HOVER = "#e8912d", "#f5a34a"
PURPLE, PURPLE_HOVER = "#7c5cf0", "#957bf5"
GRAY, GRAY_HOVER = "#33415c", "#455676"

FONT_FAMILY = "Segoe UI"
if sys.platform == "win32":
    MONO_FAMILY = "Consolas"
elif sys.platform == "darwin":
    MONO_FAMILY = "Menlo"
else:
    MONO_FAMILY = "DejaVu Sans Mono"


def dark_titlebar(win):
    """Windows 10/11: make the title bar dark too (silently ignored elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                       ctypes.sizeof(value))
    except Exception:
        pass


def place_window(win, parent=None, w=None, h=None):
    """Centers a window (over its parent if given) and darkens its title bar."""
    win.update_idletasks()
    w = w or win.winfo_reqwidth()
    h = h or win.winfo_reqheight()
    if parent is not None and parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    else:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
    dark_titlebar(win)


def _button_style(s, name, bg, hover, fg="white", pad=(16, 9), size=10):
    s.configure(name, background=bg, foreground=fg, bordercolor=bg, lightcolor=bg, darkcolor=bg,
                focuscolor=bg, padding=pad, relief="flat", font=(FONT_FAMILY, size, "bold"))
    s.map(name,
          background=[("pressed", hover), ("active", hover), ("disabled", GRAY)],
          bordercolor=[("pressed", hover), ("active", hover)],
          lightcolor=[("pressed", hover), ("active", hover)],
          darkcolor=[("pressed", hover), ("active", hover)])


def setup_theme(root):
    """Applies the dark theme to a Tk root window (and every widget made afterwards)."""
    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", SURFACE2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    root.option_add("*TCombobox*Listbox.font", (FONT_FAMILY, 10))

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE2, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER, troughcolor=SURFACE, focuscolor=BG,
                font=(FONT_FAMILY, 10))

    # labels / frames
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Title.TLabel", font=(FONT_FAMILY, 15, "bold"))
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Error.TLabel", foreground="#ff7b80")
    s.configure("Card.TFrame", background=SURFACE)
    s.configure("Card.TLabel", background=SURFACE)
    s.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)

    # inputs
    s.configure("TEntry", fieldbackground=SURFACE2, foreground=TEXT, insertcolor=TEXT,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=8)
    s.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
          darkcolor=[("focus", ACCENT)])
    s.configure("TCombobox", fieldbackground=SURFACE2, background=SURFACE2, foreground=TEXT,
                arrowcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                padding=7, selectbackground=SURFACE2, selectforeground=TEXT)
    s.map("TCombobox", fieldbackground=[("readonly", SURFACE2)], foreground=[("readonly", TEXT)],
          selectbackground=[("readonly", SURFACE2)], selectforeground=[("readonly", TEXT)],
          background=[("active", BORDER)], bordercolor=[("focus", ACCENT)])

    # buttons
    _button_style(s, "TButton", GRAY, GRAY_HOVER)
    _button_style(s, "Accent.TButton", ACCENT, ACCENT_HOVER)
    _button_style(s, "Success.TButton", GREEN, GREEN_HOVER)
    _button_style(s, "Danger.TButton", RED, RED_HOVER)
    _button_style(s, "Warn.TButton", AMBER, AMBER_HOVER)
    _button_style(s, "Purple.TButton", PURPLE, PURPLE_HOVER)
    _button_style(s, "Muted.TButton", GRAY, GRAY_HOVER)
    _button_style(s, "Chip.TButton", SURFACE2, BORDER, fg=TEXT, pad=(12, 6), size=9)

    # table
    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                rowheight=32, borderwidth=0, relief="flat", font=(FONT_FAMILY, 10))
    s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
    s.configure("Treeview.Heading", background=SURFACE2, foreground=TEXT, relief="flat",
                borderwidth=0, padding=(10, 9), font=(FONT_FAMILY, 10, "bold"))
    s.map("Treeview.Heading", background=[("active", BORDER)])

    # tabs
    s.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BG, lightcolor=BG,
                darkcolor=BG, tabmargins=(0, 0, 0, 0))
    s.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=(22, 11),
                borderwidth=0, bordercolor=SURFACE, lightcolor=SURFACE, darkcolor=SURFACE,
                focuscolor=SURFACE, font=(FONT_FAMILY, 10, "bold"))
    s.map("TNotebook.Tab",
          background=[("selected", SURFACE2), ("active", SURFACE2)],
          foreground=[("selected", TEXT), ("active", TEXT)],
          lightcolor=[("selected", ACCENT)], bordercolor=[("selected", ACCENT)])

    # scrollbars
    for orient in ("Vertical", "Horizontal"):
        s.configure(f"{orient}.TScrollbar", background=SURFACE2, troughcolor=BG, bordercolor=BG,
                    arrowcolor=MUTED, lightcolor=SURFACE2, darkcolor=SURFACE2, gripcount=0)
        s.map(f"{orient}.TScrollbar", background=[("active", BORDER)])


def message_box(parent, title, text, kind="info", ask=False, danger=False):
    """Dark replacement for tkinter's messagebox. Returns True/False (for ask=True)."""
    icons = {"info": ("ℹ", ACCENT), "success": ("✔", GREEN), "error": ("✖", RED),
             "warn": ("⚠", AMBER), "ask": ("?", AMBER)}
    icon, color = icons["ask" if ask else kind]
    result = {"ok": False}

    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.configure(bg=BG)
    dlg.transient(parent)
    dlg.resizable(False, False)

    body = tk.Frame(dlg, bg=BG)
    body.pack(padx=28, pady=(26, 8))
    tk.Label(body, text=icon, fg=color, bg=BG, font=(FONT_FAMILY, 26, "bold")).pack(
        side="left", anchor="n", padx=(0, 18))
    tk.Label(body, text=text, fg=TEXT, bg=BG, justify="left", wraplength=380,
             font=(FONT_FAMILY, 10)).pack(side="left")

    btns = tk.Frame(dlg, bg=BG)
    btns.pack(pady=(10, 22))

    def close(value):
        result["ok"] = value
        dlg.destroy()

    if ask:
        yes = ttk.Button(btns, text="Yes", style="Danger.TButton" if danger else "Accent.TButton",
                         command=lambda: close(True))
        yes.pack(side="left", padx=5)
        ttk.Button(btns, text="No", style="Muted.TButton", command=lambda: close(False)).pack(
            side="left", padx=5)
        default = yes
        dlg.bind("<Return>", lambda e: close(not danger))
    else:
        default = ttk.Button(btns, text="OK", style="Accent.TButton", command=lambda: close(True))
        default.pack()
        dlg.bind("<Return>", lambda e: close(True))
    dlg.bind("<Escape>", lambda e: close(False))

    place_window(dlg, parent)
    try:
        dlg.wait_visibility()
        dlg.grab_set()
    except tk.TclError:
        pass
    default.focus()
    parent.wait_window(dlg)
    return result["ok"]


def info_box(parent, title, text):
    message_box(parent, title, text, "info")


def success_box(parent, title, text):
    message_box(parent, title, text, "success")


def error_box(parent, title, text):
    message_box(parent, title, text, "error")


def confirm_box(parent, title, text, danger=False):
    return message_box(parent, title, text, ask=True, danger=danger)



# ================= CHATBOT BRAIN ================= #

NUM = r"\d+(?:\.\d+)?"
TABLE = "@@TABLE@@"      # marks the part of a reply that is shown in a monospace box
WEIGHT_RE = re.compile(rf"(?<![\w.])({NUM})\s*(kilograms?|kilos?|kgs?|grams?|gms?|g)\b", re.I)
QUOTE_RE = re.compile(
    r"^(?:what(?:'s| is) the |what does )?(?:price|cost|how much(?: is| are| for| does| do)?)"
    r"(?: of| for)?\s+(.+?)(?:\s+cost)?\??$", re.I)

HELP_TEXT = """CUSTOMER
  invoice for Ahmed Ali
  invoice for Ahmed Ali phone 0501234567 trn 100123456700003

ITEMS BY PIECE
  3 laptops at 2500, 10 pens

ITEMS BY WEIGHT (grams or kg)
  500g tomatoes
  250 grams of saffron
  1.5 kg onions
  750g nuts at 40 per kg      (when the price per kg is not in stock)

PRICE CHECK (does not add to the invoice)
  price of 250g saffron
  how much is 750 grams of tomatoes

EDIT
  remove last | remove 2 | remove tomato
  date 25-12-2026

FINISH
  show | generate | new

STOCK
  stock Laptop 2500
  stock Tomato 12 per kg
  stock list | customers"""


class InvoiceBot:
    def __init__(self):
        self.stock = read_stock()
        self.customers = read_json("customers_data.json", {})
        self.reset()

    # ---------- state ---------- #

    def reset(self):
        self.items = []      # [sl, desc, qty, price, total, unit]
        self.pending = []    # items waiting for a price: [qty, desc, unit]
        self.customer = {"name": "", "phone": "", "trn": ""}
        today, count = peek_invoice_number()
        self.invoice_no = format_invoice_number(today, count)
        self.date = datetime.datetime.now().strftime("%d-%m-%Y")

    def totals(self):
        subtotal = round(sum(i[4] for i in self.items), 2)
        vat = round(subtotal * VAT_RATE, 2)
        return subtotal, vat, round(subtotal + vat, 2)

    def renumber(self):
        for n, item in enumerate(self.items, start=1):
            item[0] = n

    # ---------- matching ---------- #

    def find_stock(self, desc):
        lookup = {k.lower(): k for k in self.stock}
        d = desc.lower().strip()
        candidates = [d]
        if d.endswith("es"):
            candidates.append(d[:-2])
        if d.endswith("s"):
            candidates.append(d[:-1])
        for c in candidates:
            if c in lookup:
                return lookup[c]
        m = difflib.get_close_matches(d, list(lookup), n=1, cutoff=0.8)
        return lookup[m[0]] if m else None

    def find_customer(self, name):
        lookup = {k.lower(): k for k in self.customers}
        if name.lower() in lookup:
            return lookup[name.lower()]
        m = difflib.get_close_matches(name.lower(), list(lookup), n=1, cutoff=0.8)
        return lookup[m[0]] if m else None

    # ---------- parsing ---------- #

    @staticmethod
    def split_chunks(text):
        text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)   # 2,500 -> 2500
        parts = re.split(r"[,;\n]|\s+and\s+(?=\d)", text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def parse_item(chunk):
        """
        Returns {"qty", "desc", "price" (or None), "weighed"} or None.
        For weighed items qty is in kilograms (500 g -> 0.5).
        """
        chunk = re.sub(r"^(?:please\s+)?(?:add|put|include)\s+", "", chunk.strip(), flags=re.I)
        chunk = re.sub(r"\s*(?:aed|dirhams?|dhs)\b", "", chunk, flags=re.I)
        if not re.search(r"[A-Za-z]", chunk):
            return None

        qty, rest, weighed, has_qty = 1.0, chunk, False, False
        w = WEIGHT_RE.search(chunk)
        if w:
            amount = float(w.group(1))
            qty = amount if w.group(2).lower().startswith("k") else amount / 1000
            weighed, has_qty = True, True
            rest = (chunk[:w.start()] + " " + chunk[w.end():]).strip()
            rest = re.sub(r"^(?:of|x|×)\s+", "", rest, flags=re.I)
            rest = re.sub(r"\s*(?:per|/|a)\s*(?:kg|kilo)s?\b", "", rest, flags=re.I).strip()
        else:
            m = re.match(rf"^({NUM})\s*(?:x|×|pcs?|units?|nos)?\s+(.+)$", chunk, re.I)
            m2 = re.match(r"^(.+?)\s+[x×]\s*(\d+)\s*(.*)$", chunk, re.I)
            if m:
                qty, rest, has_qty = float(m.group(1)), m.group(2), True
            elif m2:
                qty, rest, has_qty = float(m2.group(2)), (m2.group(1) + " " + m2.group(3)).strip(), True
            rest = re.sub(r"\s*(?:per|/)\s*(?:kg|kilo)s?\b", "", rest, flags=re.I).strip()

        price, bare = None, False
        p = re.match(rf"^(.+?)(?:\s+(?:at|for|price|each)\s+|\s*@\s*)({NUM})\s*(?:each|/-)?$", rest, re.I)
        if not p:
            p = re.match(rf"^(.+?)\s+({NUM})\s*(?:each|/-)?$", rest, re.I)
            bare = p is not None
        if p:
            rest, price = p.group(1), float(p.group(2))

        desc = re.sub(r"\s+(?:each|@|at|of)$", "", rest.strip(), flags=re.I).strip()
        if not desc or qty <= 0:
            return None
        return {"qty": qty, "desc": desc, "price": price, "weighed": weighed,
                "has_qty": has_qty, "bare": bare}

    def resolve(self, chunk):
        """
        Works out quantity, unit and price for one piece of text.
        Returns None (not an item), {"error"}, {"pending"} (price needed) or {"item"}.
        """
        p = self.parse_item(chunk)
        if not p:
            return None
        qty, desc, price, weighed = p["qty"], p["desc"], p["price"], p["weighed"]
        unit = "kg" if weighed else "pc"

        match = self.find_stock(desc)
        if match and p["bare"] and not weighed and not p["has_qty"] and price is not None and price <= 999:
            qty, price = price, None          # "tomatoes 3" means 3 (kg), not a price of 3
        if match:
            info = self.stock[match]
            desc = match
            if weighed and info["unit"] == "pc" and price is None:
                return {"error": f"{match} is sold per piece, not by weight. "
                                 f"Give a quantity (e.g. \"3 {match}\") or a price per kg."}
            if not weighed and info["unit"] == "kg":
                unit = "kg"           # "3 tomatoes" for a per-kg item means 3 kg
            if price is None and info["unit"] == unit:
                price = info["price"]
        else:
            desc = desc[:1].upper() + desc[1:]

        if unit == "pc":
            if qty != int(qty):
                return {"error": f"\"{desc}\": pieces must be a whole number."}
            qty = int(qty)
        if price is None:
            return {"pending": [qty, desc, unit]}
        return {"item": [qty, desc, price, unit]}

    # ---------- display ---------- #

    @staticmethod
    def line_text(qty, desc, price, unit):
        return f"{fmt_qty(qty, unit)} x {desc} @ {fmt_price(price, unit)} = {round(qty * price, 2):.2f}"

    def invoice_text(self):
        lines = [f"Invoice {self.invoice_no}  |  {self.date}",
                 "Customer: " + (self.customer["name"] or "(not set)")]
        if self.customer["phone"] or self.customer["trn"]:
            lines.append(f"Phone: {self.customer['phone'] or '-'}   TRN: {self.customer['trn'] or '-'}")
        if not self.items:
            lines.append("")
            lines.append("No items yet.")
            return "\n".join(lines)
        lines.append("")
        lines.append(f"{'#':<3}{'Item':<22}{'Qty':>9}{'Price':>12}{'Total':>11}")
        for sl, desc, qty, price, total, unit in self.items:
            lines.append(f"{sl:<3}{desc[:21]:<22}{fmt_qty(qty, unit):>9}{fmt_price(price, unit):>12}{total:>11.2f}")
        sub, vat, net = self.totals()
        lines.append("-" * 57)
        lines.append(f"{'Subtotal':<46}{sub:>11.2f}")
        lines.append(f"{f'VAT {VAT_RATE * 100:g}%':<46}{vat:>11.2f}")
        lines.append(f"{'NET TOTAL':<46}{net:>11.2f}")
        return "\n".join(lines)

    def table(self):
        return TABLE + self.invoice_text()

    # ---------- actions ---------- #

    def add_resolved(self, item):
        qty, desc, price, unit = item
        self.items.append([len(self.items) + 1, desc, qty, price, round(qty * price, 2), unit])
        return self.line_text(qty, desc, price, unit)

    def ask_next_pending(self):
        qty, desc, unit = self.pending[0]
        what = "price per kg" if unit == "kg" else "price for 1 unit"
        return f"I don't have a price for \"{desc}\". What is the {what}? (or type skip)"

    def quote(self, text):
        r = self.resolve(text)
        if r is None:
            return "Tell me what to price, e.g. \"price of 250g saffron\"."
        if "error" in r:
            return r["error"]
        if "pending" in r:
            qty, desc, unit = r["pending"]
            return (f"\"{desc}\" is not in stock, so I don't know its price. "
                    f"Add the price, e.g. \"{fmt_qty(qty, unit)} {desc} at 40 per kg\".")
        return self.line_text(*r["item"]) + "   (not added to the invoice)"

    def set_customer(self, text):
        phone = re.search(r"(?:phone|tel|mobile|ph)\s*:?\s*(\+?[\d][\d\s-]{5,})", text, re.I)
        trn = re.search(r"trn\s*:?\s*(\d{10,20})", text, re.I)
        name = re.split(r"\b(?:phone|tel|mobile|ph|trn)\b", text, flags=re.I)[0].strip(" ,.-:")
        if not name:
            return "Please tell me the customer name, e.g. \"invoice for Ahmed Ali\"."
        saved = self.find_customer(name)
        if saved:
            info = self.customers[saved]
            self.customer = {"name": saved, "phone": info.get("phone", ""), "trn": info.get("trn", "")}
            msg = f"Found saved customer {saved}."
        else:
            self.customer = {"name": name, "phone": "", "trn": ""}
            msg = f"New customer {name}."
        if phone:
            self.customer["phone"] = phone.group(1).strip()
        if trn:
            self.customer["trn"] = trn.group(1)
        return msg

    def remove(self, arg):
        if not self.items:
            return "There is nothing to remove."
        arg = arg.strip().lower()
        if arg in ("last", "last item"):
            removed = self.items.pop()
        elif arg.isdigit() and 1 <= int(arg) <= len(self.items):
            removed = self.items.pop(int(arg) - 1)
        else:
            hits = [i for i in self.items if arg in i[1].lower()]
            if not hits:
                return f"I couldn't find \"{arg}\" on the invoice."
            removed = hits[0]
            self.items.remove(removed)
        self.renumber()
        return f"Removed {fmt_qty(removed[2], removed[5])} x {removed[1]}."

    def generate(self):
        if not self.items:
            return "There are no items yet. Add some first."
        if not self.customer["name"]:
            return "Who is this invoice for? Type e.g. \"invoice for Ahmed Ali\"."
        template_path = file_path("invoice_format.docx")
        if not os.path.exists(template_path):
            return "invoice_format.docx was not found in the app folder."

        sub, vat, net = self.totals()
        doc = DocxTemplate(template_path)
        doc.render({
            "invoice_number": self.invoice_no,
            "date": self.date,
            "customer_name": self.customer["name"],
            "customer_trn": self.customer["trn"],
            "phone": self.customer["phone"],
            "invoice_list": [[i[0], i[1], fmt_qty(i[2], i[5]), fmt_price(i[3], i[5]), f"{i[4]:.2f}"]
                             for i in self.items],
            "total_amount": f"{sub:.2f}",
            "vat_amount": f"{vat:.2f}",
            "total_words": amount_in_words(net),
            "net_total": f"{net:.2f}",
        })
        try:
            os.makedirs(INVOICE_FOLDER, exist_ok=True)
            out = os.path.join(INVOICE_FOLDER, f"Invoice_{self.invoice_no}.docx")
            doc.save(out)
        except PermissionError:
            return "Cannot save. Close the invoice if it is open in Word and try again."

        today, count = peek_invoice_number()
        write_json("invoice_counter.json", {"date": today, "count": count})

        extra = ""
        name = self.customer["name"]
        if not self.find_customer(name):
            self.customers[name] = {"phone": self.customer["phone"], "trn": self.customer["trn"]}
            write_json("customers_data.json", self.customers)
            extra = f"\n(New customer {name} saved for next time.)"

        msg = f"Invoice generated!\nNet total: {net:.2f}\nSaved in:\n{out}{extra}\n\nReady for a new invoice."
        self.reset()
        return msg

    # ---------- main entry ---------- #

    def handle(self, text):
        text = text.strip()
        low = text.lower()
        if not text:
            return ""

        text = normalize_fractions(text)
        low = text.lower()

        # always use the latest stock/customers (the Stock Manager app may have changed them)
        self.stock = read_stock()
        self.customers = read_json("customers_data.json", {})

        # waiting for a price?
        if self.pending:
            m = re.match(rf"^(?:aed\s*)?({NUM})\s*(?:aed|dirhams?|each|per kg|/\s*kg)?$", low)
            if m:
                qty, desc, unit = self.pending.pop(0)
                reply = "Added " + self.add_resolved([qty, desc, float(m.group(1)), unit]) + "."
                reply += ("\n" + self.ask_next_pending()) if self.pending else ("\n" + self.table())
                return reply
            if low in ("skip", "cancel", "no"):
                dropped = self.pending.pop(0)
                reply = f"Skipped {dropped[1]}."
                if self.pending:
                    reply += "\n" + self.ask_next_pending()
                return reply
            self.pending.clear()

        if re.match(r"^(help|\?|commands|hi|hello)$", low):
            return TABLE + HELP_TEXT
        if re.match(r"^(new|clear|reset|cancel)(\s+invoice)?$", low):
            self.reset()
            return "Started a fresh invoice. Who is it for?"
        if re.match(r"^(show|list|view|total|summary|invoice|preview)$", low):
            return self.table()
        if re.match(r"^(generate|done|finish|finished|create|print|make)(\s+(the\s+)?invoice)?$", low):
            return self.generate()

        m = re.match(r"^(?:remove|delete)\s+(.+)$", low)
        if m:
            return self.remove(m.group(1))

        m = re.match(r"^date\s+(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", low)
        if m:
            self.date = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}-{m.group(3)}"
            return f"Date set to {self.date}."

        if re.match(r"^(stock list|stock|items|show stock)$", low):
            if not self.stock:
                return "Stock is empty. Add with: stock Laptop 2500"
            return TABLE + "Stock:\n" + "\n".join(
                f"  {k}: {v['price']:.2f} " + ("per kg" if v["unit"] == "kg" else "per piece")
                for k, v in self.stock.items())
        if re.match(r"^(customers|customer list|show customers)$", low):
            if not self.customers:
                return "No saved customers yet."
            return TABLE + "Customers:\n" + "\n".join(f"  {k}" for k in self.customers)

        m = re.match(rf"^(?:add to stock|stock|save item)\s+(.+?)\s+(?:at\s+|@\s*)?({NUM})\s*"
                     r"(per\s*kg|/\s*kg|kg)?$", text, re.I)
        if m:
            name, price = m.group(1).strip(), float(m.group(2))
            unit = "kg" if m.group(3) else "pc"
            existing = self.find_stock(name)
            name = existing or name[:1].upper() + name[1:]
            save_stock_item(name, price, unit)
            return f"Saved to stock: {name} = {price:.2f} " + ("per kg" if unit == "kg" else "per piece")

        m = re.match(r"^(?:invoice for|bill to|customer|client|for)\s+(.+)$", text, re.I)
        if m:
            return self.set_customer(m.group(1))

        m = QUOTE_RE.match(text)
        if m:
            return self.quote(m.group(1))

        # otherwise: treat as items
        added, unknown, errors = [], [], []
        for chunk in self.split_chunks(text):
            r = self.resolve(chunk)
            if r is None:
                unknown.append(chunk)
            elif "error" in r:
                errors.append(r["error"])
            elif "pending" in r:
                self.pending.append(r["pending"])
            else:
                added.append(self.add_resolved(r["item"]))

        if not added and not self.pending and not errors:
            return "Sorry, I didn't understand that. Type \"help\" to see what I can do."

        parts = []
        if added:
            parts.append("Added:\n" + "\n".join(f"  - {a}" for a in added))
        parts += errors
        if unknown:
            parts.append("I skipped: " + ", ".join(unknown))
        reply = "\n".join(parts)
        if self.pending:
            reply += ("\n" if reply else "") + self.ask_next_pending()
        elif added:
            reply += "\n" + self.table()
        return reply.strip()


# ================= SPOKEN NUMBERS -> DIGITS ================= #

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: (i + 2) * 10 for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000}
_NUMWORD = "|".join(sorted(list(_UNITS) + list(_TENS) + list(_SCALES), key=len, reverse=True))
_DIGITWORD = "zero|one|two|three|four|five|six|seven|eight|nine"
_RUN = re.compile(rf"\b(?:{_NUMWORD})(?:[\s-]+(?:and[\s-]+)?(?:{_NUMWORD}))*"
                  rf"(?:\s+point(?:\s+(?:{_DIGITWORD}))+)?\b", re.I)


def _run_to_number(run):
    words = re.split(r"[\s-]+", run.lower())
    decimals = ""
    if "point" in words:
        i = words.index("point")
        decimals = "".join(str(_UNITS[w]) for w in words[i + 1:])
        words = words[:i]
    total = current = 0
    for w in words:
        if w == "and":
            continue
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        else:
            total += (current or 1) * _SCALES[w]
            current = 0
    value = total + current
    return f"{value}.{decimals}" if decimals else str(value)


def spoken_to_digits(text):
    """'three laptops at two thousand five hundred' -> '3 laptops at 2500'; 'half a kilo' -> '0.5 kg'."""
    t = _RUN.sub(lambda m: _run_to_number(m.group(0)), text)
    t = re.sub(r"\b(\d+)\s+and\s+a\s+half\b", lambda m: f"{m.group(1)}.5", t, flags=re.I)
    t = normalize_fractions(t)
    t = re.sub(r"\b[Aa]\s+(?=\d)", "", t)
    return t.strip()


# ================= VOICE ASSISTANT (engine) ================= #

WHISPER_MODEL = "small"     # "base" = lighter and faster, "small" = recommended, "medium" = most accurate
SAMPLE_RATE = 16000

# (name shown to the user, whisper code, Google code)
LANGUAGES = [
    ("Auto-detect", None, "en-US"), ("English", "en", "en-US"), ("Arabic", "ar", "ar-AE"),
    ("Hindi", "hi", "hi-IN"), ("Urdu", "ur", "ur-PK"), ("Malayalam", "ml", "ml-IN"),
    ("Tamil", "ta", "ta-IN"), ("Telugu", "te", "te-IN"), ("Bengali", "bn", "bn-BD"),
    ("Nepali", "ne", "ne-NP"), ("Sinhala", "si", "si-LK"), ("Filipino", "tl", "fil-PH"),
    ("Persian", "fa", "fa-IR"), ("Turkish", "tr", "tr-TR"), ("Russian", "ru", "ru-RU"),
    ("French", "fr", "fr-FR"), ("Spanish", "es", "es-ES"), ("Chinese", "zh", "zh-CN"),
    ("Indonesian", "id", "id-ID"),
]
LANG_NAMES = {code: name for name, code, _ in LANGUAGES if code}
LANG_CODE_BY_NAME = {name: code for name, code, _ in LANGUAGES}

INSTALL_HELP = (
    "Voice input needs a few extra packages. Open a terminal and run:\n\n"
    "    pip install sounddevice numpy faster-whisper\n\n"
    "faster-whisper recognises the language automatically, works offline after a one-time "
    "model download, and translates other languages to English for the assistant.\n\n"
    "Lighter alternative (needs internet, no automatic translation):\n"
    "    pip install sounddevice numpy SpeechRecognition")


class VoiceEngine:
    """Records speech, finds the language, transcribes it, and translates it to English."""

    def __init__(self):
        have = lambda name: importlib.util.find_spec(name) is not None
        self.mic_ok = have("sounddevice") and have("numpy")
        self.whisper_ok = have("faster_whisper")
        self.google_ok = have("speech_recognition")
        self.model = None
        self.model_error = ""
        self._lock = threading.Lock()

    @property
    def available(self):
        return self.mic_ok and (self.whisper_ok or self.google_ok)

    @property
    def problem(self):
        return "" if self.available else INSTALL_HELP

    def load_model(self, status=None):
        if not self.whisper_ok:
            return None
        with self._lock:
            if self.model is not None or self.model_error:
                return self.model
            try:
                if status:
                    status("Loading speech model… (the first time it is downloaded)")
                from faster_whisper import WhisperModel
                self.model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
                if status:
                    status("Voice ready")
            except Exception as e:                      # offline on first run, disk full, ...
                self.model_error = str(e)
                if status:
                    status("Speech model unavailable" + (" - using online recogniser" if self.google_ok else ""))
        return self.model

    @staticmethod
    def build_hint(stock):
        names = ", ".join(list(stock)[:40])
        return ("Invoice for a customer. Add 3 laptops at 2500 dirhams. 500 grams of tomatoes, "
                "1.5 kilos of onions, 250 grams of saffron. Generate invoice. Items: " + names)[:600]

    # ---------- recording ---------- #

    def record(self, stop_event, on_level, max_seconds=25, wait_seconds=9):
        """Records until the speaker pauses (or stop_event is set). Returns float32 audio or None."""
        import numpy as np
        import sounddevice as sd

        q = queue.Queue()
        blocks, ambient = [], []
        speech, silent, threshold = False, 0.0, 0.015
        t0 = time.time()

        def callback(indata, frames, t, status):
            q.put(indata.copy())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=1600, callback=callback):
            while not stop_event.is_set():
                try:
                    block = q.get(timeout=0.25)
                except queue.Empty:
                    continue
                blocks.append(block)
                rms = float(np.sqrt(np.mean(block ** 2)))
                on_level(rms)
                if len(ambient) < 4:                     # learn the room noise first (0.4 s)
                    ambient.append(rms)
                    threshold = min(0.05, max(0.012, 3.0 * sum(ambient) / len(ambient)))
                    continue
                if rms > threshold:
                    speech, silent = True, 0.0
                elif speech:
                    silent += 0.1
                    if silent >= 1.4:                    # a natural pause: they are done
                        break
                elapsed = time.time() - t0
                if (not speech and elapsed > wait_seconds) or elapsed > max_seconds:
                    break

        duration = sum(len(b) for b in blocks) / SAMPLE_RATE
        if duration < 0.4 or (not speech and not stop_event.is_set()):
            return None
        audio = np.concatenate(blocks)[:, 0].astype("float32")
        peak = float(np.abs(audio).max())
        if 0 < peak < 0.5:                               # quiet microphone: bring it up
            audio = audio * (0.8 / peak)
        return audio

    # ---------- recognising ---------- #

    def transcribe(self, audio, language=None, hint=""):
        """
        Returns {"text": what was said, "english": text for the assistant, "lang": code,
                 "confidence": 0-1 or None, "engine": "whisper" | "google"}.
        """
        if self.whisper_ok and not self.model_error:
            model = self.load_model()
            if model is not None:
                return self._whisper(model, audio, language, hint)
        if self.google_ok:
            return self._google(audio, language)
        raise RuntimeError("No speech engine is available. " + (self.model_error or INSTALL_HELP))

    def _whisper(self, model, audio, language, hint):
        lang, conf = language, 1.0
        if lang is None:                                 # find the language, among the supported ones
            try:
                best, prob, probs = model.detect_language(audio)[:3]
                allowed = {c for _, c, _ in LANGUAGES if c}
                cand = [(c, p) for c, p in probs if c in allowed]
                if cand:
                    total = sum(p for _, p in cand) or 1.0
                    best, top = max(cand, key=lambda x: x[1])
                    lang, conf = best, top / total
                else:
                    lang, conf = best, prob
            except Exception:
                lang = None
        opts = dict(beam_size=5, vad_filter=True, condition_on_previous_text=False)
        segs, info = model.transcribe(audio, language=lang, task="transcribe",
                                      initial_prompt=(hint if lang == "en" else None), **opts)
        text = " ".join(s.text.strip() for s in segs).strip()
        if lang is None:
            lang, conf = info.language, info.language_probability
        english = text
        if text and lang != "en":                        # translate for the assistant
            segs2, _ = model.transcribe(audio, language=lang, task="translate",
                                        initial_prompt=hint or None, **opts)
            english = " ".join(s.text.strip() for s in segs2).strip() or text
        return {"text": text, "english": english, "lang": lang, "confidence": conf, "engine": "whisper"}

    def _google(self, audio, language):
        import numpy as np
        import speech_recognition as sr
        code = next((g for n, c, g in LANGUAGES if c == language), "en-US") if language else "en-US"
        pcm = (np.clip(audio, -1, 1) * 32767).astype("int16").tobytes()
        try:
            text = sr.Recognizer().recognize_google(sr.AudioData(pcm, SAMPLE_RATE, 2), language=code)
        except sr.UnknownValueError:
            text = ""
        except sr.RequestError as e:
            raise RuntimeError("Could not reach the speech service. Check the internet connection.") from e
        return {"text": text, "english": text, "lang": language or "en", "confidence": None, "engine": "google"}


class Speaker:
    """Optional spoken replies (pyttsx3, offline)."""

    def __init__(self):
        self.ok = importlib.util.find_spec("pyttsx3") is not None
        self._lock = threading.Lock()

    def say(self, text):
        if not self.ok or not text:
            return

        def run():
            with self._lock:
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 170)
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
                except Exception:
                    pass
        threading.Thread(target=run, daemon=True).start()


def speakable(reply, net_total=None):
    prose = reply.split(TABLE)[0]
    prose = re.sub(r"\s+x\s+", " times ", prose)
    prose = prose.replace("@", " at ").replace("=", " equals ").replace("/kg", " per kilo")
    prose = re.sub(r"^\s*-\s*", "", prose, flags=re.M)
    prose = re.sub(r"\s+", " ", prose).strip()
    if net_total:
        prose += f" Net total {net_total:.2f} dirhams."
    return prose[:240]


# ================= UI WIDGETS ================= #

_NAMED = {"white": "ffffff", "black": "000000"}


def _rgb(color):
    c = _NAMED.get(color.lower(), color.lstrip("#"))
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def blend(c1, c2, t):
    a, b = _rgb(c1), _rgb(c2)
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_points(x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
            x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def fade_in_window(win, steps=10, delay=16):
    """Smooth fade-in when a window opens (silently skipped where unsupported)."""
    try:
        win.attributes("-alpha", 0.0)
    except tk.TclError:
        return

    def step(i):
        try:
            win.attributes("-alpha", min(1.0, i / steps))
        except tk.TclError:
            return
        if i < steps:
            win.after(delay, lambda: step(i + 1))
    step(1)


class HeaderBar(tk.Canvas):
    """Title bar with a soft gradient and a user pill."""

    def __init__(self, parent, title, right_text, height=66):
        super().__init__(parent, height=height, bg=BG, highlightthickness=0, bd=0)
        self.title, self.right_text = title, right_text
        self.bind("<Configure>", self.redraw)

    def redraw(self, event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.delete("all")
        step = 8
        for x in range(0, w, step):
            self.create_rectangle(x, 0, x + step + 1, h, fill=blend("#1a2d57", "#0b1220", x / w), outline="")
        self.create_line(0, h - 1, w, h - 1, fill=BORDER)
        self.create_text(26, h / 2, text=self.title, anchor="w", fill=TEXT, font=(FONT_FAMILY, 17, "bold"))
        t = self.create_text(w - 36, h / 2, text=self.right_text, anchor="e", fill=TEXT,
                             font=(FONT_FAMILY, 10, "bold"))
        x1, y1, x2, y2 = self.bbox(t)
        pill = self.create_polygon(rounded_points(x1 - 14, y1 - 7, x2 + 14, y2 + 7, 15), smooth=True,
                                   fill=SURFACE2, outline=BORDER)
        self.tag_raise(t)


class Bubble(tk.Canvas):
    """A rounded chat bubble that wraps its text and fades in."""

    def __init__(self, parent, text, fill, fg, font, max_width=0, outline="", page_bg=BG,
                 pad_x=16, pad_y=11, radius=16):
        super().__init__(parent, bg=page_bg, highlightthickness=0, bd=0)
        self.text, self.fill, self.fg, self.font = text, fill, fg, font
        self.max_width, self.outline, self.page_bg = max_width, outline, page_bg
        self.pad_x, self.pad_y, self.radius = pad_x, pad_y, radius
        self.draw()

    def draw(self):
        self.delete("all")
        wrap = max(80, self.max_width - 2 * self.pad_x) if self.max_width else 0
        tid = self.create_text(self.pad_x, self.pad_y, text=self.text, fill=self.fg, font=self.font,
                               anchor="nw", width=wrap, tags="txt")
        x1, y1, x2, y2 = self.bbox(tid)
        w, h = (x2 - x1) + 2 * self.pad_x, (y2 - y1) + 2 * self.pad_y
        self.configure(width=w, height=h)
        self.create_polygon(rounded_points(1, 1, w - 1, h - 1, self.radius), smooth=True,
                            fill=self.fill, outline=self.outline, tags="bg")
        self.tag_lower("bg")

    def set_max_width(self, max_width):
        if self.max_width and abs(max_width - self.max_width) > 4:
            self.max_width = max_width
            self.draw()

    def fade_in(self, steps=7, delay=22):
        def step(i):
            if not self.winfo_exists():
                return
            t = i / steps
            self.itemconfig("bg", fill=blend(self.page_bg, self.fill, t))
            self.itemconfig("txt", fill=blend(self.fill, self.fg, t))
            if i < steps:
                self.after(delay, lambda: step(i + 1))
        step(0)


class TypingDots(tk.Canvas):
    """The little bouncing '...' shown while the assistant 'thinks'."""

    def __init__(self, parent, page_bg=BG):
        super().__init__(parent, width=64, height=36, bg=page_bg, highlightthickness=0, bd=0)
        self.t = 0
        self._loop()

    def _loop(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        self.create_polygon(rounded_points(1, 1, 63, 35, 17), smooth=True, fill=SURFACE2, outline="")
        for i in range(3):
            wave = max(0.0, math.sin((self.t - i * 4) / 5.0))
            self.create_oval(12 + i * 16, 14 - 3 * wave, 20 + i * 16, 22 - 3 * wave,
                             fill=blend(MUTED, TEXT, wave), outline="")
        self.t += 1
        self.after(40, self._loop)


class WaveBars(tk.Canvas):
    """Live sound bars while listening; a gentle shimmer while recognising."""

    def __init__(self, parent, bars=40, width=520, height=46, page_bg=SURFACE):
        super().__init__(parent, width=width, height=height, bg=page_bg, highlightthickness=0, bd=0)
        self.n, self.w, self.h = bars, width, height
        self.levels = [0.0] * bars
        self.active, self.phase = False, 0
        self._loop()

    def reset(self):
        self.levels = [0.0] * self.n

    def push(self, rms):
        self.levels.append(min(1.0, rms * 16))
        self.levels = self.levels[-self.n:]

    def _loop(self):
        if not self.winfo_exists():
            return
        if self.winfo_ismapped():
            self.delete("all")
            gap = self.w / self.n
            for i, v in enumerate(self.levels):
                if not self.active:
                    v = 0.10 + 0.08 * math.sin(self.phase / 3.0 + i / 2.0)
                bh = max(4, v * self.h * 0.95)
                x = i * gap + gap / 2
                col = blend(ACCENT, RED, v) if self.active else ACCENT
                self.create_line(x, self.h / 2 - bh / 2, x, self.h / 2 + bh / 2, width=max(2, gap * 0.5),
                                 capstyle="round", fill=col)
            self.phase += 1
        self.after(40, self._loop)


class MicButton(tk.Canvas):
    """Round microphone button: pulses with your voice, spins while recognising."""

    def __init__(self, parent, command, size=54, page_bg=BG):
        super().__init__(parent, width=size, height=size, bg=page_bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.size, self.command = size, command
        self.state, self.level, self.tick, self.hover = "idle", 0.0, 0, False
        self._last = None
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: setattr(self, "hover", True))
        self.bind("<Leave>", lambda e: setattr(self, "hover", False))
        self._loop()

    def set_state(self, state):
        self.state = state

    def set_level(self, rms):
        self.level = max(self.level * 0.55, min(1.0, rms * 14))

    def _loop(self):
        if not self.winfo_exists():
            return
        self.tick += 1
        self.level *= 0.9
        sig = (self.state, self.hover, round(self.level, 2) if self.state == "listening" else 0,
               self.tick % 24 if self.state != "idle" else 0)
        if sig != self._last:
            self._last = sig
            self._draw()
        self.after(33, self._loop)

    def _draw(self):
        self.delete("all")
        c, r = self.size / 2, self.size / 2 - 9
        if self.state == "listening":
            glow = 3 + 12 * self.level + 2 * math.sin(self.tick / 4.0)
            self.create_oval(c - r - glow, c - r - glow, c + r + glow, c + r + glow,
                             fill=blend(BG, RED, 0.30), outline="")
            color = RED_HOVER if self.hover else RED
        elif self.state == "processing":
            color = ACCENT
        else:
            color = ACCENT_HOVER if self.hover else ACCENT
        self.create_oval(c - r, c - r, c + r, c + r, fill=color, outline="")
        if self.state == "processing":
            self.create_arc(c - 10, c - 10, c + 10, c + 10, start=-(self.tick * 14) % 360, extent=270,
                            style="arc", outline="white", width=3)
        elif self.state == "listening":
            self.create_rectangle(c - 7, c - 7, c + 7, c + 7, fill="white", outline="")   # stop square
        else:
            self.create_line(c, c - 8, c, c + 1, width=9, capstyle="round", fill="white")
            self.create_arc(c - 9, c - 7, c + 9, c + 9, start=180, extent=180, style="arc",
                            outline="white", width=2)
            self.create_line(c, c + 9, c, c + 13, width=2, fill="white")
            self.create_line(c - 5, c + 13, c + 5, c + 13, width=2, capstyle="round", fill="white")


class RoundedEntry(tk.Canvas):
    """Text box with rounded corners and an accent glow when focused."""

    def __init__(self, parent, font, height=50, radius=15, page_bg=BG, fill=SURFACE2):
        super().__init__(parent, height=height, bg=page_bg, highlightthickness=0, bd=0)
        self.radius, self.fill, self.focused = radius, fill, False
        self.entry = tk.Entry(self, bd=0, relief="flat", bg=fill, fg=TEXT, insertbackground=TEXT,
                              font=font, highlightthickness=0, selectbackground=ACCENT,
                              selectforeground="white")
        self.win = self.create_window(18, height / 2, window=self.entry, anchor="w")
        self.entry.bind("<FocusIn>", lambda e: self._focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._focus(False))
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", lambda e: self.entry.focus_set())

    def _focus(self, on):
        self.focused = on
        self._redraw()

    def _redraw(self, event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 30:
            return
        self.delete("box")
        self.create_polygon(rounded_points(2, 2, w - 2, h - 2, self.radius), smooth=True, fill=self.fill,
                            outline=ACCENT if self.focused else BORDER, width=2 if self.focused else 1,
                            tags="box")
        self.tag_lower("box")
        self.itemconfig(self.win, width=max(10, w - 38), height=h - 24)


# ================= CHAT WINDOW ================= #

def log_error(text):
    try:
        with open(file_path("error_log.txt"), "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n" + "-" * 60 + "\n")
    except OSError:
        pass


def main_app(current_user=""):
    window = tk.Tk()
    window.report_callback_exception = lambda exc, val, tb: log_error(
        "".join(traceback.format_exception(exc, val, tb)))
    window.title("PRO TAX INVOICE CHATBOT")
    setup_theme(window)
    st = ttk.Style(window)
    st.configure("TCheckbutton", background=BG, foreground=MUTED, focuscolor=BG)
    st.map("TCheckbutton", background=[("active", BG)], foreground=[("selected", TEXT)],
           indicatorcolor=[("selected", ACCENT)])
    window.minsize(1060, 680)
    try:
        window.state("zoomed")
    except tk.TclError:
        place_window(window, None, 1280, 800)
    dark_titlebar(window)

    bot = InvoiceBot()
    voice = VoiceEngine()
    speaker = Speaker()
    ui_q = queue.Queue()
    vs = {"mode": "idle", "stop": None, "audio": None, "res": None, "stop_listen": None}

    HeaderBar(window, "🧾  PRO TAX INVOICE", f"👤  {current_user}").pack(fill="x")

    body = tk.Frame(window, bg=BG)
    body.pack(fill="both", expand=True)

    # ================= right: live invoice ================= #
    panel = tk.Frame(body, bg=SURFACE, width=470, highlightbackground=BORDER, highlightthickness=1)
    panel.pack(side="right", fill="y", padx=(0, 18), pady=18)
    panel.pack_propagate(False)

    tk.Label(panel, text="LIVE INVOICE", bg=SURFACE, fg=MUTED,
             font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", padx=22, pady=(20, 6))
    cust_label = tk.Label(panel, text="", bg=SURFACE, fg=TEXT, font=(FONT_FAMILY, 16, "bold"), anchor="w")
    cust_label.pack(fill="x", padx=22)
    inv_label = tk.Label(panel, text="", bg=SURFACE, fg=MUTED, font=(FONT_FAMILY, 9), anchor="w")
    inv_label.pack(fill="x", padx=22, pady=(2, 0))
    contact_label = tk.Label(panel, text="", bg=SURFACE, fg=MUTED, font=(FONT_FAMILY, 9), anchor="w")
    contact_label.pack(fill="x", padx=22, pady=(0, 14))
    tk.Frame(panel, bg=BORDER, height=1).pack(fill="x", padx=22)

    columns = ("No", "Item", "Qty", "Price", "Total")
    widths = (32, 150, 72, 92, 84)
    tree = ttk.Treeview(panel, columns=columns, show="headings", height=12)
    for col, wd in zip(columns, widths):
        tree.heading(col, text=col)
        tree.column(col, width=wd, anchor="w" if col in ("No", "Item") else "e")
    tree.pack(fill="both", expand=True, padx=16, pady=12)

    tk.Frame(panel, bg=BORDER, height=1).pack(fill="x", padx=22)
    tot = tk.Frame(panel, bg=SURFACE)
    tot.pack(fill="x", padx=22, pady=(12, 6))
    tot.columnconfigure(1, weight=1)

    def total_row(r, label, big=False):
        tk.Label(tot, text=label, bg=SURFACE, fg=TEXT if big else MUTED,
                 font=(FONT_FAMILY, 12 if big else 10, "bold" if big else "normal")).grid(
            row=r, column=0, sticky="w", pady=2)
        v = tk.Label(tot, text="0.00", bg=SURFACE, fg=ACCENT if big else TEXT,
                     font=(FONT_FAMILY, 20 if big else 10, "bold" if big else "normal"))
        v.grid(row=r, column=1, sticky="e", pady=2)
        return v

    sub_v = total_row(0, "Subtotal")
    vat_v = total_row(1, f"VAT {VAT_RATE * 100:g}%")
    net_v = total_row(2, "NET TOTAL (AED)", big=True)

    btn_row = tk.Frame(panel, bg=SURFACE)
    btn_row.pack(fill="x", padx=22, pady=(6, 22))
    ttk.Button(btn_row, text="✔  Generate Invoice", style="Success.TButton",
               command=lambda: submit("generate")).pack(side="left", fill="x", expand=True, ipady=3)
    ttk.Button(btn_row, text="↺  New", style="Muted.TButton",
               command=lambda: submit("new")).pack(side="left", padx=(8, 0), ipady=3)

    # ================= left: chat ================= #
    left = tk.Frame(body, bg=BG)
    left.pack(side="left", fill="both", expand=True, padx=(18, 18), pady=(14, 18))

    bar = tk.Frame(left, bg=BG)
    bar.pack(side="bottom", fill="x", pady=(10, 0))

    chat_wrap = tk.Frame(left, bg=BG)
    chat_wrap.pack(side="top", fill="both", expand=True)
    canvas = tk.Canvas(chat_wrap, bg=BG, highlightthickness=0, bd=0)
    vsb = ttk.Scrollbar(chat_wrap, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=BG)
    inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    wrap_bubbles, resize_job, scroll_job = [], {"id": None}, {"id": None}

    def bubble_width():
        w = canvas.winfo_width()
        return max(300, int(w * 0.64)) if w > 1 else 640

    def rewrap():
        mw = bubble_width()
        for b in wrap_bubbles:
            b.set_max_width(mw)

    def on_inner_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def on_canvas_configure(e):
        canvas.itemconfig(inner_id, width=e.width)
        if resize_job["id"]:
            window.after_cancel(resize_job["id"])
        resize_job["id"] = window.after(80, rewrap)

    inner.bind("<Configure>", on_inner_configure)
    canvas.bind("<Configure>", on_canvas_configure)

    def smooth_scroll():
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        top, bottom = canvas.yview()
        if bottom - top >= 0.999:
            return
        target = max(0.0, 1.0 - (bottom - top))
        if scroll_job["id"]:
            window.after_cancel(scroll_job["id"])

        def step(i=1, steps=10):
            t = i / steps
            canvas.yview_moveto(top + (target - top) * (1 - (1 - t) ** 3))
            if i < steps:
                scroll_job["id"] = window.after(16, lambda: step(i + 1))
        step()

    def on_wheel(e):
        under = window.winfo_containing(e.x_root, e.y_root)
        if under is None or not str(under).startswith(str(chat_wrap)):
            return
        if inner.winfo_height() <= canvas.winfo_height():
            return
        if getattr(e, "num", 0) == 4:
            canvas.yview_scroll(-2, "units")
        elif getattr(e, "num", 0) == 5:
            canvas.yview_scroll(2, "units")
        else:
            canvas.yview_scroll(-2 if e.delta > 0 else 2, "units")

    window.bind_all("<MouseWheel>", on_wheel)
    window.bind_all("<Button-4>", on_wheel)
    window.bind_all("<Button-5>", on_wheel)

    def avatar(parent, blank=False):
        av = tk.Canvas(parent, width=34, height=34, bg=BG, highlightthickness=0, bd=0)
        if not blank:
            av.create_oval(2, 2, 32, 32, fill=SURFACE2, outline=BORDER)
            av.create_text(17, 17, text="🧾", font=(FONT_FAMILY, 11))
        av.pack(side="left", anchor="n", padx=(0, 10))

    def add_message(text, who):
        stamp = datetime.datetime.now().strftime("%H:%M")
        for i, part in enumerate(text.split(TABLE)):
            part = part.strip("\n")
            if not part:
                continue
            row = tk.Frame(inner, bg=BG)
            row.pack(fill="x", padx=14, pady=(7, 2))
            if who == "user":
                col = tk.Frame(row, bg=BG)
                col.pack(side="right")
                b = Bubble(col, part, ACCENT, "#ffffff", (FONT_FAMILY, 11), bubble_width())
                wrap_bubbles.append(b)
                anchor = "e"
            else:
                avatar(row, blank=(i > 0))
                col = tk.Frame(row, bg=BG)
                col.pack(side="left")
                anchor = "w"
                if i > 0:        # table / list: monospace, no wrapping
                    b = Bubble(col, part, SURFACE, TEXT, (MONO_FAMILY, 10), 0, outline=BORDER)
                else:
                    fill, fg = SURFACE2, TEXT
                    if part.startswith("Invoice generated"):
                        fill, fg = "#10382a", "#86efac"
                    elif part.startswith(("Sorry", "Something went wrong", "⚠")):
                        fill, fg = "#3a1519", "#ff9aa0"
                    b = Bubble(col, part, fill, fg, (FONT_FAMILY, 11), bubble_width())
                    wrap_bubbles.append(b)
            b.pack(anchor=anchor)
            if i == 0:
                tk.Label(col, text=stamp, bg=BG, fg=MUTED, font=(FONT_FAMILY, 8)).pack(anchor=anchor, padx=6)
            b.fade_in()
        smooth_scroll()

    def show_typing():
        row = tk.Frame(inner, bg=BG)
        row.pack(fill="x", padx=14, pady=(7, 2))
        avatar(row)
        TypingDots(row).pack(side="left")
        smooth_scroll()
        return row

    def refresh_panel():
        tree.delete(*tree.get_children())
        for sl, desc, qty, price, total, unit in bot.items:
            tree.insert("", "end", values=(sl, desc, fmt_qty(qty, unit), fmt_price(price, unit), f"{total:.2f}"))
        c = bot.customer
        cust_label.config(text=c["name"] or "No customer yet")
        inv_label.config(text=f"Invoice {bot.invoice_no}   •   {bot.date}")
        contact_label.config(text=f"Phone: {c['phone'] or '-'}    TRN: {c['trn'] or '-'}")
        sub, vat, net = bot.totals()
        sub_v.config(text=f"{sub:,.2f}")
        vat_v.config(text=f"{vat:,.2f}")
        net_v.config(text=f"{net:,.2f}")

    # ---------- sending ---------- #

    def reply_later(reply):
        typing = show_typing()

        def finish():
            typing.destroy()
            refresh_panel()
            add_message(reply, "bot")
            if speak_var.get():
                speaker.say(speakable(reply, bot.totals()[2] if bot.items else None))
        window.after(420, finish)

    def submit(text=None):
        if text is None:
            text = entry.get()
            entry.delete(0, "end")
        text = text.strip()
        if not text:
            return
        add_message(text, "user")
        try:
            reply = bot.handle(text)
        except Exception as e:          # never let the chat crash
            reply = f"Something went wrong: {e}"
        if reply:
            reply_later(reply)
        entry.focus()

    # ================= voice assistant (UI) ================= #

    voice_host = tk.Frame(bar, bg=BG)
    voice_host.pack(fill="x")

    # --- listening / recognising card --- #
    listen_card = tk.Frame(voice_host, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
    listen_title = tk.Label(listen_card, text="", bg=SURFACE, fg=TEXT, font=(FONT_FAMILY, 12, "bold"))
    listen_title.pack(anchor="w", padx=20, pady=(14, 2))
    listen_sub = tk.Label(listen_card, text="", bg=SURFACE, fg=MUTED, font=(FONT_FAMILY, 9))
    listen_sub.pack(anchor="w", padx=20)
    wave = WaveBars(listen_card, width=560, page_bg=SURFACE)
    wave.pack(anchor="w", padx=20, pady=(8, 14))

    # --- confirmation card --- #
    confirm_card = tk.Frame(voice_host, bg=SURFACE, highlightbackground=ACCENT, highlightthickness=1)
    tk.Label(confirm_card, text="🎙  Did I hear you right?", bg=SURFACE, fg=TEXT,
             font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=20, pady=(14, 4))

    lang_row = tk.Frame(confirm_card, bg=SURFACE)
    lang_row.pack(fill="x", padx=20)
    lang_dot = tk.Label(lang_row, text="●", bg=SURFACE, fg=GREEN, font=(FONT_FAMILY, 10))
    lang_dot.pack(side="left")
    lang_info = tk.Label(lang_row, text="", bg=SURFACE, fg=TEXT, font=(FONT_FAMILY, 10, "bold"))
    lang_info.pack(side="left", padx=(6, 0))
    confirm_lang = ttk.Combobox(lang_row, values=[n for n, _, _ in LANGUAGES], state="readonly", width=13)
    ttk.Button(lang_row, text="↻ Re-recognise", style="Chip.TButton",
               command=lambda: rerecognise()).pack(side="right")
    confirm_lang.pack(side="right", padx=(0, 8))
    tk.Label(lang_row, text="Wrong language?", bg=SURFACE, fg=MUTED, font=(FONT_FAMILY, 9)).pack(
        side="right", padx=(0, 8))

    heard_label = tk.Label(confirm_card, text="", bg=SURFACE, fg=MUTED, font=(FONT_FAMILY, 10),
                           justify="left", anchor="w", wraplength=700)
    heard_label.pack(fill="x", padx=20, pady=(8, 0))
    tk.Label(confirm_card, text="This is what I'll send to the assistant (you can edit it):", bg=SURFACE,
             fg=MUTED, font=(FONT_FAMILY, 9)).pack(anchor="w", padx=20, pady=(10, 4))
    confirm_box_entry = RoundedEntry(confirm_card, (FONT_FAMILY, 12), height=46, page_bg=SURFACE, fill=SURFACE2)
    confirm_box_entry.pack(fill="x", padx=20)
    warn_label = tk.Label(confirm_card, text="", bg=SURFACE, fg=AMBER, font=(FONT_FAMILY, 9),
                          justify="left", anchor="w", wraplength=700)
    warn_label.pack(fill="x", padx=20, pady=(6, 0))

    confirm_btns = tk.Frame(confirm_card, bg=SURFACE)
    confirm_btns.pack(fill="x", padx=20, pady=(10, 16))
    ttk.Button(confirm_btns, text="✔  Yes, send it", style="Success.TButton",
               command=lambda: confirm_send()).pack(side="left", ipady=2)
    ttk.Button(confirm_btns, text="🎤  Speak again", style="Muted.TButton",
               command=lambda: speak_again()).pack(side="left", padx=8, ipady=2)
    ttk.Button(confirm_btns, text="✖  Cancel", style="Muted.TButton",
               command=lambda: cancel_voice()).pack(side="left", ipady=2)

    def show_card(which):
        for card in (listen_card, confirm_card):
            card.pack_forget()
        if which is not None:
            which.pack(fill="x", pady=(0, 10))
            smooth_scroll()

    def set_mode(mode):
        vs["mode"] = mode
        mic.set_state({"listening": "listening", "processing": "processing"}.get(mode, "idle"))

    def selected_language():
        return LANG_CODE_BY_NAME.get(lang_var.get())

    # ---------- recording ---------- #

    def start_listening():
        if not voice.available:
            message_box(window, "Voice assistant", voice.problem, "info")
            return
        if vs["mode"] == "listening":
            vs["stop"].set()                       # tap again = stop now
            return
        if vs["mode"] == "processing":
            return
        show_card(None)
        stop = threading.Event()
        vs["stop"] = stop
        wave.reset()
        wave.active = True
        listen_title.config(text="🎤  Listening…")
        listen_sub.config(text="Speak naturally in any language. I'll stop when you pause "
                               "(or tap the red button).")
        set_mode("listening")
        show_card(listen_card)

        def work():
            try:
                audio = voice.record(stop, lambda lv: ui_q.put(("level", lv)))
                ui_q.put(("recorded", audio))
            except Exception as e:
                ui_q.put(("error", f"I couldn't use the microphone: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def recognise(audio, language):
        set_mode("processing")
        wave.active = False
        listen_title.config(text="✨  Recognising what you said…")
        listen_sub.config(text="Finding the language and writing it down.")
        show_card(listen_card)
        hint = voice.build_hint(bot.stock)

        def work():
            try:
                ui_q.put(("result", voice.transcribe(audio, language, hint)))
            except Exception as e:
                ui_q.put(("error", f"Speech recognition failed: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def on_recorded(audio):
        if audio is None:
            set_mode("idle")
            show_card(None)
            add_message("I didn't hear anything. Tap the microphone and try again, a little closer to it.", "bot")
            return
        vs["audio"] = audio
        recognise(audio, selected_language())

    def on_result(res):
        vs["res"] = res
        if not res["text"].strip():
            set_mode("idle")
            show_card(None)
            add_message("I couldn't make out any words. Please try again.", "bot")
            return
        set_mode("idle")
        code, conf = res["lang"], res["confidence"]
        name = LANG_NAMES.get(code, (code or "unknown").upper())
        if conf is None:
            lang_info.config(text=f"Language: {name}")
        else:
            lang_info.config(text=f"Detected language: {name}  ({conf * 100:.0f}% sure)")
        lang_dot.config(fg=GREEN if (conf is None or conf >= 0.8) else AMBER)
        confirm_lang.set(name if name in LANG_CODE_BY_NAME else "Auto-detect")

        warn = ""
        if res["engine"] == "google" and code != "en":
            warn = ("Translating to English needs the faster-whisper package. "
                    "Please edit the text so the assistant can understand it.")
        elif conf is not None and conf < 0.6:
            warn = ("I'm not very sure about the language. If this looks wrong, choose the right language "
                    "on the right and tap Re-recognise.")
        warn_label.config(text=warn)
        heard_label.config(text=(f"You said ({name}):  {res['text']}" if code != "en" else ""))

        send_text = spoken_to_digits(res["english"]) if (code == "en" or res["engine"] == "whisper") else res["english"]
        e = confirm_box_entry.entry
        e.delete(0, "end")
        e.insert(0, send_text)
        show_card(confirm_card)
        e.focus_set()
        e.icursor("end")

    def rerecognise():
        if vs["audio"] is None:
            return
        recognise(vs["audio"], LANG_CODE_BY_NAME.get(confirm_lang.get()))

    def confirm_send():
        text = confirm_box_entry.entry.get().strip()
        show_card(None)
        set_mode("idle")
        if text:
            submit(text)

    def speak_again():
        show_card(None)
        set_mode("idle")
        start_listening()

    def cancel_voice():
        show_card(None)
        set_mode("idle")
        entry.focus()

    confirm_box_entry.entry.bind("<Return>", lambda e: confirm_send())
    confirm_box_entry.entry.bind("<Escape>", lambda e: cancel_voice())

    # ---------- background results -> UI ---------- #

    def poll():
        try:
            while True:
                kind, data = ui_q.get_nowait()
                if kind == "level":
                    mic.set_level(data)
                    wave.push(data)
                elif kind == "recorded":
                    on_recorded(data)
                elif kind == "result":
                    on_result(data)
                elif kind == "status":
                    voice_status.config(text=data)
                elif kind == "error":
                    set_mode("idle")
                    show_card(None)
                    add_message("⚠ " + data, "bot")
        except queue.Empty:
            pass
        window.after(40, poll)

    # ================= input bar ================= #

    chips = tk.Frame(bar, bg=BG)
    chips.pack(fill="x", pady=(0, 8))
    for label, cmd in (("📋 Show", "show"), ("📦 Stock list", "stock list"), ("＋ New", "new"), ("❓ Help", "help")):
        ttk.Button(chips, text=label, style="Chip.TButton", command=lambda c=cmd: submit(c)).pack(
            side="left", padx=(0, 6))

    lang_var = tk.StringVar(value="Auto-detect")
    ttk.Combobox(chips, textvariable=lang_var, values=[n for n, _, _ in LANGUAGES],
                 state="readonly", width=13).pack(side="right")
    tk.Label(chips, text="🌐 Voice language", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9)).pack(
        side="right", padx=(0, 6))
    speak_var = tk.BooleanVar(value=False)
    if speaker.ok:
        ttk.Checkbutton(chips, text="🔊 Speak replies", variable=speak_var).pack(side="right", padx=(0, 16))
    voice_status = tk.Label(chips, text="", bg=BG, fg=MUTED, font=(FONT_FAMILY, 9))
    voice_status.pack(side="right", padx=(0, 16))

    row = tk.Frame(bar, bg=BG)
    row.pack(fill="x")
    box = RoundedEntry(row, (FONT_FAMILY, 12), height=54)
    box.pack(side="left", fill="x", expand=True)
    entry = box.entry
    entry.bind("<Return>", lambda e: submit())
    mic = MicButton(row, start_listening)
    mic.pack(side="left", padx=(10, 0))
    ttk.Button(row, text="Send  ➤", style="Accent.TButton", command=submit).pack(
        side="left", padx=(10, 0), ipady=7)

    # ================= start ================= #

    def on_close():
        if vs["stop"] is not None:
            vs["stop"].set()
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", on_close)

    if voice.whisper_ok and voice.mic_ok:           # load the speech model in the background
        threading.Thread(target=lambda: voice.load_model(lambda s: ui_q.put(("status", s))),
                         daemon=True).start()
    elif not voice.available:
        voice_status.config(text="Voice: setup needed (tap the mic)")

    refresh_panel()
    add_message(f"Hi {current_user.split(' ')[0] if current_user else 'there'}! I'm your invoice assistant.\n"
                "Start with the customer, e.g. \"invoice for Ahmed Ali\", then tell me the items:\n"
                "  •  by piece:  3 laptops at 2500\n"
                "  •  by weight:  500g tomatoes  or  1.5 kg onions\n"
                "  •  just checking a price:  price of 250g saffron\n"
                "Or tap the 🎤 and speak, in any language: I'll show you what I heard before sending it.\n"
                "Type \"help\" anytime.", "bot")
    entry.focus()
    fade_in_window(window)
    window.after(40, poll)
    window.mainloop()


# ================= LOGIN (Name + Phone) ================= #

def login_screen():
    """Returns the logged-in user's name, or None if the window was closed."""
    result = {"user": None}
    root = tk.Tk()
    root.title("Login - Pro Invoice App")
    setup_theme(root)

    outer = ttk.Frame(root, padding=(34, 28))
    outer.pack(fill="both", expand=True)
    tk.Label(outer, text="🧾", bg=BG, fg=TEXT, font=(FONT_FAMILY, 40)).pack()
    ttk.Label(outer, text="Welcome", style="Title.TLabel").pack(pady=(2, 0))
    ttk.Label(outer, text="Sign in to create invoices", style="Muted.TLabel").pack(pady=(2, 18))

    card = ttk.Frame(outer, style="Card.TFrame", padding=22)
    card.pack(fill="x")
    ttk.Label(card, text="Full Name", style="CardMuted.TLabel").pack(anchor="w")
    name_e = ttk.Entry(card, width=32)
    name_e.pack(fill="x", pady=(4, 12))
    ttk.Label(card, text="Phone Number", style="CardMuted.TLabel").pack(anchor="w")
    phone_e = ttk.Entry(card, width=32)
    phone_e.pack(fill="x", pady=(4, 0))

    def submit(event=None):
        ok, res = login_or_register(name_e.get(), phone_e.get())
        if not ok:
            error_box(root, "Login failed", res)
            return
        result["user"] = res
        root.destroy()

    ttk.Button(outer, text="Login", style="Accent.TButton", command=submit).pack(
        fill="x", pady=(18, 8), ipady=3)
    ttk.Label(outer, text="New here? Just enter your name and phone number\nand you'll be registered automatically.",
              style="Muted.TLabel", justify="center").pack()
    name_e.bind("<Return>", lambda e: phone_e.focus())
    phone_e.bind("<Return>", submit)

    place_window(root, None, 420, 520)
    name_e.focus()
    fade_in_window(root)
    root.mainloop()
    return result["user"]


def run():
    try:
        user = login_screen()
        if user:
            main_app(user)
    except Exception:
        text = traceback.format_exc()
        log_error(text)
        print(text)
        try:
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Pro Invoice - startup error",
                                 "The app hit an error and had to close.\n\n"
                                 f"It was saved to:\n{file_path('error_log.txt')}\n\n" + text[-900:])
        except Exception:
            pass


if __name__ == "__main__":
    run()
