import tkinter as tk
from tkinter import ttk, messagebox
from docxtpl import DocxTemplate
from num2words import num2words
import datetime
import difflib
import json
import math
import os
import re
import sys

# ================= SETTINGS ================= #

VAT_RATE = 0.05
CURRENCY_MAIN = "Dirhams"
CURRENCY_SUB = "Fils"
DEFAULT_UNIT = "1 piece"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INVOICE_FOLDER = os.path.join(BASE_DIR, "Invoices")

# ================= DARK THEME ================= #

BG = "#0f1115"
SURFACE = "#171a21"
SURFACE2 = "#1f232c"
BORDER = "#2b303b"
TEXT = "#e7e9ee"
MUTED = "#8a93a6"
ACCENT = "#6c8cff"
ACCENT_DARK = "#2f4fd0"
GREEN = "#22a55b"
GRAY = "#4a5163"
USER_BUBBLE = "#26356e"
BOT_BUBBLE = "#1f232c"

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
                    rowheight=28, borderwidth=0, font=(FONT, 10))
    style.map("Treeview", background=[("selected", ACCENT_DARK)], foreground=[("selected", "white")])
    style.configure("Treeview.Heading", background=SURFACE2, foreground=MUTED, relief="flat",
                    borderwidth=0, padding=(6, 7), font=(FONT, 9, "bold"))
    style.map("Treeview.Heading", background=[("active", BORDER)], foreground=[("active", TEXT)])
    style.configure("Vertical.TScrollbar", background=SURFACE2, troughcolor=BG, bordercolor=BG,
                    arrowcolor=MUTED, lightcolor=SURFACE2, darkcolor=SURFACE2, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", BORDER)])


def make_button(parent, text, color, command, width=None, size=10, pady=7):
    b = tk.Button(parent, text=text, command=command, bg=color, fg="white",
                  activebackground=lighten(color, 0.2), activeforeground="white",
                  relief="flat", bd=0, padx=14, pady=pady, cursor="hand2",
                  font=(FONT, size, "bold"), width=width or 0)
    b.bind("<Enter>", lambda e: b.config(bg=lighten(color, 0.12)))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


def make_entry(parent, width=30, font_size=10):
    return tk.Entry(parent, width=width, bg=SURFACE2, fg=TEXT, insertbackground=TEXT,
                    relief="flat", bd=0, font=(FONT, font_size), highlightthickness=1,
                    highlightbackground=BORDER, highlightcolor=ACCENT)


def center_window(win, w, h):
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


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
    with open(file_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_phone(phone):
    """Keeps digits only (and drops a leading + or 00) so 050-123 4567 == 0501234567."""
    return re.sub(r"\D", "", phone)


def login_or_register(name, phone):
    """
    Name + phone number login. Anyone can log in; a new person is registered
    automatically, so there is no limit on the number of users.
    Returns (ok, message).
    """
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


# ================= STOCK ENTRIES =================
# New format : {"Apples": {"price": 6.0, "unit": "1 kg"}}
# Old format : {"Laptop": 2500.0}   (still understood, treated as "1 piece")

def stock_entry(value):
    """Returns (price, unit) for either stock format."""
    try:
        if isinstance(value, dict):
            price = float(value.get("price", 0))
            unit = str(value.get("unit") or DEFAULT_UNIT).strip()
        else:
            price, unit = float(value), DEFAULT_UNIT
    except (TypeError, ValueError):
        price, unit = 0.0, DEFAULT_UNIT
    return (price if math.isfinite(price) else 0.0), unit


def is_per_kg(unit):
    return re.sub(r"\s+", "", str(unit).lower()) in ("1kg", "kg", "perkg", "/kg")


def format_weight(grams):
    if grams >= 1000:
        return f"{grams / 1000:g} kg"
    return f"{grams:g} g"


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


# ================= CHATBOT BRAIN ================= #

NUM = r"\d+(?:\.\d+)?"
WEIGHT_UNIT = r"(?:kilograms?|kilos?|kgs?|grams?|gms?|g)"

# "500 g apples", "250 grams of tomatoes", "1.5 kg onions"
WEIGHT_FIRST = re.compile(rf"^({NUM})\s*({WEIGHT_UNIT})\s+(?:of\s+)?(.+)$", re.I)
# "apples 500 g", "tomatoes 250 grams"
WEIGHT_LAST = re.compile(rf"^(.+?)\s+({NUM})\s*({WEIGHT_UNIT})$", re.I)
# "price of 500 g apples", "how much is 250 g tomatoes", "cost 750g onions"
PRICE_QUERY = re.compile(r"^(?:price\s+of|price|how\s+much\s+(?:is|are|for)|cost\s+of|cost)\s+(.+)$", re.I)

HELP_TEXT = """Here is what you can tell me:

CUSTOMER
  invoice for Ahmed Ali
  invoice for Ahmed Ali phone 0501234567 trn 100123456700003

ADD ITEMS (one or many, separated by commas)
  3 laptops at 2500
  2 x mouse 50, 5 keyboards at 120
  10 pens          (price is taken from stock)
  If I don't know the price I will ask you.
  Tip: use "at" before the price, e.g. "2 iPhone 15 at 3000"

SELL BY WEIGHT (items priced per kg)
  500 g apples
  250 grams of tomatoes, 1.5 kg onions
  price of 750 g mangoes     (shows the price only)

EDIT
  remove last | remove 2 | remove laptop
  date 25-12-2026

CHECK / FINISH
  show            see the current invoice
  generate        create the Word invoice
  new             start over

STOCK / CUSTOMERS
  stock Laptop 2500      save an item to stock
  stock Apples 6 per kg  save a per-kg item
  stock list             show saved items
  customers              show saved customers"""


class InvoiceBot:
    def __init__(self, on_change=None):
        self.stock = read_json("stock_data.json", {})
        self.customers = read_json("customers_data.json", {})
        self.on_change = on_change or (lambda: None)
        self.reset()

    # ---------- state ---------- #

    def reset(self):
        self.items = []      # [sl, desc, qty, price, total]
        self.pending = []    # items waiting for a price: [qty, desc]
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
    def parse_weight(chunk):
        """Returns (grams, description) for things like '500 g apples', or None."""
        chunk = re.sub(r"^(?:please\s+)?(?:add|put|include)\s+", "", chunk.strip(), flags=re.I)
        m = WEIGHT_FIRST.match(chunk)
        if m:
            amount, unit, desc = float(m.group(1)), m.group(2).lower(), m.group(3)
        else:
            m = WEIGHT_LAST.match(chunk)
            if not m:
                return None
            desc, amount, unit = m.group(1), float(m.group(2)), m.group(3).lower()
        grams = amount * 1000 if unit.startswith("k") else amount
        desc = desc.strip()
        if not desc or not re.search(r"[A-Za-z]", desc):
            return None
        return grams, desc

    @staticmethod
    def parse_item(chunk):
        """Returns (qty, description, price or None), or None if not an item."""
        chunk = re.sub(r"^(?:please\s+)?(?:add|put|include)\s+", "", chunk.strip(), flags=re.I)
        chunk = re.sub(r"\s*(?:aed|dirhams?|dhs)\b", "", chunk, flags=re.I)
        if not re.search(r"[A-Za-z]", chunk):
            return None

        qty, rest = 1, chunk
        m = re.match(rf"^({NUM})\s*(?:x|×|pcs?|units?|nos)?\s+(.+)$", chunk, re.I)
        m2 = re.match(rf"^(.+?)\s+[x×]\s*(\d+)\s*(.*)$", chunk, re.I)
        if m:
            qty, rest = int(float(m.group(1))), m.group(2)
        elif m2:
            qty, rest = int(m2.group(2)), (m2.group(1) + " " + m2.group(3)).strip()

        price = None
        p = re.match(rf"^(.+?)\s*(?:at|@|for|price|each)\s*({NUM})\s*(?:each|/-)?$", rest, re.I)
        if not p:
            p = re.match(rf"^(.+?)\s+({NUM})\s*(?:each|/-)?$", rest, re.I)
        if p:
            rest, price = p.group(1), float(p.group(2))

        desc = re.sub(r"\s*(?:each|@|at)$", "", rest.strip(), flags=re.I).strip()
        if not desc or qty <= 0:
            return None
        return qty, desc, price

    # ---------- display ---------- #

    def invoice_text(self):
        lines = [f"Invoice {self.invoice_no}   Date: {self.date}"]
        c = self.customer
        lines.append("Customer: " + (c["name"] or "(not set)") +
                     (f"   Phone: {c['phone']}" if c["phone"] else "") +
                     (f"   TRN: {c['trn']}" if c["trn"] else ""))
        if not self.items:
            lines.append("No items yet.")
            return "\n".join(lines)
        lines.append("")
        lines.append(f"{'#':<3}{'Description':<24}{'Qty':>5}{'Price':>11}{'Total':>12}")
        for sl, desc, qty, price, total in self.items:
            lines.append(f"{sl:<3}{desc[:23]:<24}{qty:>5}{price:>11.2f}{total:>12.2f}")
        sub, vat, net = self.totals()
        lines.append("-" * 55)
        lines.append(f"{'Subtotal':<43}{sub:>12.2f}")
        lines.append(f"{f'VAT {VAT_RATE * 100:g}%':<43}{vat:>12.2f}")
        lines.append(f"{'NET TOTAL':<43}{net:>12.2f}")
        return "\n".join(lines)

    # ---------- actions ---------- #

    def add_item(self, qty, desc, price):
        match = self.find_stock(desc)
        if match:
            desc_final = match
            if price is None:
                price = stock_entry(self.stock[match])[0]
        else:
            desc_final = desc[:1].upper() + desc[1:]
        if price is None:
            self.pending.append([qty, desc_final])
            return None
        self.items.append([len(self.items) + 1, desc_final, qty, price, round(qty * price, 2)])
        return f"{qty} x {desc_final} @ {price:.2f}"

    def weight_price(self, grams, desc):
        """
        Calculates the price for `grams` of a per-kg stock item.
        Returns (ok, name, price_per_kg, amount) on success, or (False, message, None, None).
        """
        if grams <= 0:
            return False, "The weight must be more than zero.", None, None
        match = self.find_stock(desc)
        if not match:
            return False, f"\"{desc}\" is not in stock. Ask the admin to add it as a per-kg item.", None, None
        price, unit = stock_entry(self.stock[match])
        if not is_per_kg(unit):
            return False, (f"{match} is not sold by weight (it is priced per {unit}). "
                           f"Try e.g. \"2 {match.lower()}\"."), None, None
        return True, match, price, round(price * grams / 1000, 2)

    def add_weight_item(self, grams, desc):
        """Adds a weighed item to the invoice. Returns (ok, text)."""
        ok, name, per_kg, amount = self.weight_price(grams, desc)
        if not ok:
            return False, name
        label = format_weight(grams)
        self.items.append([len(self.items) + 1, f"{name} ({label})", 1, amount, amount])
        return True, f"{label} {name} @ {per_kg:.2f}/kg = {amount:.2f} AED"

    def ask_next_pending(self):
        qty, desc = self.pending[0]
        return f"I don't have a price for \"{desc}\". What is the price for 1 unit? (or type skip)"

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
        return f"Removed {removed[2]} x {removed[1]}."

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
            "invoice_list": [[i[0], i[1], i[2], f"{i[3]:.2f}", f"{i[4]:.2f}"] for i in self.items],
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

        # pick up any changes the admin made to the stock file
        self.stock = read_json("stock_data.json", self.stock)

        # waiting for a price?
        if self.pending:
            m = re.match(rf"^(?:aed\s*)?({NUM})\s*(?:aed|dirhams?|each)?$", low)
            if m:
                qty, desc = self.pending.pop(0)
                price = float(m.group(1))
                self.items.append([len(self.items) + 1, desc, qty, price, round(qty * price, 2)])
                reply = f"Added {qty} x {desc} @ {price:.2f}."
                if self.pending:
                    reply += "\n" + self.ask_next_pending()
                else:
                    reply += "\n\n" + self.invoice_text()
                self.on_change()
                return reply
            if low in ("skip", "cancel", "no"):
                dropped = self.pending.pop(0)
                reply = f"Skipped {dropped[1]}."
                if self.pending:
                    reply += "\n" + self.ask_next_pending()
                return reply
            self.pending.clear()   # they said something else, so drop the question

        if re.match(r"^(help|\?|commands|hi|hello)$", low):
            return HELP_TEXT

        if re.match(r"^(new|clear|reset|cancel)(\s+invoice)?$", low):
            self.reset()
            self.on_change()
            return "Started a fresh invoice. Who is it for?"

        if re.match(r"^(show|list|view|total|summary|invoice|preview)$", low):
            return self.invoice_text()

        if re.match(r"^(generate|done|finish|finished|create|print|make)(\s+(the\s+)?invoice)?$", low):
            reply = self.generate()
            self.on_change()
            return reply

        m = re.match(r"^(?:remove|delete)\s+(.+)$", low)
        if m:
            reply = self.remove(m.group(1))
            self.on_change()
            return reply

        m = re.match(r"^date\s+(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", low)
        if m:
            self.date = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}-{m.group(3)}"
            self.on_change()
            return f"Date set to {self.date}."

        if re.match(r"^(stock list|stock|items|show stock)$", low):
            if not self.stock:
                return "Stock is empty. Add with: stock Laptop 2500"
            lines = []
            for k, v in self.stock.items():
                price, unit = stock_entry(v)
                lines.append(f"  {k}: {price:.2f} / {unit}")
            return "Stock:\n" + "\n".join(lines)

        if re.match(r"^(customers|customer list|show customers)$", low):
            if not self.customers:
                return "No saved customers yet."
            return "Customers:\n" + "\n".join(f"  {k}" for k in self.customers)

        # price check only:  "price of 500 g apples"
        m = PRICE_QUERY.match(text)
        if m:
            w = self.parse_weight(m.group(1))
            if w:
                ok, name, per_kg, amount = self.weight_price(*w)
                if not ok:
                    return name
                return f"{format_weight(w[0])} of {name} @ {per_kg:.2f}/kg = {amount:.2f} AED"

        m = re.match(rf"^(?:add to stock|stock|save item)\s+(.+?)\s+(?:at\s+|@\s*)?({NUM})\s*(?:(?:per|/)\s*kg)?$", text, re.I)
        if m:
            per_kg = bool(re.search(r"(?:per|/)\s*kg\s*$", text, re.I))
            name, price = m.group(1).strip(), float(m.group(2))
            existing = self.find_stock(name)
            name = existing or name[:1].upper() + name[1:]
            if per_kg:
                unit = "1 kg"
            else:
                unit = stock_entry(self.stock[existing])[1] if existing else DEFAULT_UNIT
            self.stock[name] = {"price": round(price, 2), "unit": unit}
            write_json("stock_data.json", self.stock)
            return f"Saved to stock: {name} = {price:.2f} / {unit}"

        m = re.match(r"^(?:invoice for|bill to|customer|client|for)\s+(.+)$", text, re.I)
        if m:
            reply = self.set_customer(m.group(1))
            self.on_change()
            return reply

        # otherwise: treat as items
        added, unknown, problems = [], [], []
        for chunk in self.split_chunks(text):
            w = self.parse_weight(chunk)
            if w:
                ok, result = self.add_weight_item(*w)
                (added if ok else problems).append(result)
                continue
            parsed = self.parse_item(chunk)
            if not parsed:
                unknown.append(chunk)
                continue
            result = self.add_item(*parsed)
            if result:
                added.append(result)

        if not added and not problems and not self.pending:
            return "Sorry, I didn't understand that. Type \"help\" to see what I can do."

        reply = ""
        if added:
            reply += "Added:\n" + "\n".join(f"  - {a}" for a in added)
        if problems:
            reply += ("\n" if reply else "") + "\n".join(problems)
        if unknown:
            reply += "\nI skipped: " + ", ".join(unknown)
        if self.pending:
            reply += ("\n" if reply else "") + self.ask_next_pending()
        elif added:
            reply += "\n\n" + self.invoice_text()
        self.on_change()
        return reply.strip()


# ================= CHAT WINDOW ================= #

def main_app(current_user=""):
    window = tk.Tk()
    window.title("PRO TAX INVOICE CHATBOT")
    apply_theme(window)
    try:
        window.state("zoomed")
    except tk.TclError:
        try:
            window.attributes("-zoomed", True)
        except tk.TclError:
            window.geometry("1200x740")

    # ----- header ----- #
    header = tk.Frame(window, bg=BG)
    header.pack(side="top", fill="x", padx=16, pady=(14, 4))
    tk.Label(header, text="🧾  PRO TAX INVOICE", font=(FONT, 16, "bold"), bg=BG, fg=TEXT).pack(side="left")
    tk.Label(header, text=f"👤  {current_user}", bg=SURFACE2, fg=TEXT, font=(FONT, 9, "bold"),
             padx=12, pady=6).pack(side="right")

    # ----- right panel: live invoice ----- #
    right = tk.Frame(window, bg=SURFACE, width=440)
    right.pack(side="right", fill="y", padx=(0, 16), pady=(8, 16))
    right.pack_propagate(False)

    tk.Label(right, text="LIVE INVOICE", bg=SURFACE, fg=MUTED, font=(FONT, 9, "bold")).pack(
        anchor="w", padx=14, pady=(14, 4))
    info_label = tk.Label(right, text="", bg=SURFACE, fg=TEXT, font=(FONT, 10),
                          justify="left", anchor="w")
    info_label.pack(fill="x", padx=14, pady=(0, 10))

    table_frame = tk.Frame(right, bg=SURFACE)
    table_frame.pack(fill="both", expand=True, padx=10)
    columns = ("SL", "DESC", "QTY", "PRICE", "TOTAL")
    tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)
    widths = {"SL": 32, "DESC": 170, "QTY": 40, "PRICE": 70, "TOTAL": 80}
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=widths[col], anchor="w" if col == "DESC" else "e")
    tree_scroll = ttk.Scrollbar(table_frame, command=tree.yview)
    tree.config(yscrollcommand=tree_scroll.set)
    tree_scroll.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)

    totals_box = tk.Frame(right, bg=SURFACE2)
    totals_box.pack(fill="x", padx=10, pady=10)
    totals_label = tk.Label(totals_box, text="", bg=SURFACE2, fg=TEXT, font=(FONT, 10),
                            justify="right", anchor="e")
    totals_label.pack(fill="x", padx=12, pady=(10, 2))
    net_label = tk.Label(totals_box, text="", bg=SURFACE2, fg=ACCENT, font=(FONT, 15, "bold"),
                         anchor="e")
    net_label.pack(fill="x", padx=12, pady=(0, 10))

    # ----- left panel: chat ----- #
    left = tk.Frame(window, bg=BG)
    left.pack(side="left", fill="both", expand=True, padx=(16, 12), pady=(8, 16))

    # bottom widgets are packed first so they are never squeezed out of view
    entry_row = tk.Frame(left, bg=BG)
    entry_row.pack(side="bottom", fill="x", pady=(10, 0))
    chips = tk.Frame(left, bg=BG)
    chips.pack(side="bottom", fill="x", pady=(10, 0))

    chat_wrap = tk.Frame(left, bg=SURFACE)
    chat_wrap.pack(side="top", fill="both", expand=True)

    chat = tk.Text(chat_wrap, wrap="word", state="disabled", bg=SURFACE, fg=TEXT,
                   font=("Consolas", 11), padx=12, pady=12, relief="flat", bd=0,
                   highlightthickness=0, insertbackground=TEXT, cursor="arrow")
    scroll = ttk.Scrollbar(chat_wrap, command=chat.yview)
    chat.config(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    chat.pack(side="left", fill="both", expand=True)

    chat.tag_configure("user", background=USER_BUBBLE, foreground="white", justify="right",
                       lmargin1=140, lmargin2=140, rmargin=10, spacing1=8, spacing3=8)
    chat.tag_configure("bot", background=BOT_BUBBLE, foreground=TEXT, justify="left",
                       lmargin1=10, lmargin2=10, rmargin=140, spacing1=8, spacing3=8)

    def refresh_panel():
        tree.delete(*tree.get_children())
        for sl, desc, qty, price, total in bot.items:
            tree.insert("", "end", values=(sl, desc, qty, f"{price:.2f}", f"{total:.2f}"))
        c = bot.customer
        info_label.config(text=f"Invoice:  {bot.invoice_no}      Date:  {bot.date}\n"
                               f"Customer:  {c['name'] or '-'}\n"
                               f"Phone:  {c['phone'] or '-'}      TRN:  {c['trn'] or '-'}")
        sub, vat, net = bot.totals()
        totals_label.config(text=f"Subtotal:  {sub:.2f}\nVAT {VAT_RATE * 100:g}%:  {vat:.2f}")
        net_label.config(text=f"NET TOTAL   {net:.2f} AED")

    bot = InvoiceBot(on_change=refresh_panel)

    def say(text, who):
        chat.config(state="normal")
        chat.insert("end", text + "\n", who)
        chat.insert("end", "\n")
        chat.config(state="disabled")
        chat.see("end")

    def send(event=None, preset=None):
        text = (preset or entry.get()).strip()
        if not text:
            return
        entry.delete(0, tk.END)
        say(text, "user")
        try:
            reply = bot.handle(text)
        except Exception as e:  # never let the chat crash
            reply = f"Something went wrong: {e}"
        if reply:
            say(reply, "bot")

    # quick-action chips
    for label, cmd in (("Show", "show"), ("Stock list", "stock list"), ("New", "new"), ("Help", "help")):
        make_button(chips, label, SURFACE2, lambda c=cmd: send(preset=c), size=9, pady=4).pack(
            side="left", padx=(0, 6))

    entry = make_entry(entry_row, font_size=12)
    entry.pack(side="left", fill="x", expand=True, ipady=10)
    entry.bind("<Return>", send)
    make_button(entry_row, "Send  ➤", ACCENT_DARK, send, width=10, pady=9).pack(side="left", padx=(8, 0))
    make_button(entry_row, "Generate", GREEN, lambda: send(preset="generate"), width=10, pady=9).pack(
        side="left", padx=(8, 0))

    refresh_panel()
    say("Hi! I'm your invoice assistant.\n"
        "Start with the customer, e.g. \"invoice for Ahmed Ali\", then just tell me the items, "
        "e.g. \"3 laptops at 2500, 2 mouse\".\n"
        "Fruit & veg sold by weight? Try \"500 g apples\" or \"price of 250 g tomatoes\".\n"
        "Type \"help\" anytime.", "bot")
    entry.focus()
    window.mainloop()


# ================= LOGIN (Name + Phone) ================= #

def run_login():
    login_window = tk.Tk()
    login_window.title("Login - Pro Invoice App")
    apply_theme(login_window)
    center_window(login_window, 430, 470)

    card = tk.Frame(login_window, bg=SURFACE)
    card.pack(fill="both", expand=True, padx=24, pady=24)

    tk.Label(card, text="🧾", bg=SURFACE, font=(FONT, 30)).pack(pady=(22, 0))
    tk.Label(card, text="Welcome", font=(FONT, 16, "bold"), bg=SURFACE, fg=TEXT).pack(pady=(4, 0))
    tk.Label(card, text="Sign in to create invoices", bg=SURFACE, fg=MUTED, font=(FONT, 9)).pack(pady=(2, 8))

    tk.Label(card, text="Full Name", bg=SURFACE, fg=MUTED, font=(FONT, 9, "bold")).pack(
        padx=30, pady=(10, 3), anchor="w")
    name_entry = make_entry(card, width=30)
    name_entry.pack(padx=30, ipady=6, fill="x")

    tk.Label(card, text="Phone Number", bg=SURFACE, fg=MUTED, font=(FONT, 9, "bold")).pack(
        padx=30, pady=(10, 3), anchor="w")
    phone_entry = make_entry(card, width=30)
    phone_entry.pack(padx=30, ipady=6, fill="x")

    def check_login(event=None):
        ok, result = login_or_register(name_entry.get(), phone_entry.get())
        if not ok:
            messagebox.showerror("Login Failed", result, parent=login_window)
            return
        login_window.destroy()
        main_app(result)

    phone_entry.bind("<Return>", check_login)
    name_entry.bind("<Return>", lambda e: phone_entry.focus())

    make_button(card, "Login", ACCENT_DARK, check_login).pack(pady=(20, 10), padx=30, fill="x")
    tk.Label(card, text="New here? Just enter your name and phone\nnumber and you'll be registered automatically.",
             bg=SURFACE, fg=MUTED, font=(FONT, 9)).pack()

    name_entry.focus()
    login_window.mainloop()


if __name__ == "__main__":
    run_login()
