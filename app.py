from flask import Flask, render_template

app = Flask(__name__)

# Inject a global app title into all templates
@app.context_processor
def inject_app_title():
    return {"app_title": "RideReady"}

@app.route("/")
def home():
    return render_template("home.html", page_title="Home")

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html", page_title="Disclaimer")

@app.route("/advisor")
def advisor():
    return render_template("advisor.html", page_title="Advisor")

if __name__ == "__main__":
    app.run(debug=True)
