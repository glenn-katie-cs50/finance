import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/", methods=["GET", "POST"])
@login_required
def index():

    if request.method == "GET":

        # get all of the user's transactions from the database
        rows = db.execute("SELECT * FROM transactions WHERE user_id = :user_id", user_id = session["user_id"])

        # create a dictionary to hold each symbol and its information
        dictionary = {}
        totalOverall = 0
        cash = 0

        # we will add to shares if they're "buy" type, and subtract if they're "sell" type
        # using data from the lookup function
        for row in rows:

            symbol = row["symbol"]
            info = lookup(symbol)

            if symbol not in dictionary:
                dictionary[symbol] = {"symbol": symbol, "shares": 0, "price": usd(info["price"]), "total": 0}
            if row["type"] == "buy":
                dictionary[symbol]["shares"] = int(dictionary[symbol]["shares"]) + int(row["shares"])
            elif row["type"] == "sell":
                dictionary[symbol]["shares"] = int(dictionary[symbol]["shares"]) - int(row["shares"])

            dictionary[symbol]["total"] = float(info["price"]) * float(dictionary[symbol]["shares"])

        #get the user's cash and then convert it to a float
        user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session["user_id"])

        cash = float(user[0]["cash"])

        # get the total overall so it can be added to the cash
        for row in dictionary:
            totalOverall = float(totalOverall) + dictionary[row]["total"]

        totalOverall = totalOverall + cash

        # get the total overall again so it can be converted to USD
        for row in dictionary:
            dictionary[row]["total"] = usd(dictionary[row]["total"])

        return render_template("index.html",
            purchase = False,
            dictionary = dictionary,
            cash = usd(cash),
            totalOverall = usd(totalOverall))

    if request.method == "POST":

        if request.form.get("cash").isnumeric() == False or int(request.form.get("cash")) < 0:
            return apology("you must input a cash value, numbers only", 403)

        row = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session["user_id"])

        cash = float(row[0]["cash"]) + float(request.form.get("cash"))

        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash = cash, user_id = session["user_id"])

        newCash = usd(float(request.form.get("cash")))

        return render_template("index.html",
            purchase = True,
            newCash = newCash,
            cash = usd(cash))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 403)

        if lookup(request.form.get("symbol")) == None:
            return apology("stock doesn't exist", 403)

        if not request.form.get("shares") or request.form.get("shares").isnumeric() == False:
            return apology("must input a number", 403)

        if int(request.form.get("shares")) < 1:
            return apology("must input positive number", 403)

        # create the symbol's dictionary
        dictionary = lookup(request.form.get("symbol"))

        # create variables for easy reading
        shares = int(request.form.get("shares"))
        price = dictionary["price"]
        amount = float(shares) * dictionary["price"]
        buy = "buy"

        # get the user's cash, then check if the total exists
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session["user_id"])
        total = float(cash[0]["cash"]) - amount

        if total < 0:
            return apology("you cannot afford this", 403)

        else:
            # update the user's amount of cash to reflect purchase
            db.execute("UPDATE users SET cash = :total WHERE id = :user_id",
                total = cash[0]["cash"] - amount,
                user_id = session["user_id"])

            # create a new row in the database for this new purchase under "buy" type
            db.execute("INSERT INTO transactions (symbol, price, shares, user_id, date_time, type) VALUES (?, ?, ?, ?, ?, ?)",
                dictionary["symbol"],
                price,
                shares,
                session["user_id"],
                datetime.datetime.now(),
                buy)

        return render_template("buy.html",
            buy = True,
            symbol = dictionary["symbol"],
            price = dictionary["price"],
            shares = shares,
            date = datetime.datetime.now(),
            amount = amount)

    if request.method == "GET":

        return render_template("buy.html", buy = False)


@app.route("/history")
@login_required
def history():

    rows = db.execute("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY date_time DESC", user_id = session["user_id"])

    for row in rows:
        row["price"] = usd(row["price"])

    return render_template("history.html", rows = rows)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 403)

        if lookup(request.form.get("symbol")) == None:
            return apology("stock doesn't exist", 403)

        # create the symbol's dictionary
        dictionary = lookup(request.form.get("symbol"))

        price = usd(dictionary["price"])

        # load the info into the page
        return render_template("quote.html",
            name = dictionary["name"],
            price = price,
            symbol = dictionary["symbol"],
            form = True)

    if request.method == "GET":
        return render_template("quote.html", form = False)


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 403)

        if not request.form.get("password"):
            return apology("must provide password", 403)

        if not request.form.get("confirmation"):
            return apology("must confirm password", 403)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 403)

        # load the user's row from the database
        row = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # check if it exists
        if len(row) > 0:
            return apology("username already exists", 403)

        # create a password
        passhash = generate_password_hash(request.form.get("password"))

        # insert the new user's info into the database
        db.execute("INSERT INTO users (username, hash) VALUES (%s, %s)", request.form.get("username"),
            passhash)

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must input a stock symbol", 403)

        if lookup(request.form.get("symbol")) == None:
            return apology("stock doesn't exist", 403)

        if not request.form.get("shares") or request.form.get("shares").isnumeric() == False:
            return apology("must input a number", 403)

        if int(request.form.get("shares")) < 1:
            return apology("must input positive number", 403)

        # variables for easier reference later
        dictionary = lookup(request.form.get("symbol"))
        shares = int(request.form.get("shares"))
        price = dictionary["price"]
        amount = float(shares) * dictionary["price"]
        totalShares = 0

        # get all the transactions that user has made for this specific symbol
        rows = db.execute("SELECT * FROM transactions WHERE user_id = :user_id AND symbol = :symbol",
            user_id = session["user_id"],
            symbol = request.form.get("symbol"))

        # if the row is "buy", add it to the total num of shares
        # else subtract it from the total number of shares
        for row in rows:
            if row["type"] == "buy":
                totalShares = totalShares + row["shares"]
            elif row["type"] == "sell":
                totalShares = totalShares - row["shares"]

        # get the users's current amount of cash
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
            user_id = session["user_id"])

        # if the user doesn't own that stock or has fewer shares than they want to sell, return error
        if rows == None or totalShares < shares:
            return apology("you cannot sell stock you do not own", 403)

        else:
            # update the cash amount to reflect the sold shares
            db.execute("UPDATE users SET cash = :total WHERE id = :user_id",
                total = cash[0]["cash"] + amount,
                user_id = session["user_id"])

            # add a new row to the transaction table of the "sell" type
            db.execute("INSERT INTO transactions (symbol, price, shares, user_id, date_time, type) VALUES (?, ?, ?, ?, ?, ?)",
                dictionary["symbol"],
                price,
                shares,
                session["user_id"],
                datetime.datetime.now(),
                "sell")

        return render_template("sell.html",
            sell = True,
            symbol = dictionary["symbol"],
            price = dictionary["price"],
            shares = shares,
            date = datetime.datetime.now(),
            amount = amount)

    else:

        return render_template("sell.html", sell = False)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
