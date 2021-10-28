import os
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from requests.api import post
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import datetime
import math

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


@app.route("/")
@login_required
def index():
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    stocks = db.execute("SELECT stock, shares, total, price FROM portfolio WHERE id=:id", id=session["user_id"])
    if not stocks:
        return render_template("index1.html", cash=usd(cash[0]['cash']))
    else:
        stock_prices = db.execute("SELECT stock, shares, total, price FROM portfolio WHERE id=:id", id=session["user_id"])
        for price in stock_prices:
            symbol = stock_prices[0]['stock']
            price = lookup(symbol)['price']
            shares = stock_prices[0]['shares']
            total = price*shares
            db.execute("UPDATE portfolio SET price=:price, total=:total WHERE id=:id AND stock=:symbol", price=price,
                        total=total, id=session["user_id"], symbol=symbol)

        sumnums = db.execute("SELECT SUM(total) AS \"sumnums\" FROM portfolio WHERE id=:id", id=session["user_id"])
        if sumnums:
            grand_total = sumnums[0]['sumnums']+(cash[0]['cash'])
        else:
            grand_total = cash[0]['cash']
        return render_template("index.html", cash=usd(cash[0]['cash']), grand_total=usd(grand_total), stocks=stocks)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        # return apology if user does not enter a symbol
        if not request.form.get("symbol"):
            return apology("Must provide stock symbol!", 400)

    # return apology if user does not enter a number of shares or if that number is not a positive integer
        if not request.form.get("shares") or not request.form.get("shares").isdigit() or float(request.form.get("shares")) % 1 != 0 or int(request.form.get("shares")) <= 0:
            return apology("Invalid number!", 400)

    # attempt to look up the submitted stock symbol, return apology upon failure
        looked = lookup(request.form.get("symbol"))
        if not looked:
            return apology("Invalid stock symbol!", 400)

    # retrieve the user's cash from the database
        user_cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])

    # calculate the total price to pay
        price = looked["price"] * int(request.form.get("shares"))

    # return apology if price exceeds the amount of cash in the user's account
        if price > user_cash[0]['cash']:
            return apology("You too poor for that", 400)

    # update transactions table with purchase  
        transaction = db.execute("INSERT INTO transactions (id, worth, shares, symbol, purchase, price) VALUES(:id, :worth, :shares, :symbol, :purchase, :price)",
                                 id=session["user_id"], worth=price, shares=int(request.form.get("shares")), symbol=request.form.get("symbol"), price=looked["price"], purchase="purchase")

    # update portfolio table
        update = db.execute("SELECT shares FROM portfolio WHERE id=:id AND stock=:symbol",
                            id=session["user_id"], symbol=request.form.get("symbol"))
        if not update:
            db.execute("INSERT INTO portfolio (id, stock, shares, price, total) VALUES(:id, :symbol, :shares, :total, :price)",
                        id=session["user_id"], symbol=request.form.get("symbol"), shares=int(request.form.get("shares")), total=price, price=looked['price'])
        else:   
            new_shares = update[0]['shares']+int(request.form.get('shares'))
            new_total = new_shares*looked['price']
            db.execute("UPDATE portfolio SET shares=:shares, total=:total, price=:price WHERE id=:id and stock=:symbol",
                        shares=new_shares, total=new_total, id=session["user_id"], symbol=request.form.get("symbol"), price=looked['price'])

    # determine user's new cash and update it in the users table
        new_cash = user_cash[0]['cash'] - price
        update = db.execute("UPDATE users SET cash = :value WHERE id = :id", value=new_cash, id=session["user_id"])
        return render_template("bought.html", cash=usd(new_cash), price=usd(looked['price']), total=usd(price), shares=request.form.get("shares"), symbol=request.form.get("symbol"))
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    return apology("TODO")


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
        if len(rows) != 1 or not rows[0]['hash'] == request.form.get("password"):
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
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("enter a symbol!", 400)
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("invalid stock")
        price = stock["price"]
        symbol = stock["symbol"]
        return render_template("quote1.html", symbol=symbol, price=usd(price))
    else:
        return render_template("Quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        special_symbols = ["!", "#", "@", "&", ",", "$", "%", "*"]
        password = request.form.get("password")
        user = request.form.get("username")
        correctnes = []
        for char in special_symbols:
            if char in password:
                correctnes.append(True)
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password  and confirm password were submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif not request.form.get("confirmation"):
            return apology("must fill confirm password filed", 400)
        elif password != request.form.get("confirmation"):
            return apology("password and confirm password are not same try again", 400)

        # check if username is unique
        elif request.form.get("username") == db.execute("SELECT username FROM users WHERE username=?", user):
            return apology("username has been taken")
        # make sure of thet there is at least one special char in password
        elif not any(correctnes):
            return apology("you must use at least one special character in password")

        # continue if no error
        else:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", user, request.form.get("password"))

            # Redirect user to home page
            return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # return apology if user does not enter a symbol
        if not request.form.get("symbol"):
            return apology("Must provide stock symbol!", 400)
        # return apology if user does not enter a number of shares or if that number is not a positive integer
        elif not request.form.get("shares") or not request.form.get("shares").isdigit() or float(request.form.get("shares")) % 1 != 0 or int(request.form.get("shares")) <= 0:
            return apology("Invalid number!", 400)
        number = db.execute("SELECT shares FROM portfolio WHERE id=? and stock=?", session["user_id"], request.form.get("symbol"))
        total = db.execute("SELECT total FROM portfolio WHERE id=? and stock=?", session["user_id"], request.form.get("symbol"))
        if number[0]['shares'] < int(request.form.get("shares")):
            return apology("you dont have that many of stock to sell!", 400)
        else:
            looked = lookup(request.form.get("symbol"))
            value = looked['price'] * int(request.form.get("shares"))

            # UPDATE transactions table with sale
            transaction = db.execute("INSERT INTO transactions (id, worth, shares, symbol, purchase, price) VALUES(?, ?, ?, ?, ?, ?)",
                                    session["user_id"], value, int(request.form.get("shares")), request.form.get("symbol"), "sale", looked['price'])
            new_shares = number[0]['shares'] - int(request.form.get("shares"))
            new_total = total[0]['total'] - value
            if new_shares == 0:
                db.execute("DELETE FROM portfolio WHERE id=:id AND stock=:symbol",
                            id=session["user_id"], symbol=request.form.get("symbol"))
            else:
                db.execute("UPDATE portfolio SET shares=:shares, total=:total WHERE id=:id AND stock=:symbol",
                            shares=new_shares, total=new_total, id=session["user_id"], symbol=request.form.get("symbol"))

                # update cash
                cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
                new_cash = cash[0]['cash'] + value
                db.execute("UPDATE users SET cash = :set_cash WHERE id=:id", set_cash=new_cash , id=session["user_id"])
                return render_template("sold.html",
                                             shares=request.form.get("shares"), symbol=request.form.get("symbol"), get_price=value, cash_left=new_cash)
    else:
        stocks = db.execute("SELECT stock FROM portfolio WHERE id=?", session["user_id"])
        stock_name = []
        for item in stocks:
            stock_name.append(item["stock"])
        return render_template("sell.html", stocks=stock_name)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
