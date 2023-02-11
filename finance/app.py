import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, date, time

from helpers import apology, login_required, lookup, usd, check_security, isint

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # create a table for required information and store it
    table = db.execute("SELECT stock, stock_price, shares, cash, total_value as total_value FROM users, stocks WHERE id = user_id AND user_id IN (?)", session["user_id"])
    # update table information
    for row in table:
        # delete row if all stocks are sold
        if row["shares"] == 0:
            db.execute("DELETE FROM stocks WHERE stock LIKE ?", row["stock"])
        # Update stock price per current market value
        else:
            db.execute("UPDATE stocks SET stock_price = ? WHERE stock LIKE ?", lookup(row["stock"])["price"], row["stock"])
    # update total value for stocks
    db.execute("UPDATE stocks SET total_value = stock_price * shares")
    # save sum of all stocks bought in a dict
    total = db.execute("SELECT SUM(total_value) as total FROM stocks WHERE user_id IN (?)", session["user_id"])

    # re-render table after updating values
    table = db.execute("SELECT stock, stock_price, shares, cash, total_value FROM users, stocks WHERE id = user_id AND user_id IN (?)", session["user_id"])
    # check to see if there are any stocks the users has bought
    check = True
    if len(table) < 1:
        check = False
        # do not show table if stock owned is zero
        table = db.execute("SELECT * FROM users WHERE id IN (?)", session["user_id"])
        total = [{"total" : 0}]
        return render_template("index.html", table=table, total=total, check=check)
    # display table of stocks owned
    return render_template("index.html", table=table, total=total, check=check)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        stock_info = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")
        user = db.execute("SELECT * FROM users WHERE id IN (?)", session["user_id"])
        # check if shares is valid
        if not isint(shares):
            return apology("invalid request", 400)
        shares = float(shares)
        # check if request is valid
        if stock_info == None or shares <= 0:
            return apology("Invalid stock", 400)
        # check if user has enough balance
        elif user[0]["cash"] < shares * float(stock_info["price"]):
            return apology("Insufficient Balace", 400)

        # Add stock name and share bought to a new database
        row = db.execute("SELECT * FROM stocks WHERE stock LIKE ? AND user_id IN (?)", stock_info["symbol"], session["user_id"])
        # if the stock bought is new insert it into database
        if len(row) < 1:
            db.execute("INSERT INTO stocks (user_id, stock, shares, stock_price, total_value) VALUES (?, ?, ?, ?, ?)", session["user_id"], stock_info["symbol"], shares, stock_info["price"], shares * float(stock_info["price"]))
        # if user already has the stock update the shares row
        else:
            new_share = row[0]["shares"] + shares
            db.execute("UPDATE stocks SET shares = ? WHERE stock LIKE ? AND user_id IN (?)", new_share, stock_info["symbol"], session["user_id"])

        # update cash of user
        db.execute("UPDATE users SET cash = ? WHERE id in (?)", user[0]["cash"] - shares * float(stock_info["price"]), session["user_id"])

        # update history
        today = datetime.now()
        my_date = date(today.year, today.month, today.day)
        my_time = time(today.hour, today.minute, today.second)
        db.execute("INSERT INTO history (id, stock, price, shares, status, date, time) VALUES (?, ?, ?, ?, ?, ?, ?)", session["user_id"], stock_info["symbol"], lookup(stock_info["symbol"])["price"], shares, "bought", my_date, my_time)

        return redirect("/")


    return render_template("buy.html")

    # return apology("TODO")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    histories = db.execute("SELECT * FROM history WHERE id IN (?)", session["user_id"])
    if len(histories) < 1:
        return apology("No histories found!")

    return render_template("history.html", history=histories)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        if stock == None:
            return apology("Invalid stock", 400)

        price = usd(stock["price"])
        return render_template("quoted.html", stock=stock, price=price)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # show apology if info is not valid
        data = db.execute("SELECT * FROM users")
        for info in data:
            if username == info["username"]:
                return apology("username alredy exits", 400)
        if not username:
            return apology("must provide username", 400)
        if password != confirmation:
            return apology("confimation does not match password", 400)
        # check if password is secure
        if not check_security(password):
            return apology("Password not secure enough", 400)

        # register user
        hash_pass = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash_pass)
        return redirect("/login")

    return render_template("register.html")
    #return apology("TODO")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        table = db.execute("SELECT * FROM stocks WHERE user_id IN (?)", session["user_id"])
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        new_shares = shares

        # check if shares is valid
        if not isint(shares):
            return apology("invalid request", 400)
        shares = float(shares)

        check = False
        for row in table:
            if symbol == row["stock"] and shares <= row["shares"]:
                check = True
                users = db.execute("SELECT * FROM users WHERE id IN (?)", session["user_id"])
                db.execute("UPDATE users SET cash = ? WHERE id IN (?)", users[0]["cash"] + shares * float(lookup(symbol)["price"]), session["user_id"])
                new_shares = row["shares"] - shares
                break

        if not symbol or not check or shares < 1:
            return apology("invalid request", 400)
        # update shares owned in stocks table
        db.execute("UPDATE stocks SET shares = ? WHERE user_id IN (?) AND stock LIKE ?", new_shares, session["user_id"], symbol)
        # update history
        today = datetime.now()
        my_date = date(today.year, today.month, today.day)
        my_time = time(today.hour, today.minute, today.second)
        db.execute("INSERT INTO history (id, stock, price, shares, status, date, time) VALUES (?, ?, ?, ?, ?, ?, ?)", session["user_id"], symbol, lookup(symbol)["price"], shares, "sold", my_date, my_time)

        return redirect("/")

    table = db.execute("SELECT * FROM stocks WHERE user_id IN (?)", session["user_id"])
    return render_template("sell.html", table=table)


