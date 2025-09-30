from flask import Flask, render_template, url_for

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("home.html", app_title="RideReady", page_title="Welcome")

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html", app_title="RideReady", page_title="Disclaimer")

@app.route("/advisor")
def advisor():
    # Non-functional placeholder for now
    return render_template("advisor.html", app_title="RideReady", page_title="Advisor")

if __name__ == "__main__":
    # Dev server only; we'll switch to Gunicorn in Docker later
    app.run(host="127.0.0.1", port=8080, debug=True)
