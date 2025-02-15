import ssl
from fastapi import FastAPI, HTTPException, Query
import os
import json
import subprocess
from pathlib import Path
import openai
import sqlite3
import markdown
from datetime import datetime

try:
    ssl.create_default_context()
except AttributeError:
    raise ImportError("SSL module is missing. Ensure your Python installation includes SSL support.")

app = FastAPI()

data_dir = Path("/data").resolve()

OPENAI_API_KEY = os.environ.get("AIPROXY_TOKEN")

def is_safe_path(path: Path) -> bool:
    try:
        return data_dir in path.resolve().parents and path.is_relative_to(data_dir)
    except (RuntimeError, ValueError, AttributeError):
        return False

@app.get("/read")
def read_file(path: str = Query(..., description="File path to read")):
    file_path = (data_dir / path.lstrip("/")).resolve()
    if not is_safe_path(file_path) or not file_path.is_file():
        raise HTTPException(status_code=403, detail="Access to this path is not allowed or file does not exist.")
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@app.post("/run")
def run_task(task: str = Query(..., description="Task description")):
    try:
        interpreted_task = interpret_task_with_llm(task)
        result = execute_task(interpreted_task)
        return {"status": "success", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def interpret_task_with_llm(task: str) -> dict:
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "Interpret the following task and return a JSON object with 'action' and 'params'."},
                  {"role": "user", "content": task}],
        api_key=OPENAI_API_KEY
    )
    return json.loads(response["choices"][0]["message"]["content"])

def execute_task(task_data: dict):
    action = task_data.get("action")
    params = task_data.get("params", {})

    if action == "install_uv_and_run_script":
        subprocess.run(["pip", "install", "uv"], check=True)
        subprocess.run(["python", "datagen.py", params.get("email", "")], check=True)
        return "Script executed successfully."
    
    elif action == "format_markdown":
        file_path = data_dir / "format.md"
        if file_path.exists():
            subprocess.run(["npx", "prettier", "--write", str(file_path)], check=True)
            return "Markdown formatted successfully."
    
    elif action == "count_wednesdays":
        file_path = data_dir / "dates.txt"
        if file_path.exists():
            with file_path.open() as f:
                dates = [line.strip() for line in f]
            count = sum(1 for d in dates if datetime.strptime(d, "%Y-%m-%d").weekday() == 2)
            (data_dir / "dates-wednesdays.txt").write_text(str(count))
            return "Wednesdays counted successfully."
    
    elif action == "sort_contacts":
        file_path = data_dir / "contacts.json"
        if file_path.exists():
            with file_path.open() as f:
                contacts = json.load(f)
            contacts.sort(key=lambda c: (c.get("last_name", ""), c.get("first_name", "")))
            (data_dir / "contacts-sorted.json").write_text(json.dumps(contacts, indent=2))
            return "Contacts sorted successfully."
    
    elif action == "extract_email_sender":
        file_path = data_dir / "email.txt"
        if file_path.exists():
            email_content = file_path.read_text()
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "Extract the sender's email from the following message."},
                          {"role": "user", "content": email_content}],
                api_key=OPENAI_API_KEY
            )
            sender_email = response["choices"][0]["message"]["content"].strip()
            (data_dir / "email-sender.txt").write_text(sender_email)
            return "Email sender extracted successfully."
    
    elif action == "calculate_ticket_sales":
        db_path = data_dir / "ticket-sales.db"
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT SUM(units * price) FROM tickets WHERE type = ?", ("Gold",))
                total_sales = cursor.fetchone()[0] or 0
            (data_dir / "ticket-sales-gold.txt").write_text(str(total_sales))
            return "Ticket sales calculated successfully."
    
    return "Unknown action."