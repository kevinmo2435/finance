import os

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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    syms = db.execute("SELECT symbol FROM stocks WHERE user_id = :uid",uid=session["user_id"])
    symsl = set()
    for sym in syms:
        symsl.add(sym["symbol"].upper())
    stocks = {}
    for sym in symsl:
        stocks.update({sym:lookup(sym)})
        stocks[sym]["price"] = usd(stocks[sym]["price"])
    shares = {}
    for sym in symsl:
        share = db.execute("SELECT shares FROM stocks WHERE user_id = :uid AND symbol = :symbol",uid = session["user_id"],symbol=sym.upper())
        tshares = 0;
        for ashares in share:
            tshares += ashares["shares"]
        shares.update({sym:tshares})
    totals = {}
    tcash = 0;
    for sym in symsl:
        details = lookup(sym)
        price = details["price"]
        numshares = shares[sym]
        total = price*numshares
        tcash +=total
        usdt = usd(total)
        totals.update({sym:usdt})
    money = db.execute("SELECT cash FROM users WHERE id = :user_id",user_id=session["user_id"])
    cash = money[0]["cash"]
    tcash+=cash
    cash = usd(cash)
    tcash = usd(tcash)

    return render_template("index.html",stocks = stocks, symsl = symsl,shares = shares,totals=totals,cash = cash,tcash = tcash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method=="POST":
        if not request.form.get("symbol"):
            return apology("missing symbol",400)
        symbol = request.form.get("symbol").upper()
        details = lookup(symbol)
        if not details:
            return apology("invalid symbol", 400)
        if not request.form.get("shares"):
            return apology("missing shares",400)
        if int(request.form.get("shares")) <1:
            return apology("invalid number", 400)
        else:
            money = db.execute("SELECT cash FROM users WHERE id = :user_id",user_id=session["user_id"])
            cash = money[0]["cash"]
            num = int(request.form.get("shares"))
            price = details["price"]
            newfunds =  cash - (num*price)
            if newfunds <0:
                return apology("not enough funds",403)
            syms = db.execute("SELECT symbol FROM stocks WHERE symbol = :symbol",symbol = symbol)
            if len(syms)>0:
                nums = db.execute("SELECT shares FROM stocks WHERE symbol=:symbol",symbol=symbol)
                numz = nums[0]["shares"]
                total = numz +num
                db.execute("UPDATE stocks SET shares = :total WHERE symbol = :symbol",total=total,symbol=symbol)
            else:    
                db.execute("INSERT  INTO stocks(user_id,symbol,shares) VALUES(:uid,:sym,:shares)",uid=session["user_id"],sym=symbol,shares=num)
            db.execute("UPDATE users SET cash = :newfunds WHERE id= :uid",newfunds=newfunds,uid=session["user_id"])
            return redirect("/")
    else:
        return render_template("buy.html")


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
    if request.method=="POST":
        symbol = request.form.get("quote")
        details = lookup(symbol)
        if not details:
            return apology("invalid symbol", 400)
        details["price"] = usd(details["price"])
        return render_template("quoted.html", details = details)
    else:
        return render_template("quote.html")
        


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method=="POST":
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if len(rows)==1:
            return apology("user name exists",403)
        elif not request.form.get("username"):
            return apology("must provide username", 403)
        elif not request.form.get("password"):
            return apology("must provide password", 403)
        elif not request.form.get("password_check"):
            return apology("must provide password", 403)
        elif  request.form.get("password") != request.form.get("password_check"):
            return apology("passwords must match", 403)
        else:
            name = request.form.get("username")
            phash = generate_password_hash(request.form.get("password"))
            db.execute("INSERT INTO users(username, hash) VALUES(:name, :phash)",name=name, phash = phash)
            return  render_template("login.html")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("missing symbol",400)
        if not request.form.get("shares"):
            return apology("missing shares",400)
        if int(request.form.get("shares"))<1:
            return apology("invalid shares",400)
        else:
            sell = int(request.form.get("shares"))
            details = lookup(request.form.get("symbol"))
            price = details["price"]
            syms = details["symbol"].upper()
            
            syms2 = db.execute("SELECT symbol FROM stocks WHERE user_id = :uid",uid=session["user_id"])
            symsl = set()
            for symz in syms2:
                symsl.add(symz["symbol"].upper())
                shares = {}
            for sym in symsl:
                share = db.execute("SELECT shares FROM stocks WHERE user_id = :uid AND symbol = :symbol",uid = session["user_id"],symbol=sym.upper())
                tshares = 0;
                for ashares in share:
                    tshares += ashares["shares"]
                shares.update({sym:tshares})
            stocknum = int(shares[syms])
            numstocks = stocknum-sell
            if numstocks<0:
                return apology("too many shares",400)
            print(syms)
            print(sell)
            print(stocknum)
            print(numstocks)
            db.execute("UPDATE stocks SET shares=:numstocks WHERE symbol=:syms",numstocks=numstocks,syms=syms)
            money = db.execute("SELECT cash FROM users WHERE id = :user_id",user_id=session["user_id"])
            cash = money[0]["cash"]
            cash+=price*sell
            db.execute("UPDATE users SET cash=:cash WHERE id=:user_id",cash=cash, user_id=session["user_id"])
            return redirect("/")
    else:
        syms = db.execute("SELECT symbol FROM stocks WHERE user_id = :uid",uid=session["user_id"])
    symsl = set()
    for sym in syms:
        symsl.add(sym["symbol"].upper())
    return render_template("sell.html",symsl=symsl)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        added = int(request.form.get("funds"))
        money = db.execute("SELECT cash FROM users WHERE id = :user_id",user_id=session["user_id"])
        cash = money[0]["cash"]
        added+=int(cash)
        db.execute("UPDATE users SET cash=:cash WHERE id=:uid", cash=added,uid=session["user_id"])
        return redirect("/")
    else:
        return render_template("add.html")
        
    
def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
