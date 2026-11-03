#!/usr/bin/env python3
"""
Scientific Calculator
=====================
Run:
    python calculator.py          -> GUI (Tkinter)
    python calculator.py --cli    -> command-line calculator

Features
--------
* + - * / // % ** (and ^ for power), parentheses, factorial with !
* Trig (sin cos tan asin acos atan) with DEG / RAD mode
* Hyperbolic (sinh cosh tanh asinh acosh atanh)
* log (base 10), ln, log2, logb(x, base), exp, sqrt, cbrt, root(x, n)
* abs, floor, ceil, round, factorial, nPr, nCr, gcd, lcm, mod, pow
* degrees(), radians(), sign(), hypot()
* Constants: pi, e, tau, phi (golden ratio)
* ans (last result), memory (M+, M-, MR, MC)
* Safe evaluation: no eval() of arbitrary code (uses the ast module)
"""

import ast
import math
import operator
import re
import sys

# --------------------------------------------------------------------------
# Calculation engine
# --------------------------------------------------------------------------


class CalcError(Exception):
    """Raised for any user-facing calculation error."""


class Calculator:
    def __init__(self):
        self.angle_mode = "DEG"  # "DEG" or "RAD"
        self.ans = 0.0
        self.memory = 0.0
        self.history = []

    # ----- angle helpers -------------------------------------------------
    def _to_rad(self, x):
        return math.radians(x) if self.angle_mode == "DEG" else x

    def _from_rad(self, x):
        return math.degrees(x) if self.angle_mode == "DEG" else x

    # ----- function table ------------------------------------------------
    def _functions(self):
        def fact(n):
            if n != int(n) or n < 0:
                raise CalcError("factorial needs a non-negative integer")
            if n > 1000:
                raise CalcError("factorial argument too large")
            return math.factorial(int(n))

        def npr(n, r):
            self._check_int(n, r)
            return math.perm(int(n), int(r))

        def ncr(n, r):
            self._check_int(n, r)
            return math.comb(int(n), int(r))

        def gcd(*a):
            self._check_int(*a)
            return math.gcd(*[int(x) for x in a])

        def lcm(*a):
            self._check_int(*a)
            return math.lcm(*[int(x) for x in a])

        def root(x, n):
            if n == 0:
                raise CalcError("root degree cannot be 0")
            if x < 0:
                if int(n) == n and int(n) % 2 == 1:
                    return -((-x) ** (1 / n))
                raise CalcError("even root of a negative number")
            return x ** (1 / n)

        def cbrt(x):
            return math.copysign(abs(x) ** (1 / 3), x)

        def sign(x):
            return (x > 0) - (x < 0)

        return {
            # trig
            "sin": lambda x: math.sin(self._to_rad(x)),
            "cos": lambda x: math.cos(self._to_rad(x)),
            "tan": lambda x: math.tan(self._to_rad(x)),
            "asin": lambda x: self._from_rad(math.asin(x)),
            "acos": lambda x: self._from_rad(math.acos(x)),
            "atan": lambda x: self._from_rad(math.atan(x)),
            "atan2": lambda y, x: self._from_rad(math.atan2(y, x)),
            "sec": lambda x: 1 / math.cos(self._to_rad(x)),
            "csc": lambda x: 1 / math.sin(self._to_rad(x)),
            "cot": lambda x: 1 / math.tan(self._to_rad(x)),
            # hyperbolic
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            "asinh": math.asinh,
            "acosh": math.acosh,
            "atanh": math.atanh,
            # logs / exponents / roots
            "log": math.log10,
            "log10": math.log10,
            "ln": math.log,
            "log2": math.log2,
            "logb": lambda x, b: math.log(x, b),
            "exp": math.exp,
            "sqrt": math.sqrt,
            "cbrt": cbrt,
            "root": root,
            "pow": math.pow,
            # rounding / misc
            "abs": abs,
            "floor": math.floor,
            "ceil": math.ceil,
            "round": round,
            "trunc": math.trunc,
            "sign": sign,
            "mod": math.fmod,
            "hypot": math.hypot,
            "degrees": math.degrees,
            "radians": math.radians,
            # combinatorics / number theory
            "factorial": fact,
            "fact": fact,
            "npr": npr,
            "ncr": ncr,
            "gcd": gcd,
            "lcm": lcm,
            "min": min,
            "max": max,
            "sum": lambda *a: sum(a),
        }

    @staticmethod
    def _check_int(*vals):
        for v in vals:
            if v != int(v) or v < 0:
                raise CalcError("arguments must be non-negative integers")

    def _constants(self):
        return {
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "phi": (1 + math.sqrt(5)) / 2,
            "ans": self.ans,
            "mem": self.memory,
        }

    # ----- parsing -------------------------------------------------------
    _BIN = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    _UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    @staticmethod
    def _preprocess(expr):
        s = expr.strip()
        s = (s.replace("×", "*").replace("÷", "/").replace("−", "-")
              .replace("π", "pi").replace("√", "sqrt").replace("^", "**"))
        # factorial postfix:  5!  ->  factorial(5);  (2+3)! handled below
        s = re.sub(r"(\d+(?:\.\d+)?)!", r"factorial(\1)", s)
        # simple parenthesised group factorial, e.g. (2+3)!
        while True:
            m = re.search(r"\(([^()]*)\)!", s)
            if not m:
                break
            s = s[:m.start()] + "factorial(" + m.group(1) + ")" + s[m.end():]
        # implicit multiplication:  2pi, 3(4+1), 2sin(30), )(
        # (numbers that are part of a name, like log10 / log2 / atan2, are skipped)
        s = re.sub(r"(?<![A-Za-z_\d.])(\d+(?:\.\d+)?)\s*([A-Za-z(])", r"\1*\2", s)
        s = re.sub(r"(\))\s*([\dA-Za-z(])", r"\1*\2", s)
        # keep scientific notation such as 1e5 intact
        s = re.sub(r"(?<![A-Za-z])(\d+(?:\.\d+)?)\*e(?=[+\-]?\d)", r"\1e", s)
        return s

    def _eval(self, node, funcs, consts):
        if isinstance(node, ast.Expression):
            return self._eval(node.body, funcs, consts)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise CalcError("invalid value")
        if isinstance(node, ast.BinOp):
            op = self._BIN.get(type(node.op))
            if op is None:
                raise CalcError("unsupported operator")
            a = self._eval(node.left, funcs, consts)
            b = self._eval(node.right, funcs, consts)
            if isinstance(node.op, ast.Pow) and abs(b) > 10000:
                raise CalcError("exponent too large")
            return op(a, b)
        if isinstance(node, ast.UnaryOp):
            op = self._UNARY.get(type(node.op))
            if op is None:
                raise CalcError("unsupported operator")
            return op(self._eval(node.operand, funcs, consts))
        if isinstance(node, ast.Name):
            key = node.id.lower()
            if key in consts:
                return consts[key]
            raise CalcError(f"unknown name '{node.id}'")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise CalcError("invalid function call")
            name = node.func.id.lower()
            if name not in funcs:
                raise CalcError(f"unknown function '{node.func.id}'")
            args = [self._eval(a, funcs, consts) for a in node.args]
            return funcs[name](*args)
        raise CalcError("invalid expression")

    # ----- public API ----------------------------------------------------
    def evaluate(self, expr):
        if not expr or not expr.strip():
            raise CalcError("empty expression")
        src = self._preprocess(expr)
        try:
            tree = ast.parse(src, mode="eval")
            result = self._eval(tree, self._functions(), self._constants())
        except CalcError:
            raise
        except ZeroDivisionError:
            raise CalcError("division by zero")
        except OverflowError:
            raise CalcError("result too large")
        except (ValueError, TypeError) as exc:
            raise CalcError(f"math error: {exc}")
        except SyntaxError:
            raise CalcError("syntax error")
        if isinstance(result, complex):
            raise CalcError("complex result")
        self.ans = result
        self.history.append((expr, result))
        return result

    @staticmethod
    def fmt(value):
        """Format a number nicely."""
        if isinstance(value, int):
            return str(value) if abs(value) < 10**15 else f"{value:.10e}"
        if value != value:
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        # clean up float noise such as 0.30000000000000004 or sin(180)=1.2e-16
        if abs(value) < 1e-12:
            return "0"
        text = f"{value:.12g}"
        return text

    # memory
    def mem_add(self, v):
        self.memory += v

    def mem_sub(self, v):
        self.memory -= v

    def mem_clear(self):
        self.memory = 0.0


# --------------------------------------------------------------------------
# Command-line interface
# --------------------------------------------------------------------------

HELP_TEXT = """
Commands:
  deg / rad        switch angle mode          mc / mr / m+ / m-   memory
  history          show past calculations     clear               clear history
  help             this help                  quit / exit         leave

Functions:
  sin cos tan asin acos atan atan2 sec csc cot
  sinh cosh tanh asinh acosh atanh
  log ln log2 logb(x,b) exp sqrt cbrt root(x,n) pow(x,y)
  abs floor ceil round trunc sign mod hypot degrees radians
  factorial (or n!) npr(n,r) ncr(n,r) gcd lcm min max sum
Constants: pi e tau phi ans mem      Operators: + - * / // % ** ^ !
Examples:  sin(30)   2^10   5!   ncr(10,3)   sqrt(2)*pi   log(1000)
"""


def run_cli():
    calc = Calculator()
    print("Scientific Calculator  (type 'help' for commands, 'quit' to exit)")
    while True:
        try:
            line = input(f"[{calc.angle_mode}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        low = line.lower()
        if low in ("quit", "exit", "q"):
            break
        if low == "help":
            print(HELP_TEXT)
        elif low == "deg":
            calc.angle_mode = "DEG"
            print("Angle mode: degrees")
        elif low == "rad":
            calc.angle_mode = "RAD"
            print("Angle mode: radians")
        elif low == "mc":
            calc.mem_clear()
            print("Memory cleared")
        elif low == "mr":
            print(calc.fmt(calc.memory))
        elif low == "m+":
            calc.mem_add(calc.ans)
            print(f"Memory = {calc.fmt(calc.memory)}")
        elif low == "m-":
            calc.mem_sub(calc.ans)
            print(f"Memory = {calc.fmt(calc.memory)}")
        elif low == "history":
            for expr, res in calc.history:
                print(f"  {expr} = {calc.fmt(res)}")
        elif low == "clear":
            calc.history.clear()
            print("History cleared")
        elif line:
            try:
                print("=", calc.fmt(calc.evaluate(line)))
            except CalcError as exc:
                print("Error:", exc)


# --------------------------------------------------------------------------
# GUI (Tkinter)
# --------------------------------------------------------------------------


def run_gui():
    import tkinter as tk
    from tkinter import ttk  # noqa: F401  (kept for easy theming later)

    calc = Calculator()
    root = tk.Tk()
    root.title("Scientific Calculator")
    root.configure(bg="#1e1e2e")
    root.resizable(False, False)

    BG, DISPLAY_BG = "#1e1e2e", "#11111b"
    COLORS = {
        "num": ("#313244", "#cdd6f4"),
        "op": ("#fab387", "#1e1e2e"),
        "fn": ("#45475a", "#89b4fa"),
        "mem": ("#45475a", "#a6e3a1"),
        "ctl": ("#f38ba8", "#1e1e2e"),
        "eq": ("#a6e3a1", "#1e1e2e"),
    }

    history_var = tk.StringVar(value="")
    mode_var = tk.StringVar(value="DEG")
    mem_var = tk.StringVar(value="")

    top = tk.Frame(root, bg=BG)
    top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
    tk.Label(top, textvariable=mode_var, bg=BG, fg="#f9e2af",
             font=("Consolas", 10, "bold")).pack(side="left")
    tk.Label(top, textvariable=mem_var, bg=BG, fg="#a6e3a1",
             font=("Consolas", 10, "bold")).pack(side="left", padx=10)
    tk.Label(top, textvariable=history_var, bg=BG, fg="#6c7086",
             font=("Consolas", 10), anchor="e").pack(side="right", fill="x", expand=True)

    entry_var = tk.StringVar()
    entry = tk.Entry(root, textvariable=entry_var, font=("Consolas", 22),
                     bg=DISPLAY_BG, fg="#cdd6f4", insertbackground="#cdd6f4",
                     relief="flat", justify="right", width=26)
    entry.grid(row=1, column=0, sticky="ew", padx=8, pady=8, ipady=10)
    entry.focus_set()

    def insert(text):
        entry.insert(tk.INSERT, text)
        entry.focus_set()

    def clear():
        entry_var.set("")
        history_var.set("")

    def backspace():
        pos = entry.index(tk.INSERT)
        if pos > 0:
            entry.delete(pos - 1)

    def show_error(msg):
        history_var.set(f"Error: {msg}")

    def equals(event=None):
        expr = entry_var.get()
        try:
            res = calc.evaluate(expr)
        except CalcError as exc:
            show_error(exc)
            return "break"
        history_var.set(expr + " =")
        entry_var.set(calc.fmt(res))
        entry.icursor(tk.END)
        return "break"

    def toggle_mode():
        calc.angle_mode = "RAD" if calc.angle_mode == "DEG" else "DEG"
        mode_var.set(calc.angle_mode)

    def current_value():
        try:
            return calc.evaluate(entry_var.get())
        except CalcError:
            return calc.ans

    def refresh_mem():
        mem_var.set("M" if calc.memory else "")

    def m_plus():
        calc.mem_add(current_value())
        refresh_mem()

    def m_minus():
        calc.mem_sub(current_value())
        refresh_mem()

    def m_recall():
        insert(calc.fmt(calc.memory))

    def m_clear():
        calc.mem_clear()
        refresh_mem()

    def fn(name):
        return lambda: insert(f"{name}(")

    def txt(t):
        return lambda: insert(t)

    # (label, command, style)
    layout = [
        [("DEG/RAD", toggle_mode, "ctl"), ("MC", m_clear, "mem"), ("MR", m_recall, "mem"),
         ("M+", m_plus, "mem"), ("M-", m_minus, "mem"), ("⌫", backspace, "ctl")],
        [("sin", fn("sin"), "fn"), ("cos", fn("cos"), "fn"), ("tan", fn("tan"), "fn"),
         ("(", txt("("), "op"), (")", txt(")"), "op"), ("C", clear, "ctl")],
        [("asin", fn("asin"), "fn"), ("acos", fn("acos"), "fn"), ("atan", fn("atan"), "fn"),
         ("n!", txt("!"), "fn"), ("%", txt("%"), "op"), ("÷", txt("/"), "op")],
        [("sinh", fn("sinh"), "fn"), ("cosh", fn("cosh"), "fn"), ("tanh", fn("tanh"), "fn"),
         ("7", txt("7"), "num"), ("8", txt("8"), "num"), ("9", txt("9"), "num")],
        [("log", fn("log"), "fn"), ("ln", fn("ln"), "fn"), ("log2", fn("log2"), "fn"),
         ("4", txt("4"), "num"), ("5", txt("5"), "num"), ("6", txt("6"), "num")],
        [("√", fn("sqrt"), "fn"), ("∛", fn("cbrt"), "fn"), ("x^y", txt("^"), "fn"),
         ("1", txt("1"), "num"), ("2", txt("2"), "num"), ("3", txt("3"), "num")],
        [("eˣ", fn("exp"), "fn"), ("10ˣ", txt("10^"), "fn"), ("x²", txt("^2"), "fn"),
         ("0", txt("0"), "num"), (".", txt("."), "num"), ("×", txt("*"), "op")],
        [("π", txt("pi"), "fn"), ("e", txt("e"), "fn"), ("Ans", txt("ans"), "fn"),
         ("nPr", fn("npr"), "fn"), ("nCr", fn("ncr"), "fn"), ("-", txt("-"), "op")],
        [("abs", fn("abs"), "fn"), ("gcd", fn("gcd"), "fn"), ("lcm", fn("lcm"), "fn"),
         (",", txt(","), "op"), ("=", equals, "eq"), ("+", txt("+"), "op")],
    ]

    grid = tk.Frame(root, bg=BG)
    grid.grid(row=2, column=0, padx=8, pady=(0, 8))
    for r, row in enumerate(layout):
        for c, (label, cmd, style) in enumerate(row):
            bg, fg = COLORS[style]
            tk.Button(grid, text=label, command=cmd, width=7, height=2,
                      bg=bg, fg=fg, activebackground=fg, activeforeground=bg,
                      relief="flat", font=("Segoe UI", 11, "bold"),
                      bd=0).grid(row=r, column=c, padx=2, pady=2)

    entry.bind("<Return>", equals)
    entry.bind("<KP_Enter>", equals)
    entry.bind("<Escape>", lambda e: clear())

    root.mainloop()


# --------------------------------------------------------------------------

if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        try:
            run_gui()
        except Exception as exc:  # no display / tkinter missing
            print(f"GUI unavailable ({exc}); starting command-line mode.\n")
            run_cli()
