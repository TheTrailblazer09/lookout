"""Dev entry point:  python run.py   (or: flask --app run:app run)"""
from app import create_app
 
app = create_app()
 
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)