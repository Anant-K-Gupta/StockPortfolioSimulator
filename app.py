import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

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

    portfolio = db.execute("select name, symbol, price, SUM(quantity) as total_quantity from transactions where user_id=? group by symbol having total_quantity>0", session["user_id"])
    user_cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]
    total_cash = user_cash

    for stock in portfolio:
        price = lookup(stock["symbol"])["price"]
        total = stock["total_quantity"] * price
        stock.update({"price": price, "total": total})
        total_cash += stock["price"]*stock["total_quantity"]

    return render_template("index.html", stocks=portfolio, cash=user_cash, usd=usd, total=total_cash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Please provide stock symbol!")
        if not request.form.get("shares"):
            return apology("Please provide number of shares!")
        if int(request.form.get("shares")) <= 0:
            return apology("Please provide a valid number of shares!")

        quote = lookup(request.form.get("symbol"))

        if quote == None:
            return apology("Please provide a valid stock symbol!")

        share_value = int(request.form.get("shares")) * quote["price"]
        user_cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]

        if user_cash < share_value:
            return apology("The value of purchase exceeds cash in hand!")

        db.execute("update users set cash=cash-? where id=?", share_value, session["user_id"])


        db.execute("insert into transactions (user_id, name, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?, 'buy')", session["user_id"], quote["name"], quote["symbol"], int(request.form.get("shares")), quote["price"])

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    user_history = db.execute("select type, name, symbol, quantity, price, transaction_time from transactions where user_id=? order by transaction_time desc", session["user_id"])
    return render_template("history.html", stocks=user_history, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

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
    if (request.method == "POST"):
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("Please enter a symbol.")

        # lookup the stock
        stock = lookup(symbol.upper())
        if stock == None:
            return apology("Given symbol does not exist.")

        # render the stock quote
        return render_template("quoted.html", symbol=stock["symbol"], name=stock["name"], price=stock["price"], usd=usd)
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # check for blank fields
        if not username:
            return apology("Username is a required field.")
        if not password:
            return apology("Password is a required field.")
        digits = 0
        special = 0
        for i in password:
            if i.isdigit():
                digits += 1
            if not i.isalnum():
                special += 1
        if len(password) < 5 or digits < 1 or special < 1:
            return apology("Password must be minimum 5 character long and have atleast 1 digit and 1 special character.")

        if not confirmation:
            return apology("Please confirm your password.")

        # check for password confirmation and hash
        if (password != confirmation):
            return apology("The given passwords do not match.")

        # check if username already exists
        if len(db.execute("SELECT username FROM users WHERE username = ?", username)) > 0:
            return apology("This username already exists!")

        # hash password and add to database
        hash_password = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (?,?)", username, hash_password)

        # get user id
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # remember user id for session
        session["user_id"] = rows[0]["id"]
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("shares"):
            return apology("Please enter number of shares.")
        quantity = db.execute("select SUM(quantity) as total_quantity from transactions where user_id=? and symbol=?", int(session["user_id"]), request.form.get("symbol"))[0]["total_quantity"]
        if int(request.form.get("shares"))>quantity:
            return apology("You do not have those many shares.")
        quote = lookup(request.form.get("symbol"))
        total_value = quote["price"]*int(request.form.get("shares"))
        db.execute("insert into transactions (user_id, name, symbol, quantity, price, type) VALUES (?, ?, ?, ?, ?, 'sell')", session["user_id"], quote["name"], quote["symbol"], -1*int(request.form.get("shares")), quote["price"])
        db.execute("update users set cash=cash+? where id=?", total_value, session["user_id"])
        return redirect("/")


    else:
        portfolio = db.execute("select distinct(symbol), SUM(quantity) as total_quantity from transactions where user_id=? group by symbol having total_quantity>0 ", session["user_id"])
        return render_template("sell.html", stocks=portfolio)

